"""Paired statistical comparison of SDK builds.

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

- Clause 1 establishes that the effect is larger than the practical threshold,
  but an unadjusted 95% interval on every cell does not control false
  discoveries across the run.
- Clause 2 supplies that multiplicity control, but alone would flag both
  real-but-trivial effects and pure-noise false positives. A reproducible 0.5%
  slowdown is statistically real and still not worth a red build.

Together they answer the only question worth gating on: is the slowdown both
real and large enough to care about?

Head-to-head contrasts
----------------------
A run may measure more than two arms. Every arm runs once per round, so any
*pair* of them is a valid within-round comparison -- which is what makes a
bake-off between two competing implementations possible at all, and what two
separate two-arm runs on two different runners could never give you.

Contrasts against the run's designated reference keep the rule above and can
fail the build. Contrasts between two non-reference arms are judged by
:func:`_symmetric_verdict_for` instead, which reads the same threshold as a
two-sided equivalence band and returns FASTER, SLOWER, or TIED. They never
gate: a bake-off ranks candidates, it does not decide whether the build is
broken, and there is no incumbent for "regression" to be relative to.

The three families -- gated, head-to-head, and ungated -- are BH-corrected
separately, so adding candidates to a bake-off does not cost the regression
gate any power.
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
    """Outcome for a single comparison.

    The first four are the *gated* vocabulary, used for a contrast against the
    run's reference build: the question is one-sided ("did the candidate get
    slower?") and only REGRESSION can turn the build red.

    The last three are the *symmetric* vocabulary, used for a head-to-head
    between two non-reference arms in a bake-off. There the question has no
    privileged direction -- neither arm is the incumbent -- and "no measurable
    difference" is a real answer rather than the absence of one, so TIED exists
    instead of reusing PASS.
    """

    PASS = "PASS"
    REGRESSION = "REGRESSION"
    IMPROVED = "IMPROVED"
    INCONCLUSIVE = "INCONCLUSIVE"

    FASTER = "FASTER"
    SLOWER = "SLOWER"
    TIED = "TIED"


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
    #: One-sided p-value for "candidate is slower". Retains the original field
    #: name for artifact/API compatibility; the opposite direction is explicit.
    p_value: float
    #: One-sided p-value for "candidate is faster".
    p_value_faster: float
    #: Set by :func:`apply_multiplicity_control` once every cell is known.
    p_adjusted: float | None = None
    #: BH-adjusted form of :attr:`p_value_faster`.
    p_adjusted_faster: float | None = None
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


def _one_sided_ps(d: np.ndarray) -> tuple[float, float]:
    """Wilcoxon signed-rank p-values for slower and faster, respectively.

    Signed-rank does not require normally distributed raw latencies and a
    single stalled invocation cannot drive it by magnitude alone. Interpreting
    it as a location test does assume the *paired log differences* are roughly
    symmetric; the log transform and multiplicative-jitter measurement model
    are intended to make that a reasonable assumption.
    """
    if np.all(d == 0):
        # No difference whatsoever. Wilcoxon rejects an all-zero input.
        return 1.0, 1.0
    # scipy's stubs type the result as an opaque tuple-like; index and cast.
    slower = cast(float, _scipy_stats.wilcoxon(d, alternative="greater")[1])
    faster = cast(float, _scipy_stats.wilcoxon(d, alternative="less")[1])
    return slower, faster


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
            p_value_faster=math.nan,
            note=f"only {n} usable rounds; need at least {MIN_USABLE_ROUNDS}",
        )

    lo_log, hi_log = _bootstrap_ci(
        d, confidence=confidence, seed=seed, n_resamples=n_resamples
    )
    p_slower, p_faster = _one_sided_ps(d)
    return PairedComparison(
        n_rounds=n,
        baseline_median=b_med,
        candidate_median=c_med,
        ratio=math.exp(float(np.median(d))),
        ci_low=math.exp(lo_log),
        ci_high=math.exp(hi_log),
        p_value=p_slower,
        p_value_faster=p_faster,
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


def _noise_rank(n: NoiseFloor) -> tuple[bool, bool, float]:
    """Order noise floors from most to least reassuring."""
    # A NaN width is an unusable interval, which is worse than any real one.
    width = n.width_ratio if math.isfinite(n.width_ratio) else math.inf
    return (n.tripped, n.underpowered, width)


def _worst_noise(noises: Iterable[NoiseFloor]) -> NoiseFloor | None:
    """The least reassuring control in the run, or None if there were none.

    Worst case rather than average: a single tripped control means the
    harness may be biased on this runner, and averaging that away with two
    quiet ones is exactly the reassurance the control exists to withhold.
    """
    return max(noises, key=_noise_rank, default=None)


def worst_control_key(
    comparisons: Mapping[str, PairedComparison],
    keys: Sequence[str],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> str | None:
    """Which of several A/A contrasts should stand as the noise floor.

    A K-arm control cell yields C(K,2) A/A contrasts rather than one, and they
    are not interchangeable: arm 3 runs two invocations after arm 1, so it
    carries more within-round drift than an adjacent pair does. Taking the
    worst of them keeps the floor honest for the widest-spaced contrast the
    run actually judges. Taking whichever came first would let dict ordering
    decide how noisy the run is allowed to look.

    Ties break on input order, so the choice is reproducible across runs.
    """
    ranked = [
        (_noise_rank(assess_noise_floor(comparisons.get(k), threshold=threshold)), i, k)
        for i, k in enumerate(keys)
    ]
    return max(ranked, key=lambda r: (r[0], -r[1]))[2] if ranked else None


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
    #: Head-to-head keys that came back FASTER or SLOWER -- a bake-off contrast
    #: between two non-reference arms that the run was able to decide. Never
    #: gates anything; this is the material a caller ranks arms from. Naming a
    #: winner needs to know which arm is which, and a key is opaque here, so
    #: that lives in the reporting layer.
    ranked: list[str] = field(default_factory=list)
    #: True if the run may fail the build. False when the A/A control tripped:
    #: we still report, but a gate we cannot trust must not turn the build red.
    trustworthy: bool = True
    summary: str = ""

    @property
    def should_fail(self) -> bool:
        return self.trustworthy and bool(self.regressions)

    @property
    def nothing_measured(self) -> bool:
        """True if the run produced no comparisons at all.

        Not the same thing as "no regressions", though the two are identical
        from the outside: both have an empty ``regressions`` list. A run where
        every cell was skipped -- no baseline installed, an SDK that would not
        build -- reports the cheerful summary of a clean one, which is how a
        benchmark that quietly stopped measuring anything survives for months.
        Callers gate on this separately.
        """
        return not self.comparisons


def apply_multiplicity_control(
    comparisons: dict[str, PairedComparison],
    *,
    gated: set[str] | None = None,
    symmetric: set[str] | None = None,
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
        symmetric: keys judged by the two-sided FASTER/SLOWER/TIED rule instead
            of the one-sided regression rule -- head-to-head contrasts between
            two arms neither of which is the run's reference. They are reported
            and ranked but never gate, so a bake-off cannot turn the build red
            on the strength of a comparison that has no incumbent.
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
    symmetric = symmetric or set()
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
    #
    # Head-to-head contrasts get a third family on the same argument. A
    # bake-off between two candidates is a question of interest, not a build
    # gate, and correcting the gate against it would cost the gate power for
    # tests that cannot fail the build -- which is the exact trade the
    # gated/ungated split already refuses to make.
    adjustable = [k for k in keys if k not in control_keys and k not in censored]
    gated_family = [k for k in adjustable if gated is None or k in gated]
    gated_set = set(gated_family)
    # Gated wins a tie. A key that is somehow both is a vs-reference contrast,
    # and the one-sided rule is the one that can fail the build.
    symmetric_family = [k for k in adjustable if k not in gated_set and k in symmetric]
    symmetric_set = set(symmetric_family)
    rest = [k for k in adjustable if k not in gated_set and k not in symmetric_set]
    p_adj: dict[str, float] = {}
    p_adj_faster: dict[str, float] = {}
    for family in (gated_family, symmetric_family, rest):
        p_adj.update(
            zip(
                family,
                benjamini_hochberg([comparisons[k].p_value for k in family]),
                strict=True,
            )
        )
        # The opposite direction needs its own lower-tail p-value and its own
        # adjustment. Reading an adjusted upper-tail value as `p > 1-alpha`
        # is invalid: BH controls small p-values and generally pushes large
        # ones toward 1, making that backwards test easier rather than safer.
        p_adj_faster.update(
            zip(
                family,
                benjamini_hochberg([comparisons[k].p_value_faster for k in family]),
                strict=True,
            )
        )

    result = GateResult(noise=noise, noise_by_control=noise_by_control)
    for key in keys:
        c = comparisons[key]
        pa = p_adj.get(key)
        pa_faster = p_adj_faster.get(key)
        key_noise = noise_by_control.get(controls.get(key, ""), uncontrolled)
        if key in censored:
            verdict, note = Verdict.INCONCLUSIVE, censored[key]
        elif key in control_keys:
            # A control's own contrast is reported in the gated vocabulary
            # whatever kind of pair it is: its job is to say what the harness's
            # error looks like in the same terms the gate uses.
            verdict, note = _verdict_for(
                c,
                pa,
                pa_faster,
                threshold=threshold,
                alpha=alpha,
                noise=key_noise,
                is_control=True,
            )
        elif key in symmetric_set:
            verdict, note = _symmetric_verdict_for(
                c,
                pa,
                pa_faster,
                threshold=threshold,
                alpha=alpha,
                noise=key_noise,
            )
        else:
            verdict, note = _verdict_for(
                c,
                pa,
                pa_faster,
                threshold=threshold,
                alpha=alpha,
                noise=key_noise,
                is_control=False,
            )
        result.comparisons[key] = PairedComparison(
            n_rounds=c.n_rounds,
            baseline_median=c.baseline_median,
            candidate_median=c.candidate_median,
            ratio=c.ratio,
            ci_low=c.ci_low,
            ci_high=c.ci_high,
            p_value=c.p_value,
            p_value_faster=c.p_value_faster,
            p_adjusted=pa,
            p_adjusted_faster=pa_faster,
            verdict=verdict,
            note=note or c.note,
        )
        if key in control_keys:
            continue
        if verdict is Verdict.REGRESSION and (gated is None or key in gated):
            result.regressions.append(key)
        elif verdict is Verdict.IMPROVED:
            result.improvements.append(key)
        elif verdict in (Verdict.FASTER, Verdict.SLOWER):
            result.ranked.append(key)

    result.trustworthy = not noise.tripped
    result.summary = _summarize(result, noise, threshold)
    return result


def _verdict_for(
    c: PairedComparison,
    p_adjusted: float | None,
    p_adjusted_faster: float | None,
    *,
    threshold: float,
    alpha: float,
    noise: NoiseFloor,
    is_control: bool,
) -> tuple[Verdict, str]:
    if c.n_rounds < MIN_USABLE_ROUNDS or not math.isfinite(c.ci_low):
        return Verdict.INCONCLUSIVE, c.note or "no usable interval"

    p_slower = c.p_value if is_control else p_adjusted
    p_faster = c.p_value_faster if is_control else p_adjusted_faster
    if p_slower is None or p_faster is None:
        return Verdict.INCONCLUSIVE, "no p-value"
    if not (math.isfinite(p_slower) and math.isfinite(p_faster)):
        return Verdict.INCONCLUSIVE, "no p-value"

    if c.ci_low > threshold and p_slower < alpha:
        return Verdict.REGRESSION, ""
    if c.ci_high < 1 / threshold and p_faster < alpha:
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


def _symmetric_verdict_for(
    c: PairedComparison,
    p_adjusted: float | None,
    p_adjusted_faster: float | None,
    *,
    threshold: float,
    alpha: float,
    noise: NoiseFloor,
) -> tuple[Verdict, str]:
    """Rank two arms against each other, with no privileged direction.

    Used for a head-to-head between two candidates in a bake-off, where the
    one-sided regression rule does not apply: neither arm is the incumbent, so
    there is no "did it get worse" to ask.

    The band is ``[1/threshold, threshold]`` -- the same effect size the gate
    cares about, read in both directions:

    - interval entirely above the band -> SLOWER
    - interval entirely below the band -> FASTER
    - interval entirely *inside* the band -> TIED, meaning any real difference
      is smaller than the effect anybody has claimed to care about. This is a
      positive finding and the most likely honest answer for two
      implementations of the same idea, which is why it is not folded into
      PASS: PASS is the one-sided claim "did not regress", and reporting a
      bake-off that way would let a slower arm read as a clean result.
    - anything straddling a band edge -> INCONCLUSIVE, the run could not rank
      them.

    A CI-inside-band test at 95% is TOST at 2.5% rather than the nominal 5%,
    so TIED is the conservative call: harder to earn than the equivalence test
    it stands in for, never easier.
    """
    if c.n_rounds < MIN_USABLE_ROUNDS or not math.isfinite(c.ci_low):
        return Verdict.INCONCLUSIVE, c.note or "no usable interval"

    # Same precondition as the gated rule: without a noise floor establishing
    # that an effect of this size was resolvable, neither a ranking nor a tie
    # is a statement about the arms. Invariant 4 covers TIED too -- a tie
    # nobody had the power to distinguish from a difference is not a tie.
    if noise.underpowered:
        return Verdict.INCONCLUSIVE, noise.detail

    if p_adjusted is None or p_adjusted_faster is None:
        return Verdict.INCONCLUSIVE, "no p-value"
    if not (math.isfinite(p_adjusted) and math.isfinite(p_adjusted_faster)):
        return Verdict.INCONCLUSIVE, "no p-value"

    # Direction clauses mirror REGRESSION and IMPROVED exactly. Each direction
    # uses its own BH-adjusted one-sided p-value.
    if c.ci_low > threshold and p_adjusted < alpha:
        return Verdict.SLOWER, ""
    if c.ci_high < 1 / threshold and p_adjusted_faster < alpha:
        return Verdict.FASTER, ""
    if c.ci_low > 1 / threshold and c.ci_high < threshold:
        return Verdict.TIED, ""
    return (
        Verdict.INCONCLUSIVE,
        f"interval [{c.ci_low:.3f}, {c.ci_high:.3f}] straddles the "
        f"+/-{(threshold - 1) * 100:.0f}% band; the two arms cannot be ranked",
    )


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
    # Appended rather than returned on its own: a bake-off still has a gate
    # running against the reference, and "which candidate won" must not
    # displace "did either of them regress".
    head_to_head = (
        f" {len(result.ranked)} head-to-head contrast(s) decided."
        if result.ranked
        else ""
    )
    inconclusive = [
        k for k, c in result.comparisons.items() if c.verdict is Verdict.INCONCLUSIVE
    ]
    if inconclusive:
        return (
            f"No confirmed regressions. {len(inconclusive)} cell(s) INCONCLUSIVE "
            f"(runner noise floor +/-{(noise.width_ratio - 1) * 100:.1f}%)."
            f"{head_to_head}"
        )
    return (
        f"No regressions. All cells resolved within the "
        f"{(threshold - 1) * 100:.0f}% threshold "
        f"(runner noise floor +/-{(noise.width_ratio - 1) * 100:.1f}%)."
        f"{head_to_head}"
    )
