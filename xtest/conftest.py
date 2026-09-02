"""Pytest configuration and core fixtures for OpenTDF integration tests.

This module contains:
- Pytest CLI options and test parametrization logic
- Core fixtures (test files, temp directories, otdfctl)
- Helper functions for test configuration

Domain-specific fixtures are organized in the fixtures/ package:
- fixtures.kas: KAS registry and KAS entry fixtures
- fixtures.attributes: Attribute and ABAC fixtures
- fixtures.assertions: TDF assertion fixtures
- fixtures.obligations: Obligation and trigger fixtures
- fixtures.keys: Key management fixtures
"""

import argparse
import json
import logging
import os
import random
import typing
import warnings
from pathlib import Path
from typing import cast

import pytest

import sizes
import tdfs
from otdfctl import OpentdfCommandLineTool
from perf import report, stats
from perf.cells import cells_for

logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))


def pytest_report_header() -> list[str]:
    """Surface PlatformFeatureSet detection in the always-visible session header.

    Feature detection drives skips (e.g. mechanism-xwing gates the PQ/T tests),
    and pytest does not show captured output for skipped tests. Echoing the
    detected version and feature set into the report header makes it visible in
    CI even when every gated test skips.

    Detection probes the platform over HTTP, which fails when there is no
    platform -- running only the offline unit tests, for instance. That is a
    header, not a test result, so report the failure and carry on rather than
    breaking collection for tests that never needed a platform.
    """
    try:
        pfs = tdfs.get_platform_features()
    except Exception as e:  # a header must never break collection
        return [f"platform features unavailable: {e}"]
    return [
        f"platform version: {pfs.version} (semver={pfs.semver})",
        f"detected features: {', '.join(sorted(pfs.features))}",
    ]


# Load all fixture modules
pytest_plugins = [
    "fixtures.kas",
    "fixtures.attributes",
    "fixtures.assertions",
    "fixtures.obligations",
    "fixtures.keys",
    "fixtures.audit",
    "fixtures.encryption",
    "fixtures.bench",
]


def englist(s: tuple[str, ...]) -> str:
    """Convert tuple of strings to English list format (e.g., 'a, b, or c')."""
    if len(s) > 1:
        return ", ".join(s[:-1]) + ", or " + s[-1]
    elif s:
        return s[0]
    return ""


def is_type_or_list_of_types(t: typing.Any) -> typing.Callable[[str], typing.Any]:
    """Create a validator function for CLI options that accept one or more typed values."""

    def is_a(v: str) -> typing.Any:
        for i in v.split():
            if i not in typing.get_args(t):
                raise ValueError(f"Invalid value for {t}: {i}")
        return v

    return is_a


def sdk_spec_type(v: str) -> str:
    """Validate a whitespace-separated list of SDK specifiers: 'go', 'go@*', 'go@main java@v1.2.0', etc."""
    specs = v.split()
    if not specs:
        raise ValueError("At least one SDK specifier is required")
    for spec in specs:
        parts = spec.split("@", 1)
        if not tdfs.is_sdk_type(parts[0]):
            raise ValueError(f"Invalid SDK type: {parts[0]!r}")
        if len(parts) == 2 and not parts[1]:
            raise ValueError(
                f"Empty version in SDK specifier {spec!r}; use e.g. go@main, go@v0.18.0, go@*"
            )
    return v


def sizes_opt_type(v: str) -> list[str]:
    """Validate and de-duplicate a comma-separated list of size names.

    ``ArgumentTypeError`` rather than ``ValueError``: argparse prints the
    former's message verbatim and replaces the latter's with a generic
    "invalid value", which would hide the list of names that would have
    worked.
    """
    names = [s.strip() for s in v.split(",") if s.strip()]
    if not names:
        raise argparse.ArgumentTypeError("at least one size is required")
    for name in names:
        if name not in sizes.SIZES:
            raise argparse.ArgumentTypeError(
                f"unknown size {name!r}; expected one or more of "
                f"{', '.join(sizes.SIZE_ORDER)}"
            )
    # Cheapest first, so a fan-out run reports its fast cells before spending
    # minutes on a multi-GiB one.
    return [n for n in sizes.SIZE_ORDER if n in set(names)]


_SIZES_KEY = pytest.StashKey[list[str]]()


def resolve_sizes(config: pytest.Config) -> list[str]:
    """Size names this session runs, honouring the deprecated --large alias.

    Cached on the config: this is called from both the parametrizer and the
    collection filter, and the deprecation warning below should be emitted
    once per session rather than once per caller.
    """
    cached = config.stash.get(_SIZES_KEY, None)
    if cached is not None:
        return cached

    selected = cast(list[str] | None, config.getoption("--sizes"))
    if config.getoption("--large"):
        if selected is not None:
            raise pytest.UsageError(
                "--large and --sizes are mutually exclusive; --large is the "
                "deprecated spelling of --sizes small,large"
            )
        warnings.warn(
            "--large is deprecated; use --sizes small,large (or --sizes medium "
            "for the 2-4 GiB ZIP64 band, which --large steps straight over)",
            DeprecationWarning,
            stacklevel=2,
        )
        resolved = ["small", "large"]
    else:
        resolved = selected if selected is not None else ["small"]

    config.stash[_SIZES_KEY] = resolved
    return resolved


def pytest_addoption(parser: pytest.Parser):
    """Add custom CLI options for pytest."""
    parser.addoption(
        "--audit-log-dir",
        help="directory to write audit logs on test failure (default: tmp/audit-logs)",
        type=Path,
    )
    parser.addoption(
        "--audit-log-services",
        help="comma-separated list of docker compose services to monitor for audit logs",
        type=lambda s: [s.strip() for s in s.split(",")],
    )
    parser.addoption(
        "--containers",
        help=f"which container formats to test, one or more of {englist(typing.get_args(tdfs.container_type))}",
        type=is_type_or_list_of_types(tdfs.container_type),
    )
    parser.addoption(
        "--focus",
        help="skips tests which don't use the requested sdk",
        type=is_type_or_list_of_types(tdfs.focus_type),
    )
    parser.addoption(
        "--large",
        action="store_true",
        help="deprecated alias for --sizes small,large",
    )
    parser.addoption(
        "--sizes",
        type=sizes_opt_type,
        help="comma-separated plaintext sizes to run against, from "
        f"{englist(tuple(sizes.SIZE_ORDER))} "
        f"({', '.join(f'{k}={sizes.SIZES[k]}B' for k in sizes.SIZE_ORDER)}); "
        "default small. Listing more than one fans out every test that takes "
        "a plaintext file, so CI passes exactly one.",
    )
    parser.addoption(
        "--no-audit-logs",
        action="store_true",
        help="disable automatic KAS audit log collection",
    )
    parser.addoption(
        "--skip-released-pairs",
        action="store_true",
        help="skip round-trip tests where all SDKs are released artifacts",
    )
    parser.addoption(
        "--sdks",
        help=f"select which sdks to run by default, unless overridden; one or more of {englist(typing.get_args(tdfs.sdk_type))}, optionally version-qualified (e.g. go@main, go@v0.18.0, go@*)",
        type=sdk_spec_type,
    )
    parser.addoption(
        "--sdks-decrypt",
        help="select which sdks to run for decrypt only; accepts same format as --sdks",
        type=sdk_spec_type,
    )
    parser.addoption(
        "--sdks-encrypt",
        help="select which sdks to run for encrypt only; accepts same format as --sdks",
        type=sdk_spec_type,
    )
    _add_benchmark_options(parser)


def _add_benchmark_options(parser: pytest.Parser):
    """Options for the SDK performance regression benchmarks.

    Grouped separately because they configure an experiment rather than
    selecting tests, and because none of them do anything without --bench.
    """
    group = parser.getgroup("benchmarks", "SDK performance regression benchmarks")
    group.addoption(
        "--bench",
        action="store_true",
        help="run the performance regression benchmarks (they are long, so they "
        "are opt-in and collect nothing otherwise)",
    )
    group.addoption(
        "--bench-baseline",
        help="build to compare against, e.g. go@v0.29.0; defaults to the newest "
        "installed release of each sdk",
    )
    group.addoption(
        "--bench-candidate",
        help="build under test, e.g. go@main; defaults to the installed "
        "unreleased build of each sdk",
    )
    group.addoption(
        "--bench-threshold",
        type=float,
        default=stats.DEFAULT_THRESHOLD,
        help="smallest slowdown ratio worth failing on (default: %(default)s, "
        "i.e. 15%% slower)",
    )
    group.addoption(
        "--bench-min-rounds",
        type=int,
        default=20,
        help="paired rounds to run before the stopping rule may fire "
        "(default: %(default)s)",
    )
    group.addoption(
        "--bench-max-rounds",
        type=int,
        default=60,
        help="hard cap on paired rounds per cell (default: %(default)s)",
    )
    group.addoption(
        "--bench-warmup",
        type=int,
        default=5,
        help="paired rounds discarded before measuring, to pay one-time costs "
        "like page cache and package resolution (default: %(default)s)",
    )
    group.addoption(
        "--bench-budget-seconds",
        type=float,
        default=1500.0,
        help="wall-clock allowance shared by every cell (default: %(default)s)",
    )
    group.addoption(
        "--bench-seed",
        type=int,
        default=0,
        help="seed for payload generation, round ordering, and the bootstrap; "
        "fixing it makes a run reproducible (default: %(default)s)",
    )
    group.addoption(
        "--bench-out",
        type=Path,
        default=Path("test-results/benchmarks"),
        help="directory for the JSON result artifact (default: %(default)s)",
    )
    group.addoption(
        "--bench-no-gate",
        action="store_true",
        help="measure and report, but never fail the run on a regression",
    )


def pytest_generate_tests(metafunc: pytest.Metafunc):
    """Dynamically parametrize test functions based on CLI options.

    This hook parametrizes fixtures based on command-line options:
    - size: large or small test files
    - encrypt_sdk: which SDK(s) to use for encryption
    - decrypt_sdk: which SDK(s) to use for decryption
    - in_focus: filter tests by SDK focus
    - container: which container formats to test (ztdf, ztdf-ecwrap)
    """
    if "size" in metafunc.fixturenames:
        metafunc.parametrize("size", resolve_sizes(metafunc.config), scope="session")

    def list_opt(name: str, t: typing.Any) -> list[str]:
        ttt = typing.get_args(t)
        v = metafunc.config.getoption(name)
        if not v:
            return []
        if type(v) is not str:
            raise ValueError(f"Invalid value for {name}: {v}")
        a = v.split()
        for i in a:
            if i not in ttt:
                raise ValueError(f"Invalid value for {name}: {i}, must be one of {ttt}")
        return a

    def sdk_specs_opt(names: list[str]) -> list[str]:
        """Return SDK specifier tokens from the first matching option, or all sdk types."""
        for name in names:
            v = metafunc.config.getoption(name)
            if v:
                return v.split()
        return list(typing.get_args(tdfs.sdk_type))

    subject_sdks: set[tdfs.SDK] = set()

    if "encrypt_sdk" in metafunc.fixturenames:
        try:
            e_sdks = [
                sdk
                for spec in sdk_specs_opt(["--sdks-encrypt", "--sdks"])
                for sdk in tdfs.parse_sdk_spec(spec)
            ]
        except (FileNotFoundError, ValueError) as e:
            raise pytest.UsageError(str(e)) from e
        metafunc.parametrize("encrypt_sdk", e_sdks, ids=[str(x) for x in e_sdks])
        subject_sdks |= set(e_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        try:
            d_sdks = [
                sdk
                for spec in sdk_specs_opt(["--sdks-decrypt", "--sdks"])
                for sdk in tdfs.parse_sdk_spec(spec)
            ]
        except (FileNotFoundError, ValueError) as e:
            raise pytest.UsageError(str(e)) from e
        metafunc.parametrize("decrypt_sdk", d_sdks, ids=[str(x) for x in d_sdks])
        subject_sdks |= set(d_sdks)

    if "in_focus" in metafunc.fixturenames:
        focus_opt = "all"
        if metafunc.config.getoption("--focus"):
            focus_opt = metafunc.config.getoption("--focus")
        focus: set[tdfs.sdk_type] = set()
        if focus_opt == "all":
            focus = set(typing.get_args(tdfs.sdk_type))
        else:
            focus = cast(set[tdfs.sdk_type], set(list_opt("--focus", tdfs.focus_type)))
        focused_sdks = {s for s in subject_sdks if s.sdk in focus}
        metafunc.parametrize("in_focus", [focused_sdks])

    if "container" in metafunc.fixturenames:
        containers: list[tdfs.container_type] = []
        if metafunc.config.getoption("--containers"):
            containers = cast(
                list[tdfs.container_type], list_opt("--containers", tdfs.container_type)
            )
        else:
            containers = list(typing.get_args(tdfs.container_type))
        metafunc.parametrize("container", containers)

    if "bench_cell" in metafunc.fixturenames:
        _parametrize_bench_cells(metafunc)


def _parametrize_bench_cells(metafunc: pytest.Metafunc):
    """Fan the benchmark module out over its cells.

    Without --bench there is nothing to fan out over, and the items are
    dropped wholesale in :func:`pytest_collection_modifyitems` rather than
    parametrized here. Parametrizing over an empty list would *not* collect
    zero items: pytest's default ``empty_parameter_set_mark`` turns an empty
    set into one skipped item per test, so every ordinary run would carry
    benchmark skips it never asked for.
    """
    if not metafunc.config.getoption("--bench"):
        return

    # --sdks may be version-qualified (go@main); benchmark arms come from
    # --bench-baseline/--bench-candidate instead, so only the name matters.
    specs = metafunc.config.getoption("--sdks") or " ".join(
        typing.get_args(tdfs.sdk_type)
    )
    names = list(dict.fromkeys(s.split("@", 1)[0] for s in str(specs).split()))
    cells = cells_for(names)
    metafunc.config.stash[report.CELLS_KEY] = cells
    metafunc.parametrize("bench_cell", cells, ids=[c.id for c in cells])


def pytest_configure(config: pytest.Config):
    if not config.getoption("--bench", default=False):
        return
    # Parallel workers contend for the CPU the benchmark is measuring, which
    # turns every number into noise. The CI step also omits -n; this guard is
    # what stops a later edit from silently invalidating the whole job.
    distributed = getattr(config, "workerinput", None) is not None or bool(
        config.getoption("numprocesses", default=None)
    )
    if distributed:
        raise pytest.UsageError(
            "--bench cannot run under pytest-xdist: parallel workers compete "
            "for the CPU being measured. Drop -n / --dist."
        )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Drop cells the session did not ask for.

    Two groups, deselected rather than skipped for the same reason: neither a
    20-minute benchmark nor a 2.1 GiB roundtrip has any business in the
    regular integration matrix, and a skip would report them as tests that
    exist and were declined rather than ones that were never in scope.

    - ``benchmark``: needs --bench.
    - ``zip64``: needs a payload size that can reach the 2**31 boundary. At
      the default 128 bytes these tests cannot exercise anything, and the one
      thing worse than not running them is running them green on a payload
      that never touches the code path.
    """
    drop: list[pytest.Item] = []
    want_bench = bool(config.getoption("--bench", default=False))
    want_zip64 = any(sizes.exercises_zip64_window(s) for s in resolve_sizes(config))
    for item in items:
        if not want_bench and item.get_closest_marker("benchmark"):
            drop.append(item)
        elif not want_zip64 and item.get_closest_marker("zip64"):
            drop.append(item)
    if drop:
        dropped = set(map(id, drop))
        config.hook.pytest_deselected(items=drop)
        items[:] = [i for i in items if id(i) not in dropped]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int):
    """Analyse every recorded cell, write the artifacts, and gate the run.

    The gate lives here rather than in the cells because it is a run-level
    decision: the multiplicity correction spans all cells, and the A/A control
    can invalidate the lot. Artifacts are written first and unconditionally --
    a run that is about to fail is exactly the run whose raw numbers someone
    will want to read.
    """
    del exitstatus  # the benchmark's own verdict is independent of test outcomes
    config = session.config
    if not config.getoption("--bench", default=False):
        return
    recorder = config.stash.get(report.RECORDER_KEY, None)
    if recorder is None or not (recorder.results or recorder.skipped):
        return

    # Imported here, not at module scope: importing a pytest plugin from a
    # conftest before pytest registers it costs the plugin its assertion
    # rewriting, which the fixture module's own asserts rely on.
    from fixtures import bench

    bench_config = bench.config_from_options(config)
    recorder.metadata = bench.runner_metadata(config)
    gate = recorder.gate(bench_config)

    cells = config.stash.get(report.CELLS_KEY, [])
    name = "-".join(dict.fromkeys(c.sdk for c in cells)) or "benchmarks"
    out_dir = cast(Path, config.getoption("--bench-out"))
    json_path = report.write_json(
        out_dir / f"{name}.json", recorder, bench_config, gate
    )

    summary = report.markdown(recorder, bench_config, gate)
    report.append_step_summary(summary)
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "benchmark results")
        reporter.write_line(gate.summary)
        reporter.write_line(f"raw samples and statistics: {json_path}")

    if config.getoption("--bench-no-gate", default=False):
        return
    # A run that measured nothing fails too, and not only one that found a
    # regression. --bench is an explicit request for a measurement; answering
    # it with a green tick and an empty table is the one outcome nobody
    # inspects, so a benchmark that has quietly stopped measuring can survive
    # indefinitely. Every reason a cell skips is already in the report.
    if gate.should_fail or gate.nothing_measured:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_runtest_setup(item: pytest.Item):
    if not item.config.getoption("--skip-released-pairs", default=False):
        return
    params = getattr(item, "callspec", None)
    if params is None:
        return
    e = params.params.get("encrypt_sdk")
    d = params.params.get("decrypt_sdk")
    if e is not None and d is not None and e.is_released() and d.is_released():
        pytest.skip(f"released-only pair ({e} × {d})")


# Core fixtures

#: Chunk written per iteration by :func:`_write_bulk_plaintext`.
_BULK_BLOCK = 1 << 20

#: Sizes at or above this are generated in bulk rather than line by line.
#: The line generator formats one string per 16 bytes, which is fine for 128
#: bytes and is ~140 million iterations at 2.1 GiB.
_BULK_THRESHOLD = 1 << 24


def _write_line_plaintext(path: Path, length: int) -> None:
    """The original generator: one right-aligned offset per 16 bytes.

    Kept byte-for-byte for the small size. Existing tests compare decrypted
    output against this content, and there is nothing to gain from churning
    it.
    """
    with path.open("w") as f:
        for i in range(0, length, 16):
            f.write(f"{i:15,d}\n")


def _write_bulk_plaintext(path: Path, length: int) -> None:
    """Write ``length`` deterministic, poorly-compressible bytes, quickly.

    One pseudorandom block is built once and written repeatedly, with a
    block counter patched into its first eight bytes so the content is
    position-dependent rather than a flat repeat.

    Repetition at a 1 MiB period is not something DEFLATE can exploit -- its
    window is 32 KiB -- so the payload stays realistically incompressible
    while costing one ``randbytes`` call instead of one per megabyte.

    Deliberately not ``rng.randbytes(length)`` the way ``fixtures/bench.py``
    does it: that materialises the whole payload in memory, which is fine at
    32 MiB and fatal at 2.1 GiB.
    """
    block = bytearray(random.Random("dspx-4592").randbytes(_BULK_BLOCK))
    view = memoryview(block)
    with path.open("wb") as f:
        written = 0
        while written < length:
            n = min(_BULK_BLOCK, length - written)
            block[:8] = (written // _BULK_BLOCK).to_bytes(8, "big")
            f.write(view[:n])
            written += n


def _plaintext_of(tmp_dir: Path, size: str) -> Path:
    """Return a plaintext file of the named size, generating it if needed."""
    length = sizes.SIZES[size]
    pt_file = tmp_dir / f"test-plain-{size}.txt"
    # tmp_dir persists between runs, so a multi-GiB payload that is already
    # there and the right length is reused rather than rewritten. Checking
    # the length matters: a run killed mid-generation leaves a short file,
    # and silently encrypting that would test the wrong size.
    if pt_file.is_file() and pt_file.stat().st_size == length:
        return pt_file
    if length >= _BULK_THRESHOLD:
        _write_bulk_plaintext(pt_file, length)
    else:
        _write_line_plaintext(pt_file, length)
    return pt_file


@pytest.fixture(scope="session")
def pt_file(tmp_dir: Path, size: str) -> Path:
    """Generate a plaintext test file of the named size.

    Args:
        tmp_dir: Temporary directory for test files
        size: a key of :data:`sizes.SIZES` -- 'small' (128 bytes),
            'chunky' (5 MiB, several default-sized segments),
            'medium' (2.1 GiB, inside the ZIP64 broken window), or
            'large' (5 GiB, above it)

    Returns:
        Path to the generated plaintext file
    """
    return _plaintext_of(tmp_dir, size)


@pytest.fixture(scope="session")
def chunky_pt_file(tmp_dir: Path) -> Path:
    """A 5 MiB plaintext: several segments, every one of them default-sized.

    Independent of ``--sizes`` on purpose. Adding 'chunky' to the session's
    sizes would fan out every test that takes :func:`pt_file` -- the whole of
    test_tdfs.py and test_policytypes.py -- to pay for a property one test
    needs. A separate fixture buys the coverage for one extra encrypt and
    decrypt of 5 MiB, which is cheap enough for the PR gate.
    """
    return _plaintext_of(tmp_dir, "chunky")


@pytest.fixture(scope="session")
def tmp_dir(request: pytest.FixtureRequest) -> Path:
    """Create worker-specific temporary directory for test files.

    When running with pytest-xdist, each worker gets its own subdirectory
    to prevent file collisions between parallel test processes.

    ``XT_TMP_DIR`` relocates the root. Multi-GiB roundtrips need more space
    than a CI runner's workspace volume has, and the alternative to an
    override is hard-coding a runner-specific path here.
    """
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    root = Path(os.environ.get("XT_TMP_DIR", "tmp"))
    dname = root / worker_id
    dname.mkdir(parents=True, exist_ok=True)
    return dname


def load_otdfctl() -> OpentdfCommandLineTool:
    """Load the otdfctl CLI tool from the SDK distribution.

    Attempts to load otdfctl in this order:
    1. First head version from OTDFCTL_HEADS environment variable
    2. Main branch version (sdk/go/dist/main/otdfctl.sh)
    3. System-installed otdfctl

    Returns:
        OpentdfCommandLineTool instance configured for the available otdfctl
    """
    oh = os.environ.get("OTDFCTL_HEADS", "[]")
    try:
        heads = json.loads(oh)
        if heads:
            return OpentdfCommandLineTool(f"sdk/go/dist/{heads[0]}/otdfctl.sh")
    except json.JSONDecodeError:
        print(f"Invalid OTDFCTL_HEADS environment variable: [{oh}]")
    if os.path.isfile("sdk/go/dist/main/otdfctl.sh"):
        return OpentdfCommandLineTool("sdk/go/dist/main/otdfctl.sh")
    return OpentdfCommandLineTool()


_otdfctl = load_otdfctl()


@pytest.fixture(scope="module")
def otdfctl():
    """Provide access to the otdfctl CLI tool."""
    return _otdfctl
