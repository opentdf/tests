"""Unit tests for the benchmark decision logic in ``perf/stats.py``.

These are pure-function tests: no platform, no SDK, no subprocess. They run in
``check.yml`` alongside lint, because a regression gate whose statistics are
wrong is worse than no gate at all -- it either cries wolf until it is muted,
or stays quiet while performance rots.

The two properties that matter most are covered by
``test_pure_noise_false_positive_rate_is_controlled`` (the gate does not fire
on a runner that is merely noisy) and
``test_planted_regression_is_detected`` (it does fire on a real slowdown).
"""

import math

import numpy as np
import pytest

from perf import stats
from perf.stats import Verdict

# Typical CI-runner dispersion for a CLI invocation: roughly +/-8% round to
# round. Large enough to be realistic, small enough that 30 rounds can resolve
# a 15% effect.
NOISE_SIGMA = 0.08
ROUNDS = 30
# Bootstrap resamples for tests. Lower than the production default to keep the
# repeated-trial tests quick; the estimates are still stable to ~1%.
RESAMPLES = 999


def synth(
    rng: np.random.Generator,
    true_ratio: float,
    *,
    n: int = ROUNDS,
    sigma: float = NOISE_SIGMA,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (baseline, candidate) samples with a known multiplicative effect.

    Both arms get independent lognormal noise around a shared base cost, which
    is the structure the real harness produces: a per-round shared component
    (runner speed) that cancels, plus independent per-invocation jitter.
    """
    base = 1.0 * rng.lognormal(0.0, sigma, n)
    baseline = base * rng.lognormal(0.0, sigma, n)
    candidate = base * true_ratio * rng.lognormal(0.0, sigma, n)
    return baseline, candidate


def gate_one(
    comparison: stats.PairedComparison,
    *,
    control: stats.PairedComparison | None = None,
    threshold: float = 1.15,
) -> stats.GateResult:
    """Run a single comparison through the full run-level gate."""
    cells = {"cell": comparison}
    if control is not None:
        cells["control"] = control
    return stats.apply_multiplicity_control(
        cells,
        controls=all_under_one_control(cells) if control is not None else None,
        threshold=threshold,
    )


def all_under_one_control(
    cells: dict[str, stats.PairedComparison], key: str = "control"
) -> dict[str, str]:
    """Map every cell to the single control cell, as a one-SDK run does."""
    return dict.fromkeys(cells, key)


def quiet_control(seed: int = 7) -> stats.PairedComparison:
    """An A/A control from a well-behaved runner, tight enough to have power."""
    rng = np.random.default_rng(seed)
    # More rounds and lower jitter than a real cell, so the control does not
    # itself become the limiting factor in tests about other things.
    b, c = synth(rng, 1.0, n=80, sigma=0.03)
    return stats.compare(b, c, seed=seed, n_resamples=RESAMPLES)


class TestLogRatios:
    def test_recovers_exact_ratio(self):
        d = stats.log_ratios([2.0, 4.0], [3.0, 6.0])
        assert np.allclose(np.exp(d), 1.5)

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError, match="same length"):
            stats.log_ratios([1.0, 2.0], [1.0])

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_rejects_non_positive(self, bad: float):
        # A zero or negative duration is a broken measurement, not a fast one.
        with pytest.raises(ValueError, match="positive"):
            stats.log_ratios([1.0, bad], [1.0, 1.0])

    def test_rejects_non_finite(self):
        with pytest.raises(ValueError, match="finite"):
            stats.log_ratios([1.0, math.inf], [1.0, 1.0])

    def test_empty_is_empty(self):
        assert stats.log_ratios([], []).size == 0


class TestCompare:
    def test_point_estimate_tracks_true_ratio(self):
        rng = np.random.default_rng(0)
        b, c = synth(rng, 1.25, n=200)
        r = stats.compare(b, c, seed=0, n_resamples=RESAMPLES)
        assert r.ratio == pytest.approx(1.25, rel=0.05)

    def test_interval_covers_truth(self):
        rng = np.random.default_rng(1)
        b, c = synth(rng, 1.25, n=200)
        r = stats.compare(b, c, seed=1, n_resamples=RESAMPLES)
        assert r.ci_low < 1.25 < r.ci_high

    def test_too_few_rounds_yields_no_interval(self):
        rng = np.random.default_rng(2)
        b, c = synth(rng, 2.0, n=3)
        r = stats.compare(b, c, seed=2, n_resamples=RESAMPLES)
        assert r.n_rounds == 3
        assert math.isnan(r.ci_low)
        assert "at least" in r.note

    def test_identical_inputs_give_unit_ratio_and_no_significance(self):
        v = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        r = stats.compare(v, v, seed=0, n_resamples=RESAMPLES)
        assert r.ratio == pytest.approx(1.0)
        assert r.p_value == 1.0

    def test_constant_offset_has_degenerate_interval(self):
        # Every round shows exactly a 2x slowdown: there is no sampling
        # variability, so the interval collapses onto the point estimate
        # rather than blowing up in the BCa jackknife.
        b = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        c = [2 * x for x in b]
        r = stats.compare(b, c, seed=0, n_resamples=RESAMPLES)
        assert r.ratio == pytest.approx(2.0)
        assert r.ci_low == pytest.approx(2.0)
        assert r.ci_high == pytest.approx(2.0)

    def test_single_outlier_round_does_not_dominate(self):
        # One stalled invocation out of 30 must not manufacture a regression;
        # this is why the estimator is a median and the test is signed-rank.
        rng = np.random.default_rng(3)
        b, c = synth(rng, 1.0)
        c = c.copy()
        c[0] *= 50
        r = stats.compare(b, c, seed=3, n_resamples=RESAMPLES)
        assert r.ratio == pytest.approx(1.0, abs=0.1)
        assert (
            gate_one(r, control=quiet_control()).comparisons["cell"].verdict
            is not Verdict.REGRESSION
        )


class TestDecisionRule:
    def test_planted_regression_is_detected(self):
        rng = np.random.default_rng(10)
        b, c = synth(rng, 1.30, n=60)
        g = gate_one(
            stats.compare(b, c, seed=10, n_resamples=RESAMPLES), control=quiet_control()
        )
        assert g.comparisons["cell"].verdict is Verdict.REGRESSION
        assert g.regressions == ["cell"]
        assert g.should_fail

    def test_trivial_but_real_slowdown_does_not_fire(self):
        # A reproducible 3% slowdown, measured precisely enough to be
        # statistically significant, is deliberately not a build failure.
        rng = np.random.default_rng(11)
        b, c = synth(rng, 1.03, n=400, sigma=0.02)
        r = stats.compare(b, c, seed=11, n_resamples=RESAMPLES)
        assert r.p_value < 0.05, "precondition: the effect is statistically real"
        g = gate_one(r, control=quiet_control())
        assert g.comparisons["cell"].verdict is not Verdict.REGRESSION
        assert not g.should_fail

    def test_planted_speedup_is_reported_but_never_fails(self):
        rng = np.random.default_rng(12)
        b, c = synth(rng, 0.70, n=60)
        g = gate_one(
            stats.compare(b, c, seed=12, n_resamples=RESAMPLES), control=quiet_control()
        )
        assert g.comparisons["cell"].verdict is Verdict.IMPROVED
        assert not g.should_fail

    def test_borderline_effect_without_power_is_inconclusive_not_pass(self):
        # A 15% effect with only a handful of very noisy rounds: the honest
        # answer is "cannot tell", never "no regression".
        rng = np.random.default_rng(13)
        b, c = synth(rng, 1.15, n=6, sigma=0.35)
        g = gate_one(
            stats.compare(b, c, seed=13, n_resamples=RESAMPLES), control=quiet_control()
        )
        assert g.comparisons["cell"].verdict is Verdict.INCONCLUSIVE

    def test_pure_noise_false_positive_rate_is_controlled(self):
        # The property the whole design exists to guarantee: on a runner with
        # no real effect, the gate must almost never fire. Nominal alpha is
        # 0.05, but the threshold clause should push the realized rate far
        # below that.
        trials, fired = 200, 0
        for seed in range(trials):
            rng = np.random.default_rng(1000 + seed)
            b, c = synth(rng, 1.0)
            g = gate_one(
                stats.compare(b, c, seed=seed, n_resamples=RESAMPLES),
                control=quiet_control(),
            )
            fired += g.should_fail
        assert fired / trials <= 0.02, (
            f"gate fired on {fired}/{trials} pure-noise runs; "
            "it will be muted in production at this rate"
        )

    def test_detects_regression_across_realistic_noise(self):
        # The complement of the false-positive test: a 30% regression must be
        # caught reliably, not just on a lucky seed.
        trials, caught = 40, 0
        for seed in range(trials):
            rng = np.random.default_rng(2000 + seed)
            b, c = synth(rng, 1.30, n=40)
            g = gate_one(
                stats.compare(b, c, seed=seed, n_resamples=RESAMPLES),
                control=quiet_control(),
            )
            caught += g.should_fail
        assert caught / trials >= 0.90, (
            f"only caught {caught}/{trials} real 30% regressions"
        )


class TestNoiseFloor:
    def test_clean_control_is_trusted(self):
        n = stats.assess_noise_floor(quiet_control(), threshold=1.15)
        assert not n.tripped
        assert not n.underpowered

    def test_missing_control_is_underpowered(self):
        n = stats.assess_noise_floor(None, threshold=1.15)
        assert n.underpowered
        assert "no A/A control" in n.detail

    def test_wide_control_marks_run_underpowered(self):
        rng = np.random.default_rng(20)
        b, c = synth(rng, 1.0, n=8, sigma=0.5)
        n = stats.assess_noise_floor(
            stats.compare(b, c, seed=20, n_resamples=RESAMPLES), threshold=1.15
        )
        assert n.underpowered

    def test_biased_control_disables_the_gate(self):
        # A control that reports a large effect against a true ratio of 1.0
        # means the harness or the runner is systematically biased. Real cells
        # must still be reported, but must not turn the build red.
        rng = np.random.default_rng(21)
        cb, cc = synth(rng, 1.40, n=60)  # A/A that "found" 40%: impossible
        control = stats.compare(cb, cc, seed=21, n_resamples=RESAMPLES)
        rng2 = np.random.default_rng(22)
        b, c = synth(rng2, 1.40, n=60)
        g = gate_one(
            stats.compare(b, c, seed=22, n_resamples=RESAMPLES), control=control
        )

        assert g.noise is not None and g.noise.tripped
        assert not g.trustworthy
        assert g.comparisons["cell"].verdict is Verdict.REGRESSION
        assert not g.should_fail, "an untrustworthy gate must not fail the build"
        assert "A/A control failed" in g.summary

    def test_underpowered_run_cannot_report_pass(self):
        rng = np.random.default_rng(23)
        noisy_control = stats.compare(
            *synth(np.random.default_rng(24), 1.0, n=8, sigma=0.4),
            seed=24,
            n_resamples=RESAMPLES,
        )
        b, c = synth(rng, 1.0, n=40)
        g = gate_one(
            stats.compare(b, c, seed=23, n_resamples=RESAMPLES), control=noisy_control
        )
        assert g.comparisons["cell"].verdict is Verdict.INCONCLUSIVE
        assert not g.should_fail


class TestMultiplicityControl:
    def test_bh_is_monotone_and_bounded(self):
        raw = [0.001, 0.01, 0.03, 0.2, 0.7]
        adj = stats.benjamini_hochberg(raw)
        pairs = zip(adj, raw, strict=True)
        assert all(a >= r - 1e-12 for a, r in pairs), "adjustment never shrinks p"
        assert adj == sorted(adj), "monotone in the sorted input"
        assert all(a <= 1.0 for a in adj)

    def test_bh_passes_nan_through(self):
        adj = stats.benjamini_hochberg([0.01, float("nan"), 0.02])
        assert math.isnan(adj[1])
        assert all(math.isfinite(a) for a in (adj[0], adj[2]))

    def test_correction_suppresses_lone_lucky_cell(self):
        # 20 pure-noise cells: without BH one of them firing is expected.
        cells = {}
        for i in range(20):
            rng = np.random.default_rng(3000 + i)
            b, c = synth(rng, 1.0)
            cells[f"cell{i}"] = stats.compare(b, c, seed=i, n_resamples=RESAMPLES)
        cells["control"] = quiet_control()
        g = stats.apply_multiplicity_control(
            cells, controls=all_under_one_control(cells)
        )
        assert not g.should_fail
        assert g.regressions == []

    def test_control_is_excluded_from_the_gate(self):
        rng = np.random.default_rng(30)
        b, c = synth(rng, 1.0, n=40)
        g = gate_one(
            stats.compare(b, c, seed=30, n_resamples=RESAMPLES), control=quiet_control()
        )
        assert "control" not in g.regressions
        assert g.comparisons["control"].p_adjusted is None

    def test_ungated_metric_is_reported_but_cannot_fail(self):
        rng = np.random.default_rng(31)
        b, c = synth(rng, 1.5, n=60)
        cells = {
            "wall": stats.compare(b, c, seed=31, n_resamples=RESAMPLES),
            "cpu": stats.compare(b, c, seed=32, n_resamples=RESAMPLES),
            "control": quiet_control(),
        }
        g = stats.apply_multiplicity_control(
            cells, gated={"wall"}, controls=all_under_one_control(cells)
        )
        assert g.comparisons["cpu"].verdict is Verdict.REGRESSION
        assert g.regressions == ["wall"], "cpu is reported but never gates"

    def test_empty_run_reports_no_regressions(self):
        g = stats.apply_multiplicity_control({})
        assert not g.should_fail, "nothing measured is not a regression"
        assert g.regressions == []

    def test_empty_run_says_it_measured_nothing(self):
        # The dangerous case: an empty run and a clean run have the same empty
        # regression list, so without this the report of a benchmark that
        # skipped every cell is indistinguishable from one that passed.
        g = stats.apply_multiplicity_control({})
        assert g.nothing_measured
        assert "NOTHING MEASURED" in g.summary
        assert "no regressions" not in g.summary.lower()

    def test_a_run_with_comparisons_measured_something(self):
        rng = np.random.default_rng(33)
        b, c = synth(rng, 1.0, n=40)
        g = gate_one(
            stats.compare(b, c, seed=33, n_resamples=RESAMPLES), control=quiet_control()
        )
        assert not g.nothing_measured
