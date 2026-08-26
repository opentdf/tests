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

import json
import logging
import os
import typing
from pathlib import Path
from typing import cast

import pytest

import tdfs
from fixtures.bench import MAX_ARMS, payloads_from_options
from otdfctl import OpentdfCommandLineTool
from perf import report, stats
from perf.cells import DEFAULT_PAYLOAD_SPEC, cells_for

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


def englist(s: tuple[str]) -> str:
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
        help="generate a large (greater than 4 GiB) file for testing",
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
        "--bench-refs",
        help=f"builds to compare, comma- or space-separated, e.g. "
        f"'go@main,go@my-branch'. The first is the reference: every gated "
        f"contrast is taken against it, and the rest are ranked head-to-head "
        f"as a bake-off. 2 to {MAX_ARMS} entries (the ceiling is how "
        f"many builds setup-cli-tool can install side by side). Defaults to "
        f"the newest installed release against the branch build",
    )
    group.addoption(
        "--bench-baseline",
        help="two-arm shorthand for the reference half of --bench-refs, e.g. "
        "go@v0.29.0; must be given with --bench-candidate",
    )
    group.addoption(
        "--bench-candidate",
        help="two-arm shorthand for the candidate half of --bench-refs, e.g. "
        "go@main; must be given with --bench-baseline",
    )
    group.addoption(
        "--bench-payloads",
        default=DEFAULT_PAYLOAD_SPEC,
        help="comma-separated payload sizes to measure, e.g. "
        "'1KiB,1MiB,32MiB,1GiB' (default: %(default)s). Sizes above the "
        "default are opt-in because they are what a throughput gate actually "
        "needs and what a nightly cannot afford: each one adds two cells, and "
        "a run holds roughly twice the total plus one live output per arm of "
        "the largest on disk",
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
        default=None,
        help="wall-clock allowance shared by every cell. Defaults to "
        "1500s scaled by (arms / 2), because a K-arm round costs K "
        "invocations and holding the same precision costs proportionally "
        "more time",
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
        metafunc.parametrize(
            "size",
            ["large" if metafunc.config.getoption("large") else "small"],
            scope="session",
        )

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
    # --bench-refs instead, so only the name matters here.
    specs = metafunc.config.getoption("--sdks") or " ".join(
        typing.get_args(tdfs.sdk_type)
    )
    names = list(dict.fromkeys(s.split("@", 1)[0] for s in str(specs).split()))
    cells = cells_for(names, payloads_from_options(metafunc.config))
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
    # Resolve the arm specs now so a malformed --bench-refs is a usage error
    # before anything is installed or measured, not an hour into the run.
    from fixtures import bench

    bench.arm_specs_from_options(config)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Drop the benchmark cells entirely unless --bench asked for them.

    Deselected rather than skipped: a 20-minute cell has no business in the
    regular integration matrix, and a skip would report it as a test that
    exists and was declined rather than one that was never in scope.
    """
    if config.getoption("--bench", default=False):
        return
    keep, drop = [], []
    for item in items:
        (drop if item.get_closest_marker("benchmark") else keep).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
        items[:] = keep


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

    artifact_url = (
        report.ARTIFACT_URL_PLACEHOLDER
        if os.environ.get("BENCH_DEFER_SUMMARY", "").lower() in {"1", "true", "yes"}
        else ""
    )
    summary = report.markdown(recorder, bench_config, gate, artifact_url=artifact_url)
    report.write_markdown(out_dir / f"{name}.summary.md", summary)
    if not artifact_url:
        report.append_step_summary(summary)
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "benchmark results")
        reporter.write_line(
            str(recorder.metadata.get("comparison_note", gate.summary))
            if report.same_commit(recorder.metadata)
            else gate.summary
        )
        # Repeated on the terminal as well as in the step summary: "the run
        # was too short for the number of arms you asked for" is the one
        # finding a reader is most likely to mistake for a real result.
        underpowered = report.underpowered_warning(recorder, bench_config, gate)
        if underpowered:
            reporter.write_line(underpowered)
        for bake_off in report.bake_offs(recorder, bench_config, gate):
            reporter.write_line(
                f"{bake_off.cell_id} [{bake_off.metric}]: {bake_off.detail}"
            )
        reporter.write_line(f"raw samples and statistics: {json_path}")

    if config.getoption("--bench-no-gate", default=False):
        return
    # A run that measured nothing fails too, and not only one that found a
    # regression. --bench is an explicit request for a measurement; answering
    # it with a green tick and an empty table is the one outcome nobody
    # inspects, so a benchmark that has quietly stopped measuring can survive
    # indefinitely. The exception is two requested names resolving to one SHA:
    # that is a complete, neutral answer (there is no code difference to test),
    # not a harness that failed to measure an existing difference.
    if gate.should_fail or (
        gate.nothing_measured and not report.same_commit(recorder.metadata)
    ):
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
@pytest.fixture(scope="session")
def pt_file(tmp_dir: Path, size: str) -> Path:
    """Generate a plaintext test file.

    Args:
        tmp_dir: Temporary directory for test files
        size: 'large' (>4 GiB) or 'small' (128 bytes)

    Returns:
        Path to the generated plaintext file
    """
    pt_file = tmp_dir / f"test-plain-{size}.txt"
    length = (5 * 2**30) if size == "large" else 128
    with pt_file.open("w") as f:
        for i in range(0, length, 16):
            f.write(f"{i:15,d}\n")
    return pt_file


@pytest.fixture(scope="session")
def tmp_dir(request: pytest.FixtureRequest) -> Path:
    """Create worker-specific temporary directory for test files.

    When running with pytest-xdist, each worker gets its own subdirectory
    to prevent file collisions between parallel test processes.
    """
    worker_id = getattr(request.config, "workerinput", {}).get("workerid", "master")
    dname = Path(f"tmp/{worker_id}/")
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
