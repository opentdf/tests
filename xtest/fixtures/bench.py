"""Fixtures for the SDK performance regression benchmarks.

The experiment matrix, the payload files, the arm selection, and the shared
time budget all live here. The measurement loop itself is in ``perf/runner.py``
and the statistics in ``perf/stats.py``; this module is the glue that turns
pytest's world (options, fixtures, SDK discovery) into the runner's world
(K arms and a config).
"""

from __future__ import annotations

import json
import os
import platform
import random
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import abac
import tdfs
from perf import report
from perf.cells import BenchCell, Payload, parse_payloads, payloads_to_generate
from perf.runner import Arm, BenchConfig, Budget, Invocation

#: Most builds one run can compare. The ceiling comes from
#: ``xtest/setup-cli-tool/action.yaml``, which installs into four fixed slots
#: (a/b/c/d) and refuses a fifth. Raising it here without raising it there
#: gives a run that resolves five refs and then measures four of them.
MAX_ARMS = 4


class ArmSelectionError(Exception):
    """The builds a comparison needs are not all installed."""


def parse_refs(spec: str) -> tuple[str, ...]:
    """Split a ``--bench-refs`` value into build specs, first = reference.

    Commas or whitespace, so both the shell-friendly
    ``go@main,go@my-branch`` and a quoted space-separated list work.

    Raises:
        ValueError: if the result is not between 2 and :data:`MAX_ARMS`
            entries, or if a build is named twice.
    """
    refs = tuple(p for p in re.split(r"[,\s]+", spec.strip()) if p)
    if not 2 <= len(refs) <= MAX_ARMS:
        raise ValueError(
            f"need 2 to {MAX_ARMS} refs, got {len(refs)}: {spec!r}. The first "
            "is the reference every gated contrast is taken against."
        )
    if len(set(refs)) != len(refs):
        # Two arms running the same build is what the A/A control cell is for,
        # and it is added automatically. Asking for it here would spend a slot
        # measuring a comparison the run already makes.
        raise ValueError(f"duplicate refs in {spec!r}; each arm needs a distinct build")
    return refs


def select_arms(
    sdk: str,
    specs: Sequence[str] | None = None,
) -> tuple[tdfs.SDK, ...]:
    """Pick the builds to compare for one SDK, reference first.

    With no specs the run is the nightly two-arm comparison: the reference is
    the newest installed final release and the candidate is the branch build
    (``main``), which is exactly what the CI setup action lays down side by
    side. Explicit specs name the arms instead, for reproducing a comparison,
    pinning a specific release, or running a bake-off between several
    candidates.

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
    else:
        heads = [s for s in installed if not s.is_released()]
        if not heads:
            raise ArmSelectionError(
                f"no unreleased {sdk} build to test; installed: "
                f"{', '.join(sorted(s.version for s in installed))}"
            )
        # Prefer 'main' when several branch builds are present.
        candidate = next((s for s in heads if s.version == "main"), heads[0])
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
        arms = (max(releases, key=lambda s: s.semver() or (0, 0, 0)), candidate)

    if len(set(arms)) != len(arms):
        names = ", ".join(str(a) for a in arms)
        raise ArmSelectionError(f"arms resolved to the same build: {names}")
    return arms


# --- Session-scoped configuration -------------------------------------------


def arm_specs_from_options(config: pytest.Config) -> tuple[str, ...] | None:
    """The run's build specs, reference first, or None for the default pair.

    ``--bench-refs`` is the K-arm form. ``--bench-baseline`` /
    ``--bench-candidate`` are the two-arm shorthand it grew out of; they are
    still accepted because the shape reads better for the common case, but
    mixing the two forms is an error rather than a merge -- there is no
    reading of ``--bench-refs a,b --bench-candidate c`` that is not a mistake.
    """
    refs = cast(str | None, config.getoption("--bench-refs"))
    baseline = cast(str | None, config.getoption("--bench-baseline"))
    candidate = cast(str | None, config.getoption("--bench-candidate"))
    if refs and (baseline or candidate):
        raise pytest.UsageError(
            "--bench-refs cannot be combined with --bench-baseline or "
            "--bench-candidate; --bench-refs supersedes both"
        )
    if refs:
        try:
            return parse_refs(refs)
        except ValueError as e:
            raise pytest.UsageError(f"invalid --bench-refs: {e}") from e
    if baseline and candidate:
        return (baseline, candidate)
    if baseline or candidate:
        # Half a pair cannot be resolved: the unnamed side would fall back to
        # a default chosen for a different question, and nothing in the report
        # would say the comparison was not the one that was asked for.
        raise pytest.UsageError(
            "--bench-baseline and --bench-candidate must be given together"
        )
    return None


def arm_count(config: pytest.Config) -> int:
    """How many arms this run will measure per cell."""
    specs = arm_specs_from_options(config)
    return len(specs) if specs else 2


def config_from_options(config: pytest.Config) -> BenchConfig:
    """Build a :class:`BenchConfig` from the ``--bench-*`` options.

    Every option except the budget has a default, so ``getoption`` never
    returns None here; the casts are for the type checker, which cannot see
    the parser setup.
    """

    def as_int(name: str) -> int:
        return int(cast(int, config.getoption(name)))

    budget = cast(float | None, config.getoption("--bench-budget-seconds"))
    try:
        return BenchConfig(
            min_rounds=as_int("--bench-min-rounds"),
            max_rounds=as_int("--bench-max-rounds"),
            warmup=as_int("--bench-warmup"),
            budget_seconds=(
                float(budget)
                if budget is not None
                else default_budget_seconds(arm_count(config))
            ),
            seed=as_int("--bench-seed"),
            threshold=float(cast(float, config.getoption("--bench-threshold"))),
        )
    except ValueError as e:
        raise pytest.UsageError(f"invalid benchmark options: {e}") from e


def default_budget_seconds(n_arms: int) -> float:
    """The default time allowance for a K-arm run.

    A round costs one invocation per arm, so at a fixed budget the attained
    round count falls as ``2/K`` and every interval widens as ``sqrt(K/2)``.
    Scaling the default by ``K/2`` keeps a three-arm run about as precise as
    the two-arm run the number was chosen for, instead of quietly trading
    precision for arms and reporting the difference as INCONCLUSIVE.

    An explicit ``--bench-budget-seconds`` is taken as given; someone who
    named a number has already decided what they are willing to spend.
    """
    # `BenchConfig` has slots, so the class attribute is a slot descriptor
    # rather than the default; an instance is how you read one back.
    return BenchConfig().budget_seconds * n_arms / 2


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
#: draws a 32-bit word at a time, so chunking on a 4-byte boundary yields the
#: same stream as one call for the whole payload, and the promise below --
#: that a given seed and label always produce the same bytes -- survives both
#: this constant changing and a payload growing past it.
_CHUNK_BYTES = 8 * 2**20

#: Free space a run keeps in hand beyond its payload arithmetic, for the
#: platform's own logs and database growth over a long benchmark.
_DISK_HEADROOM_BYTES = 2**30


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
    tmp_dir: Path, payloads: Sequence[Payload], n_arms: int = 2
) -> str | None:
    """Return why ``payloads`` will not fit in ``tmp_dir``, or None.

    Checked up front because the alternative is finding out mid-run: ENOSPC
    reaches the harness as a non-zero exit from the CLI under measurement,
    which is reported as a failed measurement of that build. A run can lose
    an hour before anyone notices the disk was the problem, and the report
    points at the wrong thing while they look.

    The estimate is the plaintexts, plus a cached ciphertext for each (the
    decrypt cells share one per size), plus one live output per arm in the
    largest cell. Outputs are deleted as each cell finishes, so only one
    cell's worth is ever live -- but that cell holds K of them, not two, and
    at 1 GiB payloads the difference between K and 2 is the whole margin on a
    GitHub runner.
    """
    total = sum(p.n_bytes for p in payloads)
    largest = max(p.n_bytes for p in payloads)
    need = 2 * total + n_arms * largest + _DISK_HEADROOM_BYTES
    free = shutil.disk_usage(tmp_dir).free
    if free >= need:
        return None
    gib = 2**30
    sizes = ", ".join(p.label for p in payloads)
    return (
        f"payloads {sizes} need about {need / gib:.1f} GiB of scratch space "
        f"in {tmp_dir} but only {free / gib:.1f} GiB is free; drop the largest "
        "size from --bench-payloads or run somewhere with more disk"
    )


@pytest.fixture(scope="session")
def bench_payloads(
    request: pytest.FixtureRequest,
    tmp_dir: Path,
    bench_config: BenchConfig,
    bench_payload_set: tuple[Payload, ...],
) -> dict[str, Path]:
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

    The control's payload is generated whether or not it was selected -- see
    :func:`perf.cells.payloads_to_generate`.
    """
    wanted = payloads_to_generate(bench_payload_set)
    shortfall = disk_shortfall(tmp_dir, wanted, arm_count(request.config))
    if shortfall:
        raise pytest.UsageError(shortfall)
    out: dict[str, Path] = {}
    for payload in wanted:
        path = tmp_dir / f"bench-plain-{payload.label}.bin"
        if not path.is_file() or path.stat().st_size != payload.n_bytes:
            write_payload(path, payload, bench_config.seed)
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
        """The build every gated contrast is taken against."""
        return self.arms[0]

    @property
    def candidates(self) -> tuple[tdfs.SDK, ...]:
        """Everything else -- one arm in a regression run, more in a bake-off."""
        return self.arms[1:]


class ArmResolver:
    """Resolves and memoizes the builds to compare, per SDK.

    Resolution is lazy so that a missing build skips one SDK's cells with a
    readable reason instead of erroring out every cell in the module.
    """

    def __init__(self, specs: Sequence[str] | None) -> None:
        self._specs = tuple(specs) if specs else None
        self._cache: dict[str, BenchArms] = {}

    def __call__(self, sdk: str) -> BenchArms:
        cached = self._cache.get(sdk)
        if cached is None:
            cached = self._cache[sdk] = BenchArms(
                select_arms(sdk, _specs_for(self._specs, sdk))
            )
        return cached


@pytest.fixture(scope="module")
def bench_arms(request: pytest.FixtureRequest) -> ArmResolver:
    """Resolver for the arms of any SDK in the run, reference first."""
    return ArmResolver(arm_specs_from_options(request.config))


def _specs_for(specs: Sequence[str] | None, sdk: str) -> tuple[str, ...] | None:
    """Return ``specs`` only if they name this SDK, so one flag covers a run.

    A run that measures several SDKs but names arms for one of them lets the
    others fall back to their default pair. Specs that name a *mix* of SDKs
    are an error: the arms of a cell are all one SDK by construction, so there
    is nothing a mixed list could mean.
    """
    if not specs:
        return None
    named = tuple(s for s in specs if s.split("@", 1)[0] == sdk)
    if not named:
        return None
    if len(named) != len(specs):
        raise ArmSelectionError(
            f"benchmark refs name more than one SDK ({', '.join(specs)}); "
            "the arms of a comparison must all be builds of the same SDK"
        )
    return named


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

    Every arm is checked against the reference rather than only pairwise
    neighbours: the reference is what all the gated contrasts are taken
    against, so a candidate that disagrees with it invalidates its own gate
    whatever the other candidates do.
    """
    for feature in _COMPARABILITY_FEATURES:
        ref_has = arms.reference.supports(feature)
        for arm in arms.candidates:
            if arm.supports(feature) == ref_has:
                continue
            supporter, other = (
                (arm, arms.reference)
                if not ref_has
                else (
                    arms.reference,
                    arm,
                )
            )
            return (
                f"{supporter} supports [{feature}] and {other} does not, so the "
                "two arms would not be doing the same work"
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
    measure. It is built with as many arms as the real cells have rather than
    a cheap pair, because in a K-arm round the last arm runs K-1 invocations
    after the first and carries more drift than an adjacent pair does; a
    two-arm control would understate the noise of the contrasts being judged.
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
    metadata: dict[str, object] = {
        "sdk": os.environ.get("BENCH_SDK", ""),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "runner_os": os.environ.get("RUNNER_OS", ""),
        "runner_arch": os.environ.get("RUNNER_ARCH", ""),
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "github_run_url": _github_run_url(),
        "platform_version": _platform_version(),
        "seed": config.getoption("--bench-seed"),
    }
    sources, warning = _arm_sources()
    metadata["arm_sources"] = sources
    if warning:
        metadata["arm_sources_warning"] = warning
    return metadata


def _github_run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not (server and repository and run_id):
        return ""
    return f"{server}/{repository}/actions/runs/{run_id}"


def _arm_sources() -> tuple[list[dict[str, object]], str]:
    """Resolver metadata for the builds, enriched with their GitHub repository.

    CI already paid to resolve every ref to an immutable SHA before installing
    it. Carry that result into the benchmark rather than trying to infer a PR,
    release, or branch from the flattened dist-directory name afterward.
    """
    raw = os.environ.get("BENCH_VERSION_INFO", "").strip()
    if not raw:
        return [], ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"BENCH_VERSION_INFO was not valid JSON: {e}"
    if not isinstance(parsed, list) or not all(isinstance(v, dict) for v in parsed):
        return [], "BENCH_VERSION_INFO must be a JSON array of objects"

    sources: list[dict[str, object]] = []
    for value in parsed:
        source = {str(k): v for k, v in value.items()}
        source["repo_url"] = _repo_url_for(source)
        sources.append(source)
    return sources, ""


def _repo_url_for(source: dict[str, object]) -> str:
    sdk = str(source.get("sdk", ""))
    if sdk == "java":
        return "https://github.com/opentdf/java-sdk"
    if sdk == "js":
        return "https://github.com/opentdf/web-sdk"
    if sdk != "go":
        return ""

    # otdfctl moved into the platform monorepo at v0.31.0. Resolver results
    # from there use the namespaced release tag; old standalone releases do
    # not. Branch/PR/SHA builds resolve against platform first.
    release = str(source.get("release", ""))
    if release and not release.startswith("otdfctl/"):
        match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", release)
        if match and tuple(map(int, match.groups())) < (0, 31, 0):
            return "https://github.com/opentdf/otdfctl"
    return "https://github.com/opentdf/platform"


def _platform_version() -> str:
    try:
        return tdfs.get_platform_features().version or "unknown"
    except Exception:  # pragma: no cover - reporting must not break the run
        return "unknown"
