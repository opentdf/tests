"""Pytest glue for the sparse-backed partial decrypt (DSPX-5545).

``--sparse 100GiB+112KiB`` collects ``test_sparse_partial_decrypt.py``. Without it
those tests are deselected, so nothing large reaches the per-PR runs or the
``--sizes`` fanout.

The plaintext ranges are planned here, before anything is encrypted. A
``--sparse`` run fails unless at least one encrypt and one partial decrypt
passed, even if everything else merely skipped. Every cell's outcome and
metrics go to the job summary and to ``--sparse-report``.
"""

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import pytest

import streamharness as sh
from perf import report

#: Seeded sample ranges, besides the fixed ones.
SAMPLES = 4
#: Plaintext offsets a reader keeping positions in 32 or 36 bits gets wrong.
WIDE = {"crosses-4GiB": 2**32, "crosses-64GiB": 2**36}
#: Bytes read either side of a boundary.
NEAR = 50


@dataclass(frozen=True)
class Settings:
    size: int
    seed: int
    #: What every encrypting SDK must write; None takes each one's default.
    segment_size: int | None
    timeout_s: float


_SETTINGS = pytest.StashKey[Settings]()
#: One per collected cell, by node id; outcomes and metrics are filled in.
_rows: dict[str, dict[str, Any]] = {}


def _size(v: str) -> int:
    """``"100GiB+112KiB"`` -> 107374297088: a sum, so a size can miss every
    segment boundary."""
    try:
        n = sum(sh.parse_bytes(term) for term in v.split("+"))
    except ValueError:
        n = 0
    if n <= 0:
        raise argparse.ArgumentTypeError(
            f"expected a size like 100GiB+112KiB; got {v!r}"
        )
    return n


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sparse", "sparse-backed partial decrypt (DSPX-5545)")
    group.addoption(
        "--sparse",
        type=_size,
        metavar="SIZE",
        help="encrypt SIZE (e.g. 100GiB+112KiB) once per SDK into a sparse store, then "
        "partially decrypt planned ranges through an NFS mount of it; without "
        "it test_sparse_partial_decrypt.py is not collected",
    )
    group.addoption(
        "--sparse-segment-size",
        type=_size,
        metavar="SIZE",
        help="segment size each encrypting SDK must write. No CLI can be told, "
        "so an SDK whose default differs skips. Default: each SDK's own",
    )
    group.addoption(
        "--sparse-timeout",
        type=float,
        default=7200.0,
        metavar="SECONDS",
        help="timeout for each encrypt (default 7200)",
    )
    group.addoption(
        "--sparse-seed",
        type=int,
        metavar="INT",
        help="seed for the sampled ranges; random by default, and reported",
    )
    group.addoption(
        "--sparse-report",
        type=Path,
        default=Path("test-results/sparse-partial-decrypt.json"),
        metavar="PATH",
        help="where to write the run's metrics as JSON",
    )


def settings(config: pytest.Config) -> Settings | None:
    size = config.getoption("--sparse", default=None)
    if not size:
        return None
    if _SETTINGS not in config.stash:
        seed = config.getoption("--sparse-seed")
        config.stash[_SETTINGS] = Settings(
            size=size,
            seed=random.SystemRandom().randrange(2**32) if seed is None else seed,
            segment_size=config.getoption("--sparse-segment-size"),
            timeout_s=cast(float, config.getoption("--sparse-timeout")),
        )
    return config.stash[_SETTINGS]


def range_names(n: int) -> list[str]:
    names = ["first-segment", "last-segment", "segment-boundary"]
    names += [name for name, at in WIDE.items() if at + NEAR <= n]
    return names + [f"sample-{i}" for i in range(SAMPLES)]


def plan_ranges(n: int, seg: int, seed: int) -> dict[str, tuple[int, int]]:
    """Plaintext ``(start, end)`` to keep and read back, by :func:`range_names`."""
    whole = n // seg
    if whole < 2:
        raise ValueError(f"{n} bytes is less than two {seg}-byte segments")
    middle = whole // 2 * seg
    ranges = {
        "first-segment": (0, seg),
        "last-segment": ((n - 1) // seg * seg, n),
        "segment-boundary": (middle - NEAR, middle + NEAR),
    }
    ranges |= {
        name: (at - NEAR, at + NEAR) for name, at in WIDE.items() if at + NEAR <= n
    }
    rng = random.Random(seed)
    for i in range(SAMPLES):
        start = rng.randrange(whole) * seg + rng.randrange(seg)
        ranges[f"sample-{i}"] = (start, min(n, start + rng.randint(1, 64 << 10)))
    return ranges


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    s = settings(metafunc.config)
    if s and "sparse_range" in metafunc.fixturenames:
        metafunc.parametrize("sparse_range", range_names(s.size))


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if settings(config):
        return
    cells = [i for i in items if i.get_closest_marker("sparse")]
    if cells:
        dropped = set(map(id, cells))
        config.hook.pytest_deselected(items=cells)
        items[:] = [i for i in items if id(i) not in dropped]


def pytest_collection_finish(session: pytest.Session) -> None:
    if not settings(session.config):
        return
    for item in session.items:
        if not item.get_closest_marker("sparse"):
            continue
        callspec = getattr(item, "callspec", None)
        p = callspec.params if callspec else {}
        if "decrypt_sdk" in p:
            row = {
                "op": "decrypt",
                "encrypt": str(p.get("encrypt_sdk")),
                "decrypt": str(p["decrypt_sdk"]),
                "range": p.get("sparse_range"),
            }
        else:
            row = {"op": "encrypt", "sdk": str(p.get("encrypt_sdk"))}
        _rows[item.nodeid] = row | {"outcome": "not run"}


def _reason(rep: pytest.TestReport) -> str:
    if rep.skipped and isinstance(rep.longrepr, tuple):
        return str(rep.longrepr[2]).removeprefix("Skipped: ")
    crash = getattr(rep.longrepr, "reprcrash", None)
    text = getattr(crash, "message", None) or str(rep.longrepr)
    return text.strip().splitlines()[0][:300] if text.strip() else ""


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    row = _rows.get(report.nodeid)
    if row is None or row["outcome"] in ("failed", "error"):
        return
    if report.failed:
        row["outcome"] = "failed" if report.when == "call" else "error"
        row["reason"] = _reason(report)
    elif report.skipped:
        row["outcome"], row["reason"] = "skipped", _reason(report)
    elif report.when == "call":
        row["outcome"] = "passed"


@pytest.fixture(scope="session")
def sparse_settings(pytestconfig: pytest.Config) -> Settings:
    s = settings(pytestconfig)
    assert s is not None, "collected without --sparse"
    return s


@pytest.fixture
def sparse_row(request: pytest.FixtureRequest) -> dict[str, Any]:
    """This cell's report row: add metrics to it."""
    return _rows.setdefault(request.node.nodeid, {"outcome": "not run"})


def _mib(n: int | None) -> str:
    return "" if n is None else f"{n / 2**20:,.1f} MiB"


def _result(row: dict[str, Any]) -> str:
    text = row["outcome"]
    if row.get("reason"):
        text += f": {row['reason']}"
    return text.replace("|", "\\|").replace("\n", " ")[:240]


def _bounded(row: dict[str, Any], value: str, bound: str) -> str:
    if value not in row:
        return ""
    return f"{_mib(row[value])} / {_mib(row[bound])}"


def markdown(s: Settings, rows: list[dict[str, Any]]) -> str:
    seg = f"{_mib(s.segment_size)}" if s.segment_size else "each SDK's default"
    lines = [
        f"\n### Sparse partial decrypt (DSPX-5545): {s.size / 2**30:,.1f} GiB\n",
        "Partial-read capability: every cell decrypts one planned range, from an "
        "NFS mount of a store that never held the whole TDF. Not a full decrypt.\n",
        f"Seed {s.seed}; segment size {seg}; encrypt timeout {s.timeout_s:g} s.\n",
        "| encrypt | result | route | payload start | segment | segments "
        "| manifest | wall | throughput | peak RSS | retained | peak disk / bound |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r.get("op") != "encrypt":
            continue
        rate = r.get("throughput_bps")
        lines.append(
            "| "
            + " | ".join(
                [
                    r["sdk"],
                    _result(r),
                    r.get("route", ""),
                    str(r.get("payload_start", "")),
                    _mib(r.get("segment_size")),
                    str(r.get("segment_count", "")),
                    _mib(r.get("manifest_bytes")),
                    f"{r['wall_s']:.0f} s" if "wall_s" in r else "",
                    f"{rate / 2**20:,.0f} MiB/s" if rate else "",
                    _mib(r.get("peak_rss_bytes")),
                    _mib(r.get("retained_bytes")),
                    _bounded(r, "peak_disk_bytes", "disk_bound_bytes"),
                ]
            )
            + " |"
        )
    lines += [
        "",
        "| encrypt | decrypt | range | plaintext | result | wall | peak RSS "
        "| fetched / bound | filler READs | peak disk / bound |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if r.get("op") != "decrypt":
            continue
        span = f"{r['start']:,}-{r['end']:,}" if "start" in r else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    r["encrypt"],
                    r["decrypt"],
                    str(r["range"]),
                    span,
                    _result(r),
                    f"{r['wall_s']:.1f} s" if "wall_s" in r else "",
                    _mib(r.get("peak_rss_bytes")),
                    _bounded(r, "fetched_bytes", "fetch_bound_bytes"),
                    str(r.get("filler_reads", "")),
                    _bounded(r, "peak_disk_bytes", "disk_bound_bytes"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _gate(rows: list[dict[str, Any]]) -> str | None:
    passed = {r.get("op") for r in rows if r["outcome"] == "passed"}
    missing = [op for op in ("encrypt", "decrypt") if op not in passed]
    if missing:
        return f"--sparse was given, but no {' or '.join(missing)} cell passed"
    return None


def _reporting(config: pytest.Config) -> Settings | None:
    if config.option.collectonly or getattr(config, "workerinput", None):
        return None
    return settings(config)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    s = _reporting(config)
    if s is None:
        return
    rows = list(_rows.values())
    path = config.rootpath / cast(Path, config.getoption("--sparse-report"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ticket": "DSPX-5545",
                **asdict(s),
                "encrypt": [r for r in rows if r.get("op") == "encrypt"],
                "decrypt": [r for r in rows if r.get("op") == "decrypt"],
            },
            indent=2,
        )
    )
    report.append_step_summary(markdown(s, rows))
    if _gate(rows) and exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    s = _reporting(config)
    if s is None:
        return
    rows = list(_rows.values())
    terminalreporter.write_sep("=", "sparse partial decrypt")
    for line in markdown(s, rows).splitlines():
        terminalreporter.write_line(line)
    if failure := _gate(rows):
        terminalreporter.write_line(f"FAILED: {failure}", red=True)
