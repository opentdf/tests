"""Fixtures for the SDK performance regression benchmarks.

The experiment matrix, the payload files, the arm selection, and the shared
time budget all live here. The measurement loop itself is in ``perf/runner.py``
and the statistics in ``perf/stats.py``; this module is the glue that turns
pytest's world (options, fixtures, SDK discovery) into the runner's world
(two arms and a config).
"""

from __future__ import annotations

import os
import platform
import random
import shutil
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import abac
import tdfs
from perf import report
from perf.cells import BenchCell, Payload, parse_payloads, payloads_to_generate
from perf.runner import Arm, BenchConfig, Budget, Invocation


class ArmSelectionError(Exception):
    """The two builds a comparison needs are not both installed."""


def select_arms(
    sdk: str,
    *,
    baseline_spec: str | None = None,
    candidate_spec: str | None = None,
) -> tuple[tdfs.SDK, tdfs.SDK]:
    """Pick (baseline, candidate) builds for one SDK.

    By default the candidate is the branch build (``main``) and the baseline
    is the newest installed release, which is exactly what the CI setup action
    lays down side by side. Explicit specs override either side, for
    reproducing a comparison or for pinning a specific release.

    Raises:
        ArmSelectionError: if either side is missing or the two resolve to the
            same build (a comparison of a build against itself is only
            meaningful as the explicit A/A control).
    """
    installed = tdfs.all_versions_of(sdk)  # pyright: ignore[reportArgumentType]
    if not installed:
        raise ArmSelectionError(f"no {sdk} builds installed under sdk/{sdk}/dist/")

    def resolve(spec: str, role: str) -> tdfs.SDK:
        try:
            matches = tdfs.parse_sdk_spec(spec)
        except (FileNotFoundError, ValueError) as e:
            raise ArmSelectionError(f"{role} {spec!r}: {e}") from e
        if len(matches) != 1:
            raise ArmSelectionError(
                f"{role} {spec!r} resolved to {len(matches)} builds; "
                "name one exactly, e.g. go@v0.29.0"
            )
        return matches[0]

    if candidate_spec:
        candidate = resolve(candidate_spec, "candidate")
    else:
        heads = [s for s in installed if not s.is_released()]
        if not heads:
            raise ArmSelectionError(
                f"no unreleased {sdk} build to test; installed: "
                f"{', '.join(sorted(s.version for s in installed))}"
            )
        # Prefer 'main' when several branch builds are present.
        candidate = next((s for s in heads if s.version == "main"), heads[0])

    if baseline_spec:
        baseline = resolve(baseline_spec, "baseline")
    else:
        # Final releases only. A release candidate parses to the same semver
        # as its final release, so including them leaves `max` breaking a tie
        # on whatever order the directory listing happened to produce -- and a
        # baseline that is silently an rc is a baseline nobody chose.
        releases = [s for s in installed if s.is_final_release()]
        if not releases:
            raise ArmSelectionError(
                f"no final {sdk} release to compare against (prereleases do "
                f"not count); installed: "
                f"{', '.join(sorted(s.version for s in installed))}"
            )
        baseline = max(releases, key=lambda s: s.semver() or (0, 0, 0))

    if baseline == candidate:
        raise ArmSelectionError(
            f"baseline and candidate are both {baseline}; nothing to compare"
        )
    return baseline, candidate


# --- Session-scoped configuration -------------------------------------------


def config_from_options(config: pytest.Config) -> BenchConfig:
    """Build a :class:`BenchConfig` from the ``--bench-*`` options.

    Every option has a default, so ``getoption`` never returns None here; the
    casts are for the type checker, which cannot see the parser setup.
    """

    def as_int(name: str) -> int:
        return int(cast(int, config.getoption(name)))

    def as_float(name: str) -> float:
        return float(cast(float, config.getoption(name)))

    try:
        return BenchConfig(
            min_rounds=as_int("--bench-min-rounds"),
            max_rounds=as_int("--bench-max-rounds"),
            warmup=as_int("--bench-warmup"),
            budget_seconds=as_float("--bench-budget-seconds"),
            seed=as_int("--bench-seed"),
            threshold=as_float("--bench-threshold"),
        )
    except ValueError as e:
        raise pytest.UsageError(f"invalid benchmark options: {e}") from e


@pytest.fixture(scope="session")
def bench_config(request: pytest.FixtureRequest) -> BenchConfig:
    """Round-loop and analysis settings, from the --bench-* options."""
    return config_from_options(request.config)


def payloads_from_options(config: pytest.Config) -> tuple[Payload, ...]:
    """The run's payload set, from ``--bench-payloads``."""
    spec = cast(str, config.getoption("--bench-payloads"))
    try:
        return parse_payloads(spec)
    except ValueError as e:
        raise pytest.UsageError(f"invalid --bench-payloads: {e}") from e


@pytest.fixture(scope="session")
def bench_payload_set(request: pytest.FixtureRequest) -> tuple[Payload, ...]:
    """Payload sizes this run measures, from --bench-payloads."""
    return payloads_from_options(request.config)


#: Bytes generated per ``randbytes`` call. Must stay a multiple of 4: CPython
#: builds ``randbytes(n)`` from 32-bit words, so chunks on a 4-byte boundary
#: concatenate to exactly the bytes of one ``randbytes(n_bytes)`` call, short
#: final chunk included. That keeps the promise in :func:`bench_payloads` --
#: a given seed and label always produce the same bytes -- independent of
#: this constant, and keeps files cached before chunking valid. It rests on a
#: CPython implementation detail; ``test_bench_arms`` is what enforces it.
_CHUNK_BYTES = 8 * 2**20

#: Free space a run keeps in hand beyond its payload arithmetic, for the
#: platform's own logs and database growth over a long benchmark.
_DISK_HEADROOM_BYTES = 2**30

#: Free space below which a failed cell is blamed on the disk. A CLI that hits
#: ENOSPC has filled the volume to within a few blocks by the time it exits,
#: so this only has to be well clear of zero.
_DISK_FULL_BYTES = 64 * 2**20


def write_payload(path: Path, payload: Payload, seed: int) -> None:
    """Write one payload file, in chunks so a 1 GiB file is not built in RAM."""
    rng = random.Random(f"{seed}:{payload.label}")
    remaining = payload.n_bytes
    with path.open("wb") as f:
        while remaining > 0:
            n = min(remaining, _CHUNK_BYTES)
            f.write(rng.randbytes(n))
            remaining -= n


def disk_shortfall(
    tmp_dir: Path,
    payloads: Sequence[Payload],
    *,
    n_sdks: int,
    prune: bool,
    n_arms: int = 2,
) -> str | None:
    """Return why ``payloads`` will not fit in ``tmp_dir``, or None.

    Checked up front because the alternative is finding out mid-run: ENOSPC
    reaches the harness as a non-zero exit from the CLI under measurement,
    which is reported as a failed measurement of that build. A run can lose
    an hour before anyone notices the disk was the problem, and the report
    points at the wrong thing while they look.

    Every plaintext counts as live for the whole run. On top of that:

    - With ``prune`` (see :class:`Scratch`), a cell's outputs and ciphertext
      are deleted as it ends, so one cell's worth is live at a time: at most
      the largest decrypt cell's ciphertext plus one output per arm.
    - Without it nothing is deleted. Each SDK leaves a baseline-made
      ciphertext per size and one output per arm from every cell, so the
      total grows with the number of SDKs.

    A coarse bound, deliberately. It does not credit files an earlier run
    left in ``tmp_dir``, which this run would reuse or overwrite but which
    already count against free space; DSPX-5253 tracks doing better.
    ``n_arms`` is a parameter so the bound stays right once a run compares
    more than two builds.
    """
    total = sum(p.n_bytes for p in payloads)
    if prune:
        need = total + (1 + n_arms) * max(p.n_bytes for p in payloads)
    else:
        need = total + n_sdks * (1 + 2 * n_arms) * total
    need += _DISK_HEADROOM_BYTES
    # tmp_dir may not exist yet; measure the volume that will hold it.
    probe = tmp_dir
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free >= need:
        return None
    gib = 2**30
    sizes = ", ".join(p.label for p in payloads)
    remedies = [
        "drop the largest size from --bench-payloads",
        "point XT_TMP_DIR at a larger volume",
        "delete the bench-* files an earlier run left there",
    ]
    if not prune:
        remedies.insert(0, "pass --bench-prune-scratch")
    return (
        f"payloads {sizes} need about {need / gib:.1f} GiB of scratch space "
        f"in {tmp_dir} but only {free / gib:.1f} GiB is free; "
        f"{', '.join(remedies[:-1])}, or {remedies[-1]}"
    )


def disk_exhausted(tmp_dir: Path) -> str | None:
    """Return why a cell that just failed is the scratch disk's fault, or None.

    ENOSPC reaches the harness as a non-zero exit from the CLI being
    measured, which would otherwise be reported as a failure of that build --
    and the cells after it, no smaller, would fail the same way, burying the
    cause under a column of failures that each blame a build.
    """
    free = shutil.disk_usage(tmp_dir).free
    if free >= _DISK_FULL_BYTES:
        return None
    return (
        f"the scratch disk filled up ({free / 2**20:.0f} MiB left in {tmp_dir}), "
        "so this failure says nothing about the build; free some space, point "
        "XT_TMP_DIR at a larger volume, pass --bench-prune-scratch, or drop "
        "the largest size from --bench-payloads"
    )


@pytest.fixture(scope="session")
def bench_payloads(
    tmp_dir: Path,
    bench_config: BenchConfig,
    bench_payload_set: tuple[Payload, ...],
) -> dict[str, Path]:
    """Generate one plaintext file per payload size, shared by both arms.

    Content is pseudo-random but seeded, so a rerun measures byte-identical
    input. Random rather than repetitive because compressible input would let
    an SDK that happens to compress look faster for reasons unrelated to the
    crypto path.

    One RNG per payload rather than one stream shared across them: ``tmp_dir``
    persists between runs, so a partially cached set skips some ``randbytes``
    calls and shifts the stream for every payload after it. Deriving each
    payload's bytes from the seed *and* its label keeps the promise above true
    whether the cache is empty, full, or half there.

    The control's payload is generated whether or not it was selected -- see
    :func:`perf.cells.payloads_to_generate`. Whether they all fit was checked
    in ``pytest_configure``, before the session started.
    """
    out: dict[str, Path] = {}
    for payload in payloads_to_generate(bench_payload_set):
        path = tmp_dir / f"bench-plain-{payload.label}.bin"
        if not path.is_file() or path.stat().st_size != payload.n_bytes:
            write_payload(path, payload, bench_config.seed)
        out[payload.label] = path
    return out


class Scratch:
    """Deletes each benchmark file once no remaining cell needs it, if asked.

    Off unless ``--bench-prune-scratch``: a local run keeps its outputs to
    inspect and its plaintexts to reuse next time. CI turns it on because a
    fresh runner gains from neither, and keeping everything leaves about six
    times the payload total on disk by the end of the run.

    A cell's own files -- its outputs and, for decrypt, its ciphertext -- go
    when it ends, however it ends. A plaintext goes when the last cell of its
    size has ended, which, with each size's cells adjacent (see
    :func:`perf.cells.cells_for`), is as soon as that size is done.
    """

    def __init__(
        self,
        plaintexts: dict[str, Path],
        cells: Sequence[BenchCell],
        *,
        prune: bool,
    ) -> None:
        self.prune = prune
        self._plaintexts = plaintexts
        # Ids rather than a count, so a cell that ends twice cannot release a
        # plaintext early. A deselected cell never ends, which only keeps its
        # plaintext -- disk_shortfall already counts every plaintext as live.
        self._pending: dict[str, set[str]] = {}
        for cell in cells:
            self._pending.setdefault(cell.payload.label, set()).add(cell.id)

    def release(self, cell: BenchCell, files: Iterable[Path]) -> None:
        """Delete ``cell``'s own files, and its plaintext if nothing else reads it."""
        if not self.prune:
            return
        for path in files:
            path.unlink(missing_ok=True)
        pending = self._pending.get(cell.payload.label)
        if pending is None:
            return
        pending.discard(cell.id)
        if not pending:
            self._plaintexts[cell.payload.label].unlink(missing_ok=True)


@pytest.fixture(scope="session")
def bench_scratch(
    request: pytest.FixtureRequest, bench_payloads: dict[str, Path]
) -> Scratch:
    """The session's :class:`Scratch`, pruning under --bench-prune-scratch."""
    return Scratch(
        bench_payloads,
        _selected_cells(request.config),
        prune=bool(request.config.getoption("--bench-prune-scratch")),
    )


@pytest.fixture
def bench_cell_files(
    bench_cell: BenchCell, bench_scratch: Scratch
) -> Iterator[list[Path]]:
    """Files the running cell creates, released when it ends however it ends."""
    files: list[Path] = []
    yield files
    bench_scratch.release(bench_cell, files)


@pytest.fixture(scope="session")
def bench_budget(request: pytest.FixtureRequest, bench_config: BenchConfig) -> Budget:
    """One wall-clock allowance shared by every cell in the session.

    Divided evenly as cells start, so a cell that stops early on precision
    donates its unused time to the ones after it instead of leaving the last
    cell starved by whatever the first ones happened to spend.
    """
    n_cells = max(1, len(_selected_cells(request.config)))
    return Budget(bench_config.budget_seconds, n_cells)


@pytest.fixture(scope="session")
def bench_recorder(request: pytest.FixtureRequest) -> report.BenchmarkRecorder:
    """The session-wide collector that the end-of-run gate reads."""
    return report.recorder_for(request.config)


def _selected_cells(config: pytest.Config) -> list[BenchCell]:
    """Cells this session will run, cached on the config by the parametrizer."""
    return config.stash.get(report.CELLS_KEY, [])


# --- Module-scoped experiment inputs ----------------------------------------


@dataclass(frozen=True, slots=True)
class BenchArms:
    baseline: tdfs.SDK
    candidate: tdfs.SDK


class ArmResolver:
    """Resolves and memoizes the two builds to compare, per SDK.

    Resolution is lazy so that a missing build skips one SDK's cells with a
    readable reason instead of erroring out every cell in the module.
    """

    def __init__(self, baseline_spec: str | None, candidate_spec: str | None) -> None:
        self._baseline_spec = baseline_spec
        self._candidate_spec = candidate_spec
        self._cache: dict[str, BenchArms] = {}

    def __call__(self, sdk: str) -> BenchArms:
        cached = self._cache.get(sdk)
        if cached is None:
            baseline, candidate = select_arms(
                sdk,
                baseline_spec=_spec_for(self._baseline_spec, sdk),
                candidate_spec=_spec_for(self._candidate_spec, sdk),
            )
            cached = self._cache[sdk] = BenchArms(baseline, candidate)
        return cached


@pytest.fixture(scope="module")
def bench_arms(request: pytest.FixtureRequest) -> ArmResolver:
    """Resolver for the (baseline, candidate) pair of any SDK in the run."""
    return ArmResolver(
        cast(str | None, request.config.getoption("--bench-baseline")),
        cast(str | None, request.config.getoption("--bench-candidate")),
    )


def _spec_for(spec: str | None, sdk: str) -> str | None:
    """Return ``spec`` only if it names this SDK, so one flag can cover a run."""
    if not spec:
        return None
    return spec if spec.split("@", 1)[0] == sdk else None


#: Features whose presence changes what an encrypt or decrypt actually *does*.
#: If the two arms disagree on one of these they are not performing the same
#: operation, and a timing difference between them is a difference in work,
#: not in speed.
_COMPARABILITY_FEATURES: tuple[tdfs.feature_type, ...] = (
    "hexless",
    "hexaflexible",
    "autoconfigure",
)


def comparability_problem(arms: BenchArms) -> str | None:
    """Return why these two builds cannot be fairly compared, or None."""
    for feature in _COMPARABILITY_FEATURES:
        if arms.baseline.supports(feature) != arms.candidate.supports(feature):
            supporter, other = (
                (arms.baseline, arms.candidate)
                if arms.baseline.supports(feature)
                else (arms.candidate, arms.baseline)
            )
            return (
                f"{supporter} supports [{feature}] and {other} does not, so the "
                "two arms would not be doing the same work"
            )
    return None


def pinned_target_mode(arms: BenchArms) -> tdfs.container_version | None:
    """Pick one container version both arms emit, or None for their default.

    Letting each arm choose its own target would compare two output formats.
    ``None`` is only returned when neither arm can be told which to use, in
    which case :func:`comparability_problem` has already established that they
    agree on the relevant features and will pick the same one.
    """
    if not (
        arms.baseline.supports("hexaflexible")
        and arms.candidate.supports("hexaflexible")
    ):
        return None
    if arms.baseline.supports("hexless") and arms.candidate.supports("hexless"):
        return "4.3.0"
    return "4.2.2"


class CiphertextFactory:
    """Baseline-produced ciphertexts for the decrypt cells, made on demand.

    Both arms of a decrypt comparison must read the *same* file. If each arm
    decrypted its own output, a difference in how the two builds *write* a TDF
    would show up as a difference in how fast they read one.
    """

    def __init__(
        self,
        payloads: dict[str, Path],
        tmp_dir: Path,
        attr_values: list[str],
    ) -> None:
        self._payloads = payloads
        self._tmp_dir = tmp_dir
        self._attr_values = attr_values
        self._cache: dict[tuple[str, str], Path] = {}

    def __call__(self, arms: BenchArms, payload_label: str) -> Path:
        key = (str(arms.baseline), payload_label)
        cached = self._cache.get(key)
        # --bench-prune-scratch deletes a ciphertext once its cell ends.
        if cached is not None and cached.is_file():
            return cached
        ct_file = self._tmp_dir / f"bench-ct-{arms.baseline}-{payload_label}.tdf"
        arms.baseline.encrypt(
            self._payloads[payload_label],
            ct_file,
            container="ztdf",
            attr_values=self._attr_values,
            target_mode=pinned_target_mode(arms),
        )
        assert ct_file.is_file()
        self._cache[key] = ct_file
        return ct_file


@pytest.fixture(scope="module")
def bench_ciphertexts(
    bench_payloads: dict[str, Path],
    tmp_dir: Path,
    attribute_default_rsa: abac.Attribute,
) -> CiphertextFactory:
    """Ciphertext source for decrypt cells.

    Pinned to the explicit RSA attribute so both arms wrap with RSA regardless
    of what base key the platform happens to have configured -- an arm that
    silently switched to EC would look slower for reasons that have nothing to
    do with a regression.
    """
    return CiphertextFactory(bench_payloads, tmp_dir, attribute_default_rsa.value_fqns)


def build_arms(
    cell: BenchCell,
    arms: BenchArms,
    *,
    pt_file: Path,
    ct_file: Path | None,
    tmp_dir: Path,
    attr_values: list[str],
) -> tuple[Arm, ...]:
    """Turn a cell plus its two builds into one ready-to-run invocation each.

    Everything that is not the build under test is pinned identically across
    the arms: same plaintext, same attribute (so both wrap with RSA), same
    container, same target mode. A functional difference between the builds
    that changed any of these would otherwise show up as a speed difference.

    For decrypt, both arms read the *same* ``ct_file``, produced once by the
    baseline. Letting each arm decrypt its own output would compare the cost
    of reading two different files.

    In a control cell both arms are the baseline build, so they differ only in
    the output path -- exactly the harness overhead the A/A cell exists to
    measure.
    """
    target_mode = pinned_target_mode(arms)

    def invocation(sdk: tdfs.SDK, arm_id: str) -> Invocation:
        # Appended, not `with_suffix`: arm ids are versions, and with_suffix
        # would replace the ".0" of "v0.29.0", giving two builds one output.
        stem = f"bench-{cell.id}-{arm_id}"
        if cell.operation == "encrypt":
            out = tmp_dir / f"{stem}.tdf"
            argv, env = sdk.encrypt_command(
                pt_file,
                out,
                container="ztdf",
                attr_values=attr_values,
                target_mode=target_mode,
            )
        else:
            if ct_file is None:
                raise ValueError(f"{cell.id} is a decrypt cell but has no ciphertext")
            out = tmp_dir / f"{stem}.untdf"
            argv, env = sdk.decrypt_command(ct_file, out, container="ztdf")
        return Invocation(argv, env, out)

    if cell.control:
        # The same build twice. The ids have to differ -- they key the sample
        # vectors -- so each is the version plus a copy number: v0.29.0#1.
        builds = [(f"{arms.baseline.version}#{i + 1}", arms.baseline) for i in range(2)]
    else:
        builds = [(sdk.version, sdk) for sdk in (arms.baseline, arms.candidate)]
    return tuple(
        Arm(arm_id, str(sdk), invocation(sdk, arm_id)) for arm_id, sdk in builds
    )


def runner_metadata(config: pytest.Config) -> dict[str, object]:
    """Machine facts worth keeping alongside the numbers.

    Absolute timings are not comparable across runners, which is why nothing
    here feeds the decision rule. It is recorded so that a human reading an
    old artifact can tell what they are looking at.
    """
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "runner_os": os.environ.get("RUNNER_OS", ""),
        "runner_arch": os.environ.get("RUNNER_ARCH", ""),
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "platform_version": _platform_version(),
        "seed": config.getoption("--bench-seed"),
    }


def _platform_version() -> str:
    try:
        return tdfs.get_platform_features().version or "unknown"
    except Exception:  # pragma: no cover - reporting must not break the run
        return "unknown"
