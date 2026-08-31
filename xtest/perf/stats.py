"""Paired statistical comparison of two SDK builds.

Why this shape
--------------
Absolute timings from a GitHub-hosted runner are not comparable across runs:
CPU models vary, tenancy is shared, and steal time is unbounded. Storing a
baseline and diffing against it produces false alarms until people mute the
job. So we never compare across runs. Both builds are measured on the *same*
runner, interleaved in time, and the statistic is the within-round *ratio*.
Runner speed is then a shared factor that divides out.

Everything here is a pure function over sample vectors, so the decision logic
is testable without a platform, an SDK, or a subprocess.

The scale
---------
Comparisons use the log-ratio ``d_i = ln(candidate_i) - ln(baseline_i)`` of the
i-th paired round. Logs make ratios symmetric (a 2x slowdown and a 2x speedup
are equal and opposite) and additive, which is what the median and the
bootstrap want. Results are exponentiated back to ratios for reporting.

The decision rule
-----------------
A cell is a regression iff **both**:

1. the lower bound of the 95% CI on the ratio exceeds ``threshold``, and
2. the Benjamini-Hochberg adjusted one-sided p-value is below ``alpha``.

Requiring both is deliberate, and neither clause is redundant:

- Clause 1 alone would fire on a real-but-trivial effect measured precisely
  enough -- a reproducible 0.5% slowdown is not worth a red build.
  It cannot fire on pure noise, since that would require the interval to
  exclude an effect that is not there.
- Clause 2 alone would fire on noise roughly ``alpha`` of the time per cell,
  and a run has enough cells that "roughly alpha" becomes "most nights".
  BH adjustment across cells controls the false discovery rate.

Together they answer the only question worth gating on: is the slowdown both
real and large enough to care about?
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

import numpy as np
from scipy import stats as _scipy_stats

# Rounds below this cannot support a meaningful interval. The one-sided
# signed-rank test cannot reach p < 0.05 at all below n=5, so anything less is
# reported as INCONCLUSIVE rather than given a verdict.
MIN_USABLE_ROUNDS = 5

#: A vector of per-round measurements for one arm of one cell. Accepts a plain
#: list from the runner or an array from a test's synthetic data generator.
type Samples = Sequence[float] | np.ndarray

DEFAULT_ALPHA = 0.05
DEFAULT_THRESHOLD = 1.15
DEFAULT_BOOTSTRAP_RESAMPLES = 10000


class Verdict(StrEnum):
    """Outcome for a single comparison cell."""

    PASS = "PASS"
    REGRESSION = "REGRESSION"
    IMPROVED = "IMPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class PairedComparison:
    """The statistical summary of one (cell, metric) comparison.

    Ratios are candidate-over-baseline: 1.20 means the candidate took 20%
    longer (or used 20% more memory) than the baseline.
    """

    n_rounds: int
    baseline_median: float
    candidate_median: float
    ratio: float
    ci_low: float
    ci_high: float
    p_value: float
    #: Set by :func:`apply_multiplicity_control` once every cell is known.
    p_adjusted: float | None = None
    verdict: Verdict = Verdict.INCONCLUSIVE
    note: str = ""

    @property
    def ci_half_width_log(self) -> float:
        """Half-width of the CI on the log scale, the run's attained precision."""
        if not (math.isfinite(self.ci_low) and math.isfinite(self.ci_high)):
            return math.inf
        if self.ci_low <= 0 or self.ci_high <= 0:
            return math.inf
        return (math.log(self.ci_high) - math.log(self.ci_low)) / 2


def log_ratios(baseline: Samples, candidate: Samples) -> np.ndarray:
    """Return per-round log-ratios ``ln(candidate) - ln(baseline)``.

    The two vectors must be the same length: entry i of each comes from the
    same round, which is what makes the comparison paired. Non-positive
    measurements cannot be log-transformed and indicate a broken measurement
    rather than a fast one, so they are rejected outright.
    """
    b = np.asarray(baseline, dtype=float)
    c = np.asarray(candidate, dtype=float)
    if b.shape != c.shape:
        raise ValueError(
            f"paired vectors must be the same length, got {b.shape} and {c.shape}"
        )
    if b.size == 0:
        return np.empty(0, dtype=float)
    if not (np.all(np.isfinite(b)) and np.all(np.isfinite(c))):
        raise ValueError("measurements must all be finite")
    if np.any(b <= 0) or np.any(c <= 0):
        raise ValueError("measurements must all be positive to take a log-ratio")
    return np.log(c) - np.log(b)


def _bootstrap_ci(
    d: np.ndarray, *, confidence: float, seed: int, n_resamples: int
) -> tuple[float, float]:
    """Percentile-bootstrap CI on the median log-ratio.

    Returns log-scale bounds. BCa is preferred but degenerates when the
    jackknife acceleration is undefined (every value identical), so fall back
    to the basic percentile method there.
    """
    if np.allclose(d, d[0]):
        # A perfectly constant difference has no sampling variability to
        # estimate; the interval is the point itself.
        return float(d[0]), float(d[0])
    try:
        with warnings.catch_warnings():
            # SciPy announces a degenerate BCa interval (DegenerateDataWarning,
            # a RuntimeWarning) through the warnings machinery and returns NaN
            # bounds rather than raising. Promote it, or the fallback below is
            # only reachable via the isfinite check and every other degenerate
            # case prints a warning nobody reads.
            warnings.simplefilter("error", RuntimeWarning)
            res = _scipy_stats.bootstrap(
                (d,),
                np.median,
                confidence_level=confidence,
                method="BCa",
                n_resamples=n_resamples,
                rng=np.random.default_rng(seed),
            )
        low = float(res.confidence_interval.low)
        high = float(res.confidence_interval.high)
        if math.isfinite(low) and math.isfinite(high):
            return low, high
    except ValueError, RuntimeWarning:
        pass
    res = _scipy_stats.bootstrap(
        (d,),
        np.median,
        confidence_level=confidence,
        method="percentile",
        n_resamples=n_resamples,
        rng=np.random.default_rng(seed),
    )
    return float(res.confidence_interval.low), float(res.confidence_interval.high)


def _one_sided_p(d: np.ndarray) -> float:
    """One-sided Wilcoxon signed-rank p-value for "candidate is slower".

    Signed-rank rather than a t-test because latency distributions are
    skewed and occasionally have a stray outlier round; we do not want a
    single stalled invocation to drive the verdict.
    """
    if np.all(d == 0):
        # No difference whatsoever. Wilcoxon rejects an all-zero input.
        return 1.0
    # scipy's stubs type the result as an opaque tuple-like; index and cast.
    return cast(float, _scipy_stats.wilcoxon(d, alternative="greater")[1])


def compare(
    baseline: Samples,
    candidate: Samples,
    *,
    confidence: float = 0.95,
    seed: int = 0,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
) -> PairedComparison:
    """Compute the paired comparison for one metric of one cell.

    The returned comparison has no final verdict yet: ``p_adjusted`` is unset
    and ``verdict`` is INCONCLUSIVE until :func:`apply_multiplicity_control`
    has seen every cell in the run.
    """
    d = log_ratios(baseline, candidate)
    n = int(d.size)
    b_med = float(np.median(baseline)) if n else math.nan
    c_med = float(np.median(candidate)) if n else math.nan

    if n < MIN_USABLE_ROUNDS:
        return PairedComparison(
            n_rounds=n,
            baseline_median=b_med,
            candidate_median=c_med,
            ratio=math.exp(float(np.median(d))) if n else math.nan,
            ci_low=math.nan,
            ci_high=math.nan,
            p_value=math.nan,
            note=f"only {n} usable rounds; need at least {MIN_USABLE_ROUNDS}",
        )

    lo_log, hi_log = _bootstrap_ci(
        d, confidence=confidence, seed=seed, n_resamples=n_resamples
    )
    return PairedComparison(
        n_rounds=n,
        baseline_median=b_med,
        candidate_median=c_med,
        ratio=math.exp(float(np.median(d))),
        ci_low=math.exp(lo_log),
        ci_high=math.exp(hi_log),
        p_value=_one_sided_p(d),
    )


@dataclass(frozen=True, slots=True)
class NoiseFloor:
    """What the A/A control says about this runner's measurement noise.

    The A/A control compares the baseline build against *itself* through the
    identical pipeline, so its true ratio is exactly 1.0 by construction. Any
    apparent effect it reports is pure measurement noise, which makes it a
    direct, run-specific check on whether the verdicts can be believed.
    """

    #: True if the A/A comparison itself looked like a regression. The gate
    #: is then unreliable and the run must not fail the build on its findings.
    tripped: bool
    #: CI half-width on the log scale, as an equivalent ratio (e.g. 1.04).
    width_ratio: float
    #: True if the noise floor is wider than the effect we claim to detect.
    underpowered: bool
    detail: str = ""


def assess_noise_floor(
    control: PairedComparison | None, *, threshold: float = DEFAULT_THRESHOLD
) -> NoiseFloor:
    """Judge whether this runner was quiet enough to trust the verdicts.

    Two independent failure modes:

    - The control *tripped*: A/A produced an apparent effect past the
      threshold. Something is systematically biased (ordering, caching,
      thermal drift) and every verdict in the run is suspect.
    - The run is *underpowered*: the control's interval is wider than the
      effect size we are gating on, so a real regression of that size could
      not have been distinguished from noise. A PASS here means "we could not
      tell", which must not be reported as "no regression".
    """
    if control is None:
        return NoiseFloor(
            tripped=False,
            width_ratio=math.nan,
            underpowered=True,
            detail="no A/A control cell was run",
        )
    if control.n_rounds < MIN_USABLE_ROUNDS or not math.isfinite(
        control.ci_half_width_log
    ):
        return NoiseFloor(
            tripped=False,
            width_ratio=math.nan,
            underpowered=True,
            detail=f"A/A control did not produce a usable interval ({control.note})",
        )

    width_ratio = math.exp(control.ci_half_width_log)
    # The control's true ratio is 1.0. If its interval excludes the threshold
    # in either direction, the pipeline is measuring a difference that cannot
    # exist.
    tripped = control.ci_low > threshold or control.ci_high < 1 / threshold
    underpowered = control.ci_half_width_log >= math.log(threshold)

    detail = ""
    if tripped:
        detail = (
            f"A/A control reported ratio {control.ratio:.3f} "
            f"[{control.ci_low:.3f}, {control.ci_high:.3f}] against a true 1.000; "
            "runner is too noisy or the harness is biased"
        )
    elif underpowered:
        detail = (
            f"A/A noise floor +/-{(width_ratio - 1) * 100:.1f}% is not tighter than "
            f"the {(threshold - 1) * 100:.0f}% detection threshold"
        )
    return NoiseFloor(
        tripped=tripped,
        width_ratio=width_ratio,
        underpowered=underpowered,
        detail=detail,
    )


def _worst_noise(noises: Iterable[NoiseFloor]) -> NoiseFloor | None:
    """The least reassuring control in the run, or None if there were none.

    Worst case rather than average: a single tripped control means the
    harness may be biased on this runner, and averaging that away with two
    quiet ones is exactly the reassurance the control exists to withhold.
    """

    def rank(n: NoiseFloor) -> tuple[bool, bool, float]:
        # A NaN width is an unusable interval, which is worse than any real one.
        width = n.width_ratio if math.isfinite(n.width_ratio) else math.inf
        return (n.tripped, n.underpowered, width)

    return max(noises, key=rank, default=None)


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """BH-adjusted p-values, controlling the false discovery rate.

    NaNs (cells with too few rounds to test) pass through untouched and are
    excluded from the adjustment, so an unmeasurable cell neither gains nor
    confers significance.
    """
    p = np.asarray(p_values, dtype=float)
    out = p.copy()
    testable = np.isfinite(p)
    if not testable.any():
        return out.tolist()
    out[testable] = _scipy_stats.false_discovery_control(p[testable], method="bh")
    return out.tolist()


@dataclass(slots=True)
class GateResult:
    """The run-level outcome after every cell has been compared."""

    comparisons: dict[str, PairedComparison] = field(default_factory=dict)
    #: The run-level noise floor: the *worst* of the per-control assessments,
    #: since one biased control means the harness may be biased everywhere.
    noise: NoiseFloor | None = None
    #: Every control's own assessment, keyed by its comparison key. A run with
    #: several SDKs has one control each, and go's noise floor says nothing
    #: about java's.
    noise_by_control: dict[str, NoiseFloor] = field(default_factory=dict)
    #: Keys of cells that are confirmed regressions on a gated metric.
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    #: True if the run may fail the build. False when the A/A control tripped:
    #: we still report, but a gate we cannot trust must not turn the build red.
    trustworthy: bool = True
    summary: str = ""
    #: At least one comparison between distinct baseline and candidate roles
    #: was measured. A clean A/A control alone says nothing about the candidate.
    has_candidate_comparisons: bool = False

    @property
    def should_fail(self) -> bool:
        return self.trustworthy and bool(self.regressions)

    @property
    def nothing_measured(self) -> bool:
        """True if the run produced no baseline/candidate comparison.

        An A/A control measures the harness, not the candidate, so a control-only
        run still measured nothing that can answer the benchmark's question.
        This is not the same thing as "no regressions", though the two are
        identical from the outside: both have an empty ``regressions`` list.
        Callers gate on this separately.
        """
        return not self.has_candidate_comparisons


def apply_multiplicity_control(
    comparisons: dict[str, PairedComparison],
    *,
    gated: set[str] | None = None,
    controls: Mapping[str, str] | None = None,
    control_keys: set[str] | None = None,
    censored: dict[str, str] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    alpha: float = DEFAULT_ALPHA,
) -> GateResult:
    """Assign final verdicts to every cell and decide the run's outcome.

    Args:
        comparisons: cell key -> comparison, for every measured (cell, metric).
        gated: keys allowed to fail the build. Keys outside this set are still
            given a verdict and reported, but never counted as a regression.
            ``None`` means every key is gated.
        controls: comparison key -> the A/A control key that assesses *its*
            noise floor. A run measuring several SDKs has one control each,
            and a cell judged against another SDK's control is judged against
            a noise floor that was never measured for it. A key absent from
            this mapping has no control, which is treated as underpowered.
        control_keys: every key belonging to a control cell. Kept out of the
            multiplicity correction and out of the regression and improvement
            tallies: an A/A cell is not a hypothesis about the candidate.
        censored: keys whose measurement is known to be invalid, mapped to why.
            Reported as INCONCLUSIVE and never counted as a regression or an
            improvement. A censored reading that happens to land inside the
            threshold is otherwise indistinguishable from a real PASS, which
            is the more dangerous of the two ways to be wrong.
        threshold: minimum ratio worth calling a regression, e.g. 1.15.
        alpha: false discovery rate for the BH adjustment.

    Returns:
        A :class:`GateResult` whose ``comparisons`` hold the finalized
        verdicts. The input mapping is not mutated.
    """
    keys = list(comparisons)
    controls = controls or {}
    # The keys actually doing the assessing: one metric of one control cell
    # per SDK. A control cell's other metrics are still control keys -- kept
    # out of the gate -- but they are not anybody's noise floor.
    assessors = set(controls.values())
    control_keys = control_keys or assessors
    censored = censored or {}

    noise_by_control = {
        ck: assess_noise_floor(comparisons.get(ck), threshold=threshold)
        for ck in assessors
    }
    #: What a cell with no control of its own is judged against: nothing, which
    #: `assess_noise_floor` calls underpowered, so it may report at worst
    #: INCONCLUSIVE rather than a PASS nobody measured the power for.
    uncontrolled = assess_noise_floor(None, threshold=threshold)
    noise = _worst_noise(noise_by_control.values()) or uncontrolled

    # Neither a control nor a censored reading is a hypothesis about the
    # candidate, so neither may dilute the correction applied to the cells
    # that are. The gated keys are corrected as their own family for the same
    # reason: adjusting them against metrics nobody gates on only makes a real
    # regression harder to confirm. Ungated metrics still get a family of
    # their own so that they carry a reportable verdict.
    adjustable = [k for k in keys if k not in control_keys and k not in censored]
    gated_family = [k for k in adjustable if gated is None or k in gated]
    rest = [k for k in adjustable if k not in set(gated_family)]
    p_adj: dict[str, float] = {}
    for family in (gated_family, rest):
        p_adj.update(
            zip(
                family,
                benjamini_hochberg([comparisons[k].p_value for k in family]),
                strict=True,
            )
        )

    result = GateResult(
        noise=noise,
        noise_by_control=noise_by_control,
        has_candidate_comparisons=any(k not in control_keys for k in keys),
    )
    for key in keys:
        c = comparisons[key]
        pa = p_adj.get(key)
        if key in censored:
            verdict, note = Verdict.INCONCLUSIVE, censored[key]
        else:
            verdict, note = _verdict_for(
                c,
                pa,
                threshold=threshold,
                alpha=alpha,
                noise=noise_by_control.get(controls.get(key, ""), uncontrolled),
                is_control=key in control_keys,
            )
        result.comparisons[key] = PairedComparison(
            n_rounds=c.n_rounds,
            baseline_median=c.baseline_median,
            candidate_median=c.candidate_median,
            ratio=c.ratio,
            ci_low=c.ci_low,
            ci_high=c.ci_high,
            p_value=c.p_value,
            p_adjusted=pa,
            verdict=verdict,
            note=note or c.note,
        )
        if key in control_keys:
            continue
        if verdict is Verdict.REGRESSION and (gated is None or key in gated):
            result.regressions.append(key)
        elif verdict is Verdict.IMPROVED:
            result.improvements.append(key)

    result.trustworthy = not noise.tripped
    result.summary = _summarize(result, noise, threshold)
    return result


def _verdict_for(
    c: PairedComparison,
    p_adjusted: float | None,
    *,
    threshold: float,
    alpha: float,
    noise: NoiseFloor,
    is_control: bool,
) -> tuple[Verdict, str]:
    if c.n_rounds < MIN_USABLE_ROUNDS or not math.isfinite(c.ci_low):
        return Verdict.INCONCLUSIVE, c.note or "no usable interval"

    p = c.p_value if is_control else p_adjusted
    if p is None or not math.isfinite(p):
        return Verdict.INCONCLUSIVE, "no p-value"

    if c.ci_low > threshold and p < alpha:
        return Verdict.REGRESSION, ""
    if c.ci_high < 1 / threshold and p > 1 - alpha:
        return Verdict.IMPROVED, ""

    # Not a regression. But "we looked and found nothing" only counts as PASS
    # if we could have found something. Without the power to resolve an effect
    # of `threshold`, the honest answer is that we do not know.
    if not is_control and noise.underpowered:
        return Verdict.INCONCLUSIVE, noise.detail
    if c.ci_half_width_log >= math.log(threshold):
        return (
            Verdict.INCONCLUSIVE,
            f"interval +/-{(math.exp(c.ci_half_width_log) - 1) * 100:.1f}% is wider "
            f"than the {(threshold - 1) * 100:.0f}% threshold",
        )
    return Verdict.PASS, ""


def _summarize(result: GateResult, noise: NoiseFloor, threshold: float) -> str:
    if result.nothing_measured:
        # Before the noise check: with nothing measured there is no control
        # either, and "the A/A control failed" would misdescribe a run that
        # never got as far as running one.
        return (
            "NOTHING MEASURED: no cell produced a comparison, so this run says "
            "nothing about performance either way."
        )
    if noise.tripped:
        return (
            f"INCONCLUSIVE: the A/A control failed its own comparison. {noise.detail}. "
            "Verdicts below are reported but not gated."
        )
    if result.regressions:
        return (
            f"{len(result.regressions)} confirmed regression(s) past the "
            f"{(threshold - 1) * 100:.0f}% threshold: {', '.join(result.regressions)}"
        )
    inconclusive = [
        k for k, c in result.comparisons.items() if c.verdict is Verdict.INCONCLUSIVE
    ]
    if inconclusive:
        return (
            f"No confirmed regressions. {len(inconclusive)} cell(s) INCONCLUSIVE "
            f"(runner noise floor +/-{(noise.width_ratio - 1) * 100:.1f}%)."
        )
    return (
        f"No regressions. All cells resolved within the "
        f"{(threshold - 1) * 100:.0f}% threshold "
        f"(runner noise floor +/-{(noise.width_ratio - 1) * 100:.1f}%)."
    )
