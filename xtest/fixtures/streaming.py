"""Pytest glue for the streaming harness (DSPX-5108).

``--stream chunky`` collects ``test_streaming.py`` at 5 MiB, ``--stream
medium`` at 2.1 GiB. Without the option those tests are deselected, so the
harness stays out of the ordinary ``pt_file``/``--sizes`` fanout.

A ``--stream`` run that finishes without one streaming control passing fails,
even if every test merely skipped.
"""

import argparse
import logging
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import sizes
import streamharness as sh
import tdfs
from perf import report

logger = logging.getLogger("xtest")

#: The probe's size, and so the 5 MiB control's.
PROBE_BYTES = sizes.CHUNKY_BYTES

_passed = 0
_summaries: list[str] = []


def _stream_sizes(v: str) -> list[str]:
    names = {s.strip() for s in v.split(",") if s.strip()}
    unknown = sorted(names - set(sizes.SIZES))
    if not names or unknown:
        raise argparse.ArgumentTypeError(
            f"expected one or more of {', '.join(sizes.SIZE_ORDER)}; got {v!r}"
        )
    return [n for n in sizes.SIZE_ORDER if n in names]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("streaming", "bounded streaming harness (DSPX-5108)").addoption(
        "--stream",
        type=_stream_sizes,
        metavar="SIZES",
        help="run the streaming controls in test_streaming.py at these sizes, "
        "e.g. chunky (5 MiB) or chunky,medium (2.1 GiB); without it they are "
        "not collected",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    # Not parametrized over an empty list without --stream: pytest would turn
    # that into a skip per test. The items are deselected instead.
    stream = metafunc.config.getoption("--stream")
    if stream and "stream_size" in metafunc.fixturenames:
        metafunc.parametrize("stream_size", stream)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--stream"):
        return
    drop = [i for i in items if i.get_closest_marker("stream")]
    if drop:
        dropped = set(map(id, drop))
        config.hook.pytest_deselected(items=drop)
        items[:] = [i for i in items if id(i) not in dropped]


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    global _passed
    if report.when == "call" and report.passed and "stream" in report.keywords:
        _passed += 1


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if session.config.getoption("--stream") and not _passed and exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    if not config.getoption("--stream"):
        return
    terminalreporter.write_sep("=", "streaming harness")
    for s in _summaries:
        terminalreporter.write_line(s)
    if not _passed:
        terminalreporter.write_line(
            "FAILED: --stream was given, but no streaming control passed"
        )


def encrypt_command(sdk: tdfs.SDK) -> sh.Command:
    return lambda src, dst: sdk.encrypt_command(src, dst, container="ztdf")


def decrypt_command(sdk: tdfs.SDK) -> sh.Command:
    return lambda src, dst: sdk.decrypt_command(src, dst, container="ztdf")


def _mib(n: int) -> str:
    return f"{n / 2**20:,.1f} MiB"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")[:240]


def verdict(a: sh.Attempt) -> str:
    if a.error:
        return f"unsupported: {a.error}"
    if a.spooled and a.run is not None:
        return f"accepted, but spooled {_mib(a.run.peak_tmp_bytes)} to TMPDIR"
    return "**streams**"


_HEADER = (
    "| op | src | dst | result | in | out | wall | peak RSS | peak scratch |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
)


def row(op: str, route: sh.Route, result: str, r: sh.Run[Any] | None) -> str:
    nums = (
        [
            _mib(r.bytes_in),
            _mib(r.bytes_out),
            f"{r.wall_s:.1f} s",
            _mib(r.peak_rss_bytes),
            _mib(r.peak_scratch_bytes),
        ]
        if r
        else [""] * 5
    )
    return "| " + " | ".join([op, route.src, route.dst, _cell(result), *nums]) + " |\n"


def summarize(title: str, rows: list[str], notes: list[str]) -> None:
    text = f"\n#### {title}\n\n{_HEADER}{''.join(rows)}"
    text += "".join(f"\n- {n}" for n in notes) + "\n"
    _summaries.append(text)
    logger.info("%s", text)
    report.append_step_summary(text)


def chosen(probe: sh.Probe, op: str) -> sh.Attempt:
    return probe.encrypt if op == "encrypt" else probe.decrypt


def probe_notes(probe: sh.Probe) -> list[str]:
    notes: list[str] = []
    for a in (probe.encrypt, probe.decrypt):
        notes.append(f"{a.op}: {a.route}")
        evidence = a.run.result if a.run else None
        if isinstance(evidence, sh.TdfEvidence) and evidence.payload_start:
            # A SparseSink plan for this route needs it (DSPX-5545).
            notes[-1] += f" (payload_start {evidence.payload_start})"
        if a.route.src == "file":
            notes[-1] += (
                " -- input must be a seekable file: a DSPX-5543 mount above "
                "scratch size, a materialised copy below it"
            )
        if a.route.dst == "file":
            notes[-1] += " -- output must be a regular file, written to scratch"
    return notes


def stream_scratch(tmp_dir: Path, sdk: tdfs.SDK, name: str) -> Path:
    """A fresh scratch root for one SDK's runs; the budget's scratch is measured here."""
    root = tmp_dir / "stream" / f"{sdk.sdk}-{sdk.version.replace('/', '-')}" / name
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    return root


@pytest.fixture(scope="session")
def stream_probe(tmp_dir: Path) -> Callable[[tdfs.SDK], sh.Probe]:
    """Probe an SDK's CLI once per session, at 5 MiB, and report what it accepts."""
    cache: dict[tdfs.SDK, sh.Probe] = {}

    def get(sdk: tdfs.SDK) -> sh.Probe:
        if sdk not in cache:
            scratch = stream_scratch(tmp_dir, sdk, "probe")
            probe = sh.probe(
                encrypt_command(sdk),
                decrypt_command(sdk),
                sh.Plaintext(PROBE_BYTES),
                scratch=scratch,
                budget=sh.Budget.from_env(timeout_s=300),
            )
            summarize(
                f"{sdk}: {_mib(PROBE_BYTES)} probe",
                [
                    row(
                        a.op + (" (chosen)" if a is chosen(probe, a.op) else ""),
                        a.route,
                        verdict(a),
                        a.run,
                    )
                    for a in probe.attempts
                ],
                probe_notes(probe),
            )
            shutil.rmtree(scratch, ignore_errors=True)
            cache[sdk] = probe
        return cache[sdk]

    return get
