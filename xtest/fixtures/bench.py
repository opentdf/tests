"""Fixtures for the SDK performance regression benchmarks.

The experiment matrix, the payload files, the arm selection, and the shared
time budget all live here. The measurement loop itself is in ``perf/runner.py``
and the statistics in ``perf/stats.py``; this module is the glue that turns
pytest's world (options, fixtures, SDK discovery, the installation manifest)
into the runner's world (2 to 4 arms and a config).
"""

from __future__ import annotations

import os
import platform
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import abac
import tdfs
from perf import installation, report
from perf.cells import PAYLOADS, BenchCell
from perf.config import budget_seconds, requested_arms
from perf.runner import Arm, BenchConfig, Budget, Invocation

#: The run's installation manifest, read once in ``pytest_configure``.
INSTALLATION_KEY: pytest.StashKey[installation.Installation | None] = pytest.StashKey()


class ArmSelectionError(Exception):
    """The builds a comparison needs are not all installed."""


def select_arms(
    sdk: str,
    specs: Sequence[str] | None = None,
    *,
    baseline_spec: str | None = None,
    candidate_spec: str | None = None,
) -> tuple[tdfs.SDK, ...]:
    """Pick the builds to compare for one SDK, reference first.

    ``specs`` names every arm, in order: the reproduction of a recorded
    comparison, or a multi-arm run. Without it the run is the nightly two-arm
    comparison -- the newest installed final release as the reference and the
    branch build (``main``) as the candidate -- and ``baseline_spec`` or
    ``candidate_spec`` may override either side of that pair.

    Raises:
        ArmSelectionError: if any named build is missing, if the default pair
            cannot be found, or if two arms resolve to the same build (a
            comparison of a build against itself is only meaningful as the
            explicit A/A control).
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

    if specs:
        arms = tuple(
            resolve(spec, "reference" if i == 0 else f"arm {i + 1}")
            for i, spec in enumerate(specs)
        )
        if len(set(arms)) != len(arms):
            names = ", ".join(str(a) for a in arms)
            raise ArmSelectionError(f"arms resolved to the same build: {names}")
        return arms

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


def installation_for(config: pytest.Config) -> installation.Installation | None:
    """The manifest this run was prepared with, or None if it was not.

    Read once and kept on the config, so every fixture and the end-of-run
    report see the same record even if the file changes mid-session.
    """
    if INSTALLATION_KEY not in config.stash:
        try:
            config.stash[INSTALLATION_KEY] = installation.from_env()
        except installation.ManifestError as e:
            raise pytest.UsageError(str(e)) from e
    return config.stash[INSTALLATION_KEY]


def arm_specs_from_options(config: pytest.Config) -> tuple[str, ...] | None:
    """The run's ordered arm specs, reference first, or None for the defaults.

    Explicit options win. Without them, a prepared run measures exactly what
    preparation installed, in the order it was requested -- so a local run and
    a CI run that prepared the same request measure the same arms without
    anyone restating them. A manifest that cannot be measured (failed,
    partial, or neutral) yields no specs here; :func:`preparation_problem`
    says why, per SDK.
    """
    refs = cast(str | None, config.getoption("--bench-refs"))
    baseline = cast(str | None, config.getoption("--bench-baseline"))
    candidate = cast(str | None, config.getoption("--bench-candidate"))
    if refs is None and (baseline is None) != (candidate is None):
        # A lone --bench-baseline or --bench-candidate overrides one side of
        # the default pair; `select_arms` defaults the other.
        return None
    try:
        arms = requested_arms(refs, baseline, candidate)
    except ValueError as e:
        raise pytest.UsageError(f"invalid benchmark options: {e}") from e
    if arms:
        return tuple(str(a) for a in arms)
    prepared = installation_for(config)
    if prepared is not None and prepared.usable:
        return prepared.arm_specs()
    return None


def preparation_problem(config: pytest.Config, sdk: str) -> str | None:
    """Why this SDK's prepared arms cannot be measured, or None.

    Only consulted when no arms were named explicitly: an explicit request is
    a statement that the manifest is not what this run should measure.
    """
    if any(
        config.getoption(o) is not None
        for o in ("--bench-refs", "--bench-baseline", "--bench-candidate")
    ):
        return None
    prepared = installation_for(config)
    if prepared is None or prepared.sdk != sdk or prepared.usable:
        return None
    if prepared.neutral:
        return f"neutral preparation: {prepared.status_message}"
    return (
        f"preparation {prepared.status or 'incomplete'}: "
        f"{prepared.status_message or 'fewer than two arms were installed'}"
    )


def preparation_is_neutral(config: pytest.Config) -> bool:
    """True if this run's only prepared arms collapsed onto one commit."""
    prepared = installation_for(config)
    return (
        prepared is not None
        and prepared.neutral
        and arm_specs_from_options(config) is None
    )


def arm_count(config: pytest.Config) -> int:
    """How many arms this run will measure per cell."""
    specs = arm_specs_from_options(config)
    return len(specs) if specs else 2


def config_from_options(config: pytest.Config) -> BenchConfig:
    """Build a :class:`BenchConfig` from the ``--bench-*`` options.

    Every option except the budget has a default, so ``getoption`` never
    returns None for them; the casts are for the type checker, which cannot
    see the parser setup. The budget defaults to one scaled by the arm count.
    """

    def as_int(name: str) -> int:
        return int(cast(int, config.getoption(name)))

    def as_float(name: str) -> float:
        return float(cast(float, config.getoption(name)))

    budget = cast(float | None, config.getoption("--bench-budget-seconds"))
    try:
        return BenchConfig(
            min_rounds=as_int("--bench-min-rounds"),
            max_rounds=as_int("--bench-max-rounds"),
            warmup=as_int("--bench-warmup"),
            budget_seconds=budget_seconds(budget, arm_count(config)),
            seed=as_int("--bench-seed"),
            threshold=as_float("--bench-threshold"),
        )
    except ValueError as e:
        raise pytest.UsageError(f"invalid benchmark options: {e}") from e


@pytest.fixture(scope="session")
def bench_config(request: pytest.FixtureRequest) -> BenchConfig:
    """Round-loop and analysis settings, from the --bench-* options."""
    return config_from_options(request.config)


@pytest.fixture(scope="session")
def bench_payloads(tmp_dir: Path, bench_config: BenchConfig) -> dict[str, Path]:
    """Generate one plaintext file per payload size, shared by every arm.

    Content is pseudo-random but seeded, so a rerun measures byte-identical
    input. Random rather than repetitive because compressible input would let
    an SDK that happens to compress look faster for reasons unrelated to the
    crypto path.

    One RNG per payload rather than one stream shared across them: ``tmp_dir``
    persists between runs, so a partially cached set skips some ``randbytes``
    calls and shifts the stream for every payload after it. Deriving each
    payload's bytes from the seed *and* its label keeps the promise above true
    whether the cache is empty, full, or half there.
    """
    out: dict[str, Path] = {}
    for payload in PAYLOADS:
        path = tmp_dir / f"bench-plain-{payload.label}.bin"
        if not path.is_file() or path.stat().st_size != payload.n_bytes:
            rng = random.Random(f"{bench_config.seed}:{payload.label}")
            path.write_bytes(rng.randbytes(payload.n_bytes))
        out[payload.label] = path
    return out


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
    """The builds one SDK's cells compare, reference first."""

    arms: tuple[tdfs.SDK, ...]

    @property
    def reference(self) -> tdfs.SDK:
        """The build every candidate is compared against."""
        return self.arms[0]

    @property
    def candidates(self) -> tuple[tdfs.SDK, ...]:
        """Every other arm -- one in the nightly comparison, up to three."""
        return self.arms[1:]


class ArmResolver:
    """Resolves and memoizes the builds to compare, per SDK.

    Resolution is lazy so that a missing build skips one SDK's cells with a
    readable reason instead of erroring out every cell in the module.
    """

    def __init__(
        self,
        specs: Sequence[str] | None,
        *,
        baseline_spec: str | None = None,
        candidate_spec: str | None = None,
        problem: dict[str, str | None] | None = None,
    ) -> None:
        self._specs = tuple(specs) if specs else None
        self._baseline_spec = baseline_spec
        self._candidate_spec = candidate_spec
        self._problem = problem or {}
        self._cache: dict[str, BenchArms] = {}

    def __call__(self, sdk: str) -> BenchArms:
        cached = self._cache.get(sdk)
        if cached is None:
            problem = self._problem.get(sdk)
            if problem:
                raise ArmSelectionError(problem)
            cached = self._cache[sdk] = BenchArms(
                select_arms(
                    sdk,
                    _specs_for(self._specs, sdk),
                    baseline_spec=_spec_for(self._baseline_spec, sdk),
                    candidate_spec=_spec_for(self._candidate_spec, sdk),
                )
            )
        return cached


@pytest.fixture(scope="module")
def bench_arms(request: pytest.FixtureRequest) -> ArmResolver:
    """Resolver for the arms of any SDK in the run, reference first."""
    config = request.config
    specs = arm_specs_from_options(config)
    cells = _selected_cells(config)
    return ArmResolver(
        specs,
        baseline_spec=None if specs else config.getoption("--bench-baseline"),
        candidate_spec=None if specs else config.getoption("--bench-candidate"),
        problem={c.sdk: preparation_problem(config, c.sdk) for c in cells},
    )


def _spec_for(spec: str | None, sdk: str) -> str | None:
    """Return ``spec`` only if it names this SDK, so one flag can cover a run."""
    if not spec:
        return None
    return spec if spec.split("@", 1)[0] == sdk else None


def _specs_for(specs: Sequence[str] | None, sdk: str) -> tuple[str, ...] | None:
    """Return ``specs`` only if they name this SDK, so one flag covers a run.

    A run that measures several SDKs but names arms for one of them lets the
    others fall back to their default pair. Validation has already required
    every spec to name the same SDK.
    """
    if not specs or specs[0].split("@", 1)[0] != sdk:
        return None
    return tuple(specs)


#: Features whose presence changes what an encrypt or decrypt actually *does*.
#: If two arms disagree on one of these they are not performing the same
#: operation, and a timing difference between them is a difference in work,
#: not in speed.
_COMPARABILITY_FEATURES: tuple[tdfs.feature_type, ...] = (
    "hexless",
    "hexaflexible",
    "autoconfigure",
)


def comparability_problem(arms: BenchArms) -> str | None:
    """Return why these builds cannot be fairly compared, or None.

    Every candidate is checked against the reference, since the reference is
    what each candidate's contrast is taken against: a candidate that
    disagrees with it invalidates its own comparison whatever the other
    candidates do. Agreement is transitive through the reference, so this
    also establishes that the candidates agree with each other.
    """
    for feature in _COMPARABILITY_FEATURES:
        ref_has = arms.reference.supports(feature)
        for arm in arms.candidates:
            if arm.supports(feature) == ref_has:
                continue
            supporter, other = (
                (arms.reference, arm) if ref_has else (arm, arms.reference)
            )
            return (
                f"{supporter} supports [{feature}] and {other} does not, so the "
                "arms would not be doing the same work"
            )
    return None


def pinned_target_mode(arms: BenchArms) -> tdfs.container_version | None:
    """Pick one container version every arm emits, or None for their default.

    Letting each arm choose its own target would compare output formats.
    ``None`` is only returned when the arms cannot be told which to use, in
    which case :func:`comparability_problem` has already established that they
    agree on the relevant features and will pick the same one.
    """
    if not all(a.supports("hexaflexible") for a in arms.arms):
        return None
    if all(a.supports("hexless") for a in arms.arms):
        return "4.3.0"
    return "4.2.2"


class CiphertextFactory:
    """Reference-produced ciphertexts for the decrypt cells, made on demand.

    Every arm of a decrypt comparison must read the *same* file. If each arm
    decrypted its own output, a difference in how the builds *write* a TDF
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
        reference = arms.reference
        key = (str(reference), payload_label)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        ct_file = self._tmp_dir / f"bench-ct-{reference}-{payload_label}.tdf"
        reference.encrypt(
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

    Pinned to the explicit RSA attribute so every arm wraps with RSA
    regardless of what base key the platform happens to have configured -- an
    arm that silently switched to EC would look slower for reasons that have
    nothing to do with a regression.
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
    """Turn a cell plus its builds into one ready-to-run invocation each.

    Everything that is not the build under test is pinned identically across
    the arms: same plaintext, same attribute (so every arm wraps with RSA),
    same container, same target mode. A functional difference between the
    builds that changed any of these would otherwise show up as a speed
    difference.

    For decrypt, every arm reads the *same* ``ct_file``, produced once by the
    reference. Letting each arm decrypt its own output would compare the cost
    of reading different files.

    In a control cell every arm is the reference build, so they differ only in
    the output path -- exactly the harness overhead the A/A cell exists to
    measure. It has as many arms as the real cells rather than a cheap pair:
    in a K-arm round the last arm runs K-1 invocations after the first and
    carries more drift than an adjacent pair does, and a two-arm control would
    understate the noise of the contrasts being judged.
    """
    target_mode = pinned_target_mode(arms)

    def invocation(sdk: tdfs.SDK, arm_id: str) -> Invocation:
        out = tmp_dir / f"bench-{cell.id}-{arm_id}"
        if cell.operation == "encrypt":
            out = out.with_suffix(".tdf")
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
            out = out.with_suffix(".untdf")
            argv, env = sdk.decrypt_command(ct_file, out, container="ztdf")
        return Invocation(argv, env, out)

    if cell.control:
        # Same build K times. The ids have to differ -- they key the sample
        # vectors -- so they are numbered rather than named after the version.
        builds = [
            (f"{arms.reference.version}#{i + 1}", arms.reference)
            for i in range(len(arms.arms))
        ]
    else:
        builds = [(sdk.version, sdk) for sdk in arms.arms]
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
        **_installation_metadata(config),
    }


def _installation_metadata(config: pytest.Config) -> dict[str, object]:
    """Provenance from the installation manifest, when the run was prepared.

    Carried into the artifact so a result names the commits it measured
    rather than only their dist tags, which a moving branch reuses.
    ``preparation`` is the explicit status a reader checks first: ``neutral``
    means every requested alias named one commit and nothing was compared.
    """
    prepared = installation_for(config)
    if prepared is None:
        return {}
    return {
        "installation": prepared.to_dict(),
        "preparation": "neutral" if preparation_is_neutral(config) else prepared.status,
    }


def _platform_version() -> str:
    try:
        return tdfs.get_platform_features().version or "unknown"
    except Exception:  # pragma: no cover - reporting must not break the run
        return "unknown"
