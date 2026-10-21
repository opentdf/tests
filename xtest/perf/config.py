"""Benchmark option parsing and validation.

Imports no pytest, so the pytest plugin, a local entry point and the CI
adapter can all reach the same rules. That matters because the rules used to
exist in three places at once -- `BenchConfig.__post_init__`, a lazy per-SDK
`select_arms` that turned a typo into a silent skip, and a block of shell in
`xtest.yml` -- and they disagreed. A benchmark whose configuration is only
half-checked produces numbers, not evidence, so the checks run eagerly here
rather than at fixture-setup time.

`BenchConfig` lives here, not in `runner`, for the same reason: `runner` is
the round loop and imports numpy and the measurement stack, which a CI
argument check has no business pulling in.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from perf.measure import METRICS

# Statistical constants come from their single source of truth. Do not
# redefine them here -- what is validated and what is analysed must agree.
from perf.stats import (
    DEFAULT_ALPHA,
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_THRESHOLD,
    MIN_USABLE_ROUNDS,
)

#: Benchmark arm-count ceiling. A deliberate limit of the benchmark rather
#: than of any installer: every arm runs once per round, so a fifth arm costs
#: another 25% of every round while each candidate's interval stays as wide as
#: the budget allows. Raise it by changing this one constant.
MAX_ARM_COUNT = 4

#: Default two-sided confidence level, derived from alpha rather than written
#: out, so the interval and the test can never drift apart.
DEFAULT_CONFIDENCE = 1.0 - DEFAULT_ALPHA

#: Per-arm budget that two arms get by default, in seconds.
DEFAULT_BASE_BUDGET_SECONDS = 1500.0

#: Target CI half-width on the log scale, as a fraction of the log threshold.
#: At 1/3, an interval centred on "no change" is comfortably clear of the
#: threshold, so a PASS is a real statement about precision rather than a
#: shrug. Tighter costs rounds superlinearly; looser makes PASS meaningless.
PRECISION_FRACTION = 1 / 3

#: Valid SDK names, mirroring `tdfs.sdk_type`. Duplicated rather than imported
#: because `tdfs` pulls in the whole SDK abstraction layer.
SDK_NAMES = ("go", "java", "js")


@dataclass(frozen=True, slots=True)
class BenchConfig:
    """Knobs for the round loop and the analysis that follows it."""

    min_rounds: int = 20
    max_rounds: int = 60
    warmup: int = 5
    budget_seconds: float = DEFAULT_BASE_BUDGET_SECONDS
    seed: int = 0
    threshold: float = DEFAULT_THRESHOLD
    confidence: float = DEFAULT_CONFIDENCE
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES
    #: Per-invocation timeout. A wedged CLI must not eat the whole job.
    timeout_s: float = 600.0
    #: Metrics whose verdict can fail the build. CPU time is measured and
    #: reported but excluded: it is the noisiest of the three on a shared
    #: runner, and a real CPU regression shows up in wall clock anyway.
    gated_metrics: tuple[str, ...] = ("wall", "rss")

    def __post_init__(self) -> None:
        if self.min_rounds < MIN_USABLE_ROUNDS:
            raise ValueError(
                f"min_rounds must be at least {MIN_USABLE_ROUNDS}, "
                f"below which no verdict is possible"
            )
        if self.max_rounds < self.min_rounds:
            raise ValueError("max_rounds must not be below min_rounds")
        if self.warmup < 0:
            raise ValueError("warmup must not be negative")
        # Non-finite budgets and timeouts are rejected alongside non-positive
        # ones: `inf` disables the guard it configures without saying so.
        if not math.isfinite(self.budget_seconds) or self.budget_seconds <= 0.0:
            raise ValueError("budget_seconds must be a positive, finite number")
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0.0:
            raise ValueError("timeout_s must be a positive, finite number")
        if not math.isfinite(self.threshold) or self.threshold <= 1.0:
            raise ValueError("threshold is a ratio above 1.0, e.g. 1.15 for 15%")
        if not (0.0 < self.confidence < 1.0):
            raise ValueError("confidence must be in (0, 1)")
        if self.n_resamples < 1:
            raise ValueError("n_resamples must be positive")
        unknown = set(self.gated_metrics) - set(METRICS)
        if unknown:
            raise ValueError(f"unknown gated metrics: {sorted(unknown)}")

    @property
    def target_half_width_log(self) -> float:
        """CI half-width, on the log scale, that ends the round loop."""
        return math.log(self.threshold) * PRECISION_FRACTION


@dataclass(frozen=True, slots=True)
class ArmRequest:
    """One requested SDK build: name plus optional version spec."""

    name: str
    spec: str | None  # "v0.29.0", "main", or None for default resolution

    def __str__(self) -> str:
        return f"{self.name}@{self.spec}" if self.spec else self.name


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    """An ordered list of SDK builds to compare, plus the settings to do it with.

    The first arm is the reference; the rest are candidates measured against
    it. Settings live in `config` rather than being restated as fields here,
    so there is one set of defaults and one set of range checks.
    """

    arms: tuple[ArmRequest, ...]
    config: BenchConfig = field(default_factory=BenchConfig)
    no_gate: bool = False

    def __post_init__(self) -> None:
        if not self.arms:
            raise ValueError("at least one arm is required")
        if len(self.arms) > MAX_ARM_COUNT:
            raise ValueError(
                f"at most {MAX_ARM_COUNT} arms are supported; got {len(self.arms)}"
            )

        sdk_names = {arm.name for arm in self.arms}
        if len(sdk_names) > 1:
            raise ValueError(f"all arms must use the same SDK; got {sorted(sdk_names)}")
        validate_sdk_name(self.arms[0].name)

        # Two identical arms measure a build against itself under a name that
        # says otherwise; that is what the A/A control cell is for, and it is
        # labelled as such.
        counts = Counter(str(arm) for arm in self.arms)
        dupes = sorted(spec for spec, count in counts.items() if count > 1)
        if dupes:
            raise ValueError(f"duplicate arm request(s): {', '.join(dupes)}")

    @property
    def sdk_name(self) -> str:
        """The SDK every arm uses."""
        return self.arms[0].name

    @property
    def reference(self) -> ArmRequest:
        """The first arm, which every candidate is compared against."""
        return self.arms[0]

    @property
    def candidates(self) -> tuple[ArmRequest, ...]:
        """Every arm after the reference."""
        return self.arms[1:]


def parse_arm_spec(spec: str) -> ArmRequest:
    """Parse one `sdk` or `sdk@version` request."""
    name, sep, version = spec.partition("@")
    if sep and not version:
        raise ValueError(
            f"empty version in SDK specifier {spec!r}; use e.g. go@main, go@v0.18.0, go@*"
        )
    return ArmRequest(name=name, spec=version or None)


def parse_refs(spec: str) -> tuple[ArmRequest, ...]:
    """Parse a `--bench-refs` value into an ordered request, reference first.

    Commas or whitespace separate the builds, so both the shell-friendly
    ``go@main,go@my-branch`` and a quoted space-separated list work. The
    result is validated by :class:`BenchmarkRequest` as well: 2 to
    :data:`MAX_ARM_COUNT` builds of one known SDK, none named twice.
    """
    arms = tuple(parse_arm_spec(p) for p in re.split(r"[,\s]+", spec.strip()) if p)
    if len(arms) < 2:
        raise ValueError(
            f"need 2 to {MAX_ARM_COUNT} refs, got {len(arms)}: {spec!r}. The "
            "first is the reference every candidate is compared against."
        )
    BenchmarkRequest(arms=arms)
    return arms


def requested_arms(
    refs: str | None, baseline_spec: str | None, candidate_spec: str | None
) -> tuple[ArmRequest, ...]:
    """The run's ordered arm request from whichever option form was used.

    `--bench-refs` is the general form; `--bench-baseline` and
    `--bench-candidate` are the two-arm adapter onto the same request. Mixing
    them is an error rather than a merge -- there is no reading of
    ``--bench-refs a,b --bench-candidate c`` that is not a mistake. Returns an
    empty tuple when no arms were named, which leaves arm selection to its
    defaults.
    """
    if refs is not None and (baseline_spec is not None or candidate_spec is not None):
        raise ValueError(
            "--bench-refs cannot be combined with --bench-baseline or "
            "--bench-candidate; it supersedes both"
        )
    if refs is not None:
        return parse_refs(refs)
    return normalize_baseline_candidate(baseline_spec, candidate_spec)


def normalize_baseline_candidate(
    baseline_spec: str | None, candidate_spec: str | None
) -> tuple[ArmRequest, ...]:
    """Turn the `--bench-baseline`/`--bench-candidate` pair into an ordered request.

    The baseline is the reference. Returns an empty tuple when neither option
    is given, which leaves arm selection to its own defaults; one without the
    other is an error rather than a half-specified comparison.
    """
    if baseline_spec is None and candidate_spec is None:
        return ()
    if baseline_spec is None or candidate_spec is None:
        given = baseline_spec or candidate_spec
        raise ValueError(
            "both --bench-baseline and --bench-candidate are required, or "
            f"neither; got only {given}"
        )

    arms = (parse_arm_spec(baseline_spec), parse_arm_spec(candidate_spec))
    sdk_names = {arm.name for arm in arms}
    if len(sdk_names) > 1:
        raise ValueError(
            f"baseline and candidate must use the same SDK; got {sorted(sdk_names)}"
        )
    return arms


def validate_sdk_name(name: str) -> None:
    """Reject anything that is not a known SDK.

    Arm selection used to skip an unknown name, so a typo produced a green run
    that measured nothing.
    """
    if name not in SDK_NAMES:
        raise ValueError(f"unknown SDK {name!r}; valid choices are {sorted(SDK_NAMES)}")


def default_budget_for_arm_count(
    arm_count: int, base_budget: float = DEFAULT_BASE_BUDGET_SECONDS
) -> float:
    """Scale the default budget by `arm_count / 2`.

    A round costs one invocation per arm, so K arms cost K/2 what two arms do.
    An explicit `--bench-budget-seconds` overrides this.
    """
    if arm_count < 2:
        raise ValueError(f"arm_count must be at least 2; got {arm_count}")
    return base_budget * arm_count / 2.0


def budget_seconds(explicit: float | None, arm_count: int) -> float:
    """The run's budget: an explicit one as given, else the scaled default.

    At a fixed budget the attained round count falls as ``2/K`` and every
    interval widens as ``sqrt(K/2)``; the scaled default buys that back, so a
    three-arm run is about as precise as the two-arm run the number was chosen
    for. Someone who named a number has already decided what to spend.
    """
    if explicit is not None:
        return explicit
    return default_budget_for_arm_count(arm_count)
