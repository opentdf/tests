"""Tests for the paired round loop and the gate it feeds.

No subprocesses and no platform: the measurement function and the clock are
both injected, so a whole 40-round cell runs in microseconds and a planted
regression is exactly the size we planted.

The last class here is the one that matters most. A benchmark gate that has
never been shown to catch a planted regression -- and to *ignore* a trivial
one -- is not yet known to work.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from perf import stats
from perf.measure import Sample
from perf.runner import (
    Arm,
    BenchConfig,
    Budget,
    BudgetExhausted,
    Invocation,
    analyze,
    contrast_key,
    run_cell,
)

BASELINE_WALL_S = 1.0
BASELINE_RSS = 100_000_000
BASELINE_CPU = 0.8

#: Arm id of the reference in every cell built here.
REF = "base"


def arm(name: str, output: Path | None = None) -> Arm:
    """An arm whose argv is its own id, so ``FakeRuns`` can recognize it."""
    return Arm(name, f"sdk@{name}", Invocation([name], {}, output))


def key(cell_id: str, metric: str, *, a: str = REF, b: str = "cand") -> str:
    """The contrast key for ``b`` against ``a`` -- the default vs-reference."""
    return contrast_key(cell_id, a, b, metric)


def config(**overrides: object) -> BenchConfig:
    """A config small enough to run fast, still valid for a verdict."""
    base: dict[str, object] = {
        "min_rounds": stats.MIN_USABLE_ROUNDS,
        "max_rounds": 40,
        "warmup": 2,
        "n_resamples": 400,
    }
    return BenchConfig(**(base | overrides))  # pyright: ignore[reportArgumentType]


class FakeRuns:
    """A stand-in for ``measure`` that returns scripted, noisy samples.

    ``ratio_for`` maps the invocation's first argv element to a multiplier on
    the baseline cost, so a caller plants an effect by naming the arms.
    """

    def __init__(
        self,
        ratio_for: dict[str, float],
        *,
        noise: float = 0.05,
        seed: int = 7,
        rss_floor: int = 0,
    ) -> None:
        self.ratio_for = ratio_for
        self.noise = noise
        #: Readings below this clip up to it, the way a real measurement floor
        #: behaves: the number is the floor's, not the command's.
        self.rss_floor = rss_floor
        self.rng = random.Random(seed)
        #: Every argv[0] seen, in call order. The interleaving is visible here.
        self.calls: list[str] = []
        #: Simulated seconds consumed, for tests that drive the clock from it.
        self.elapsed = 0.0

    def __call__(
        self, argv: list[str], env: dict[str, str], **kwargs: object
    ) -> Sample:
        del env, kwargs
        key = argv[0]
        self.calls.append(key)
        ratio = self.ratio_for[key]
        # Lognormal jitter: latency is positive and multiplicative, so noise
        # on the log scale is the honest model of a noisy runner.
        jitter = math.exp(self.rng.gauss(0.0, self.noise))
        wall = BASELINE_WALL_S * ratio * jitter
        self.elapsed += wall
        return Sample(
            wall_ns=int(wall * 1e9),
            cpu_s=BASELINE_CPU * ratio * jitter,
            max_rss_bytes=max(int(BASELINE_RSS * ratio * jitter), self.rss_floor),
            exit_code=0,
            rss_floor_bytes=self.rss_floor,
        )


def clock_from(runs: FakeRuns) -> Callable[[], float]:
    """A clock that advances only as simulated work happens."""
    return lambda: runs.elapsed


def run(
    ratios: float | Mapping[str, float],
    *,
    cfg: BenchConfig | None = None,
    noise: float = 0.05,
    seed: int = 7,
    cell_id: str = "cell",
    control: bool = False,
    sdk: str = "",
    rss_floor: int = 0,
):
    """Run one cell whose arms cost ``ratios`` times the reference.

    A bare float is the two-arm shorthand: a reference at 1.0 and one
    candidate at that ratio. A mapping names the arms, and the first key is
    the reference -- which is how a bake-off is set up here.
    """
    costs = (
        {REF: 1.0, "cand": float(ratios)}
        if isinstance(ratios, (int, float))
        else dict(ratios)
    )
    runs = FakeRuns(costs, noise=noise, seed=seed, rss_floor=rss_floor)
    result = run_cell(
        cell_id,
        [arm(name) for name in costs],
        cfg or config(),
        control=control,
        sdk=sdk,
        clock=clock_from(runs),
        run=runs,
    )
    return result, runs


class TestRoundLoop:
    def test_arms_are_paired_every_round(self):
        _, runs = run(1.0)
        assert runs.calls.count(REF) == runs.calls.count("cand")
        # Every consecutive pair holds one of each: that is what pairing means.
        pairs = [set(runs.calls[i : i + 2]) for i in range(0, len(runs.calls), 2)]
        assert all(p == {REF, "cand"} for p in pairs)

    def test_every_arm_runs_once_per_round_at_three_arms(self):
        # The whole reason a bake-off is answerable: all three arms share a
        # round, so the a-vs-b contrast is a within-round ratio like any other.
        _, runs = run({REF: 1.0, "a": 1.1, "b": 1.2})
        rounds = [set(runs.calls[i : i + 3]) for i in range(0, len(runs.calls), 3)]
        assert all(r == {REF, "a", "b"} for r in rounds)

    def test_order_within_rounds_is_shuffled(self):
        _, runs = run(1.0)
        firsts = runs.calls[::2]
        assert REF in firsts and "cand" in firsts, (
            "a fixed within-round order lets the second arm inherit the first "
            "one's cache state"
        )

    def test_all_three_arms_take_turns_going_first(self):
        _, runs = run({REF: 1.0, "a": 1.0, "b": 1.0})
        assert set(runs.calls[::3]) == {REF, "a", "b"}, (
            "an arm pinned to one slot in the round inherits the same cache "
            "state every time, which is a confounder and not a measurement"
        )

    def test_rejects_a_single_arm(self):
        with pytest.raises(ValueError, match="at least two arms"):
            run_cell("cell", [arm(REF)], config())

    def test_rejects_colliding_arm_ids(self):
        # Ids key the sample vectors, so a collision would interleave two
        # builds' measurements into one arm and compare it with itself.
        with pytest.raises(ValueError, match="unique"):
            run_cell("cell", [arm(REF), arm(REF)], config())

    def test_rejects_a_reference_that_is_not_an_arm(self):
        with pytest.raises(ValueError, match="reference"):
            run_cell("cell", [arm(REF), arm("cand")], config(), reference="other")

    def test_warmup_rounds_are_discarded(self):
        cfg = config(warmup=3, max_rounds=stats.MIN_USABLE_ROUNDS)
        result, runs = run(1.0, cfg=cfg)
        assert result.n_rounds == stats.MIN_USABLE_ROUNDS
        assert result.n_warmup == 3
        # Warm-up rounds ran, they just are not in the samples.
        assert len(runs.calls) == 2 * (3 + stats.MIN_USABLE_ROUNDS)

    def test_interleaving_is_reproducible_for_a_seed(self):
        _, a = run(1.0)
        _, b = run(1.0)
        assert a.calls == b.calls

    def test_cells_do_not_share_an_interleaving(self):
        _, a = run(1.0, cell_id="encrypt-1KiB")
        _, b = run(1.0, cell_id="decrypt-1KiB")
        assert a.calls != b.calls, "cells sharing one order would correlate their noise"

    def test_output_is_removed_before_each_run(self, tmp_path: Path):
        out = tmp_path / "out.tdf"
        out.write_bytes(b"stale")
        seen: list[bool] = []
        runs = FakeRuns({REF: 1.0, "cand": 1.0})

        def observe(argv: list[str], env: dict[str, str], **kwargs: object) -> Sample:
            if argv[0] == REF:
                # What the arm that owns this output sees when it starts.
                seen.append(out.exists())
                out.write_bytes(b"produced")
            return runs(argv, env, **kwargs)

        run_cell(
            "cell",
            [arm(REF, out), arm("cand")],
            config(max_rounds=stats.MIN_USABLE_ROUNDS),
            clock=clock_from(runs),
            run=observe,
        )
        assert not any(seen), "a stale output makes round 2 measure an overwrite"

    def test_samples_are_collected_for_every_metric(self):
        result, _ = run(1.0)
        for name in (REF, "cand"):
            for metric in ("wall", "cpu", "rss"):
                assert len(result.samples[name][metric]) == result.n_rounds

    def test_records_its_arms_and_which_one_is_the_reference(self):
        result, _ = run({REF: 1.0, "a": 1.0, "b": 1.0})
        assert result.arm_ids == (REF, "a", "b")
        assert result.reference == REF
        assert result.arm_labels == {REF: "sdk@base", "a": "sdk@a", "b": "sdk@b"}

    def test_contrast_pairs_cover_every_pair_once(self):
        result, _ = run({REF: 1.0, "a": 1.0, "b": 1.0})
        # Reference contrasts first, then the head-to-head. A pair and its
        # inverse are the same measurement, so only one of each appears.
        assert result.contrast_pairs() == [(REF, "a"), (REF, "b"), ("a", "b")]

    def test_contrast_direction_is_b_over_a(self):
        result, _ = run({REF: 1.0, "slow": 1.5}, noise=0.01)
        cfg = config()
        assert result.contrast(REF, "slow", "wall", cfg).ratio == pytest.approx(
            1.5, rel=0.1
        )
        assert result.contrast("slow", REF, "wall", cfg).ratio == pytest.approx(
            1 / 1.5, rel=0.1
        )


class TestStopping:
    def test_stops_early_on_precision_when_quiet(self):
        result, _ = run(1.0, noise=0.005)
        assert result.stopped_because == "precision"
        assert result.n_rounds < 40

    def test_runs_to_max_rounds_when_noisy(self):
        result, _ = run(1.0, noise=0.4)
        assert result.stopped_because == "max_rounds"
        assert result.n_rounds == 40

    def test_never_stops_before_min_rounds(self):
        cfg = config(min_rounds=25, max_rounds=40)
        result, _ = run(1.0, cfg=cfg, noise=0.0001)
        assert result.n_rounds >= 25

    def test_precision_waits_for_the_slowest_contrast_to_converge(self):
        # One quiet candidate and one noisy one. Stopping as soon as *some*
        # contrast is precise would leave the noisy arm unresolved with budget
        # still on the table -- and at K arms the slowest contrast to converge
        # is exactly the one someone is waiting on.
        cfg = config(max_rounds=40)
        quiet, _ = run({REF: 1.0, "cand": 1.0}, cfg=cfg, noise=0.005)
        assert quiet.stopped_because == "precision"

        runs = FakeRuns({REF: 1.0, "quiet": 1.0, "noisy": 1.0}, noise=0.005)
        real_call = runs.__call__

        def jittery(argv: list[str], env: dict[str, str], **kwargs: object) -> Sample:
            sample = real_call(argv, env, **kwargs)
            if argv[0] != "noisy":
                return sample
            spike = math.exp(runs.rng.gauss(0.0, 0.5))
            return Sample(
                wall_ns=int(sample.wall_ns * spike),
                cpu_s=sample.cpu_s * spike,
                max_rss_bytes=int(sample.max_rss_bytes * spike),
                exit_code=0,
            )

        mixed = run_cell(
            "cell",
            [arm(REF), arm("quiet"), arm("noisy")],
            cfg,
            clock=clock_from(runs),
            run=jittery,
        )
        assert mixed.stopped_because == "max_rounds", (
            "the loop stopped on the quiet contrast and left the noisy one unresolved"
        )

    def test_deadline_stops_the_loop(self):
        runs = FakeRuns({REF: 1.0, "cand": 1.0}, noise=0.3)
        clock = clock_from(runs)
        result = run_cell(
            "cell",
            [arm(REF), arm("cand")],
            config(warmup=0, max_rounds=200),
            deadline=clock() + 60.0,  # each round costs ~2 simulated seconds
            clock=clock,
            run=runs,
        )
        assert result.stopped_because == "budget"
        assert result.elapsed_s <= 60.0, "a round we could not finish was started"

    def test_a_three_arm_round_costs_three_invocations_of_budget(self):
        # Rounds get more expensive as arms are added, which is the whole
        # reason the default budget scales with K.
        runs = FakeRuns({REF: 1.0, "a": 1.0, "b": 1.0}, noise=0.3)
        clock = clock_from(runs)
        result = run_cell(
            "cell",
            [arm(REF), arm("a"), arm("b")],
            config(warmup=0, max_rounds=200),
            deadline=clock() + 60.0,  # each round now costs ~3 simulated seconds
            clock=clock,
            run=runs,
        )
        assert result.stopped_because == "budget"
        assert len(runs.calls) == 3 * result.n_rounds
        assert result.n_rounds < 30, "three-arm rounds cost more than two-arm ones"

    def test_warmup_gives_up_when_the_budget_runs_out(self):
        # The budget's end is absolute, so warm-ups that run past it are
        # spending the *following* cells' time -- and then reaching the
        # measured loop with nothing left, paying the whole cost of the cell
        # for no data at all. Stop at the deadline and say where it went.
        runs = FakeRuns({REF: 1.0, "cand": 1.0})
        clock = clock_from(runs)
        with pytest.raises(BudgetExhausted, match="warm-up"):
            run_cell(
                "cell",
                [arm(REF), arm("cand")],
                config(warmup=10),
                deadline=clock() + 4.0,  # each round costs ~2 simulated seconds
                clock=clock,
                run=runs,
            )
        assert len(runs.calls) < 2 * 10, "warm-up ran past its own deadline"

    def test_budget_below_min_usable_rounds_refuses_a_verdict(self):
        runs = FakeRuns({REF: 1.0, "cand": 1.0})
        clock = clock_from(runs)
        with pytest.raises(BudgetExhausted, match="below the"):
            run_cell(
                "cell",
                [arm(REF), arm("cand")],
                config(warmup=0),
                deadline=clock() + 4.0,
                clock=clock,
                run=runs,
            )


class TestBenchConfigValidation:
    def test_rejects_min_rounds_below_the_usable_floor(self):
        with pytest.raises(ValueError, match="min_rounds"):
            BenchConfig(min_rounds=stats.MIN_USABLE_ROUNDS - 1)

    def test_rejects_max_below_min(self):
        with pytest.raises(ValueError, match="max_rounds"):
            BenchConfig(min_rounds=20, max_rounds=10)

    def test_rejects_a_threshold_that_is_not_a_ratio(self):
        with pytest.raises(ValueError, match="ratio above 1.0"):
            BenchConfig(threshold=0.9)

    def test_rejects_unknown_gated_metrics(self):
        with pytest.raises(ValueError, match="unknown gated metrics"):
            BenchConfig(gated_metrics=("wall", "iops"))

    def test_target_half_width_is_a_third_of_the_log_threshold(self):
        cfg = BenchConfig(threshold=1.15)
        assert cfg.target_half_width_log == pytest.approx(math.log(1.15) / 3)


class TestBudget:
    def test_divides_remaining_time_evenly(self):
        now = 1000.0
        budget = Budget(300.0, 3, clock=lambda: now)
        assert budget.next_deadline() == pytest.approx(now + 100.0)

    def test_unused_time_flows_to_later_cells(self):
        now = [0.0]
        budget = Budget(300.0, 3, clock=lambda: now[0])
        budget.next_deadline()
        now[0] = 10.0  # the first cell stopped early on precision
        # 290s left over two cells, not the 100s it would have got by
        # dividing up front.
        assert budget.next_deadline() == pytest.approx(155.0)

    def test_never_hands_out_a_deadline_in_the_past(self):
        now = [0.0]
        budget = Budget(10.0, 2, clock=lambda: now[0])
        now[0] = 60.0
        assert budget.next_deadline() == pytest.approx(60.0)
        assert budget.remaining_s == 0.0

    def test_rejects_a_budget_with_no_cells(self):
        with pytest.raises(ValueError, match="at least one cell"):
            Budget(10.0, 0)


class TestGateOnPlantedEffects:
    """The critical check: does the gate fire when it should, and only then?

    Each case runs a real cell through the real statistics; only the
    measurement is simulated. The A/A control cell is included exactly as a
    live run would include it, so the noise floor is assessed the same way.
    """

    def gate(self, candidate_ratio: float, *, noise: float = 0.05, seed: int = 11):
        cfg = config(max_rounds=40)
        control, _ = run(
            1.0, cfg=cfg, noise=noise, seed=seed, cell_id="aa", control=True
        )
        measured, _ = run(
            candidate_ratio, cfg=cfg, noise=noise, seed=seed + 1, cell_id="encrypt"
        )
        return analyze([control, measured], cfg)

    def test_planted_25_percent_slowdown_is_caught(self):
        gate = self.gate(1.25)
        assert gate.should_fail
        assert key("encrypt", "wall") in gate.regressions
        c = gate.comparisons[key("encrypt", "wall")]
        assert c.verdict is stats.Verdict.REGRESSION
        assert c.ci_low > 1.15, "the interval must exclude the threshold, not just 1.0"
        assert c.ratio == pytest.approx(1.25, rel=0.1)

    def test_planted_3_percent_slowdown_is_ignored(self):
        gate = self.gate(1.03)
        assert not gate.should_fail
        assert (
            gate.comparisons[key("encrypt", "wall")].verdict
            is not stats.Verdict.REGRESSION
        )

    def test_no_effect_does_not_fire(self):
        gate = self.gate(1.0)
        assert not gate.should_fail
        assert not gate.regressions

    def test_planted_speedup_is_reported_not_failed(self):
        gate = self.gate(0.7)
        assert not gate.should_fail
        assert (
            gate.comparisons[key("encrypt", "wall")].verdict is stats.Verdict.IMPROVED
        )
        assert key("encrypt", "wall") in gate.improvements

    def test_the_control_cell_never_fails_the_build(self):
        # Both arms of the control are the same build, so any verdict it
        # reaches is the harness's own error, not a regression in anything.
        gate = self.gate(1.25)
        assert not any(k.startswith("aa/") for k in gate.regressions)

    def test_a_regression_in_an_ungated_metric_does_not_fail(self):
        cfg = config(max_rounds=40, gated_metrics=("wall",))
        control, _ = run(1.0, cfg=cfg, cell_id="aa", control=True)
        measured, _ = run(1.4, cfg=cfg, seed=12, cell_id="encrypt")
        gate = analyze([control, measured], cfg)
        # CPU time moved with everything else and is reported as such; it
        # simply is not allowed to turn the build red.
        assert (
            gate.comparisons[key("encrypt", "cpu")].verdict is stats.Verdict.REGRESSION
        )
        assert key("encrypt", "cpu") not in gate.regressions
        assert key("encrypt", "wall") in gate.regressions

    def test_rss_pinned_to_the_measurement_floor_cannot_report_pass(self):
        # A command whose peak sits at the floor is not measured, it is
        # clipped -- and both arms clip to the same number. That produces a
        # ratio of exactly 1.000 with a vanishing interval, which is the most
        # convincing PASS the harness can emit and carries no information.
        cfg = config(max_rounds=40)
        floor = 4 * BASELINE_RSS
        control, _ = run(1.0, cfg=cfg, cell_id="aa", control=True, rss_floor=floor)
        measured, _ = run(1.25, cfg=cfg, seed=12, cell_id="encrypt", rss_floor=floor)
        gate = analyze([control, measured], cfg)

        rss = gate.comparisons[key("encrypt", "rss")]
        assert rss.ratio == pytest.approx(1.0), "the floor clipped both arms"
        assert rss.verdict is stats.Verdict.INCONCLUSIVE
        assert "floor" in rss.note
        assert key("encrypt", "rss") not in gate.regressions
        assert key("encrypt", "rss") not in gate.improvements
        # Wall clock is untouched by a memory floor and still does its job.
        assert key("encrypt", "wall") in gate.regressions

    def test_rss_above_the_floor_is_still_gated(self):
        cfg = config(max_rounds=40)
        control, _ = run(
            1.0, cfg=cfg, cell_id="aa", control=True, rss_floor=BASELINE_RSS // 10
        )
        measured, _ = run(
            1.25, cfg=cfg, seed=12, cell_id="encrypt", rss_floor=BASELINE_RSS // 10
        )
        gate = analyze([control, measured], cfg)
        assert key("encrypt", "rss") in gate.regressions

    def test_each_sdk_is_judged_against_its_own_control(self):
        # One control per SDK: they are different harness paths with different
        # floors. Judging go's cells against java's control judges them
        # against a noise floor that was never measured for them -- and with
        # a single run-level control, whichever SDK happened to be last wins.
        cfg = config(max_rounds=40)
        go_aa, _ = run(
            1.0, cfg=cfg, noise=0.02, cell_id="go-aa", control=True, sdk="go"
        )
        go_cell, _ = run(
            1.0, cfg=cfg, noise=0.02, seed=12, cell_id="go-encrypt", sdk="go"
        )
        # java's runner was noisy enough that it could not resolve the
        # threshold; its cells must not claim a clean bill of health.
        java_aa, _ = run(
            1.0,
            cfg=cfg,
            noise=0.5,
            seed=13,
            cell_id="java-aa",
            control=True,
            sdk="java",
        )
        java_cell, _ = run(
            1.0, cfg=cfg, noise=0.02, seed=14, cell_id="java-encrypt", sdk="java"
        )
        gate = analyze([go_aa, go_cell, java_aa, java_cell], cfg)

        assert len(gate.noise_by_control) == 2, "one noise floor per SDK"
        assert gate.comparisons[key("go-encrypt", "wall")].verdict is stats.Verdict.PASS
        assert (
            gate.comparisons[key("java-encrypt", "wall")].verdict
            is stats.Verdict.INCONCLUSIVE
        ), "java's own control had no power, whatever go's control managed"

    def test_a_run_with_no_control_cannot_report_pass(self):
        cfg = config(max_rounds=40)
        measured, _ = run(1.0, cfg=cfg, cell_id="encrypt")
        gate = analyze([measured], cfg)
        assert gate.noise is not None and gate.noise.underpowered
        assert (
            gate.comparisons[key("encrypt", "wall")].verdict
            is stats.Verdict.INCONCLUSIVE
        )
        assert not gate.should_fail, "an unassessed run warns; it does not fail"


class TestGateAtThreeArms:
    """What the extra arms buy, and what they must not be allowed to do.

    Every contrast here is a within-round ratio measured on one runner, which
    is the only reason a candidate-versus-candidate question is answerable at
    all. But only the vs-reference contrasts may fail a build: a bake-off
    ranks implementations, it does not decide whether the branch is shippable.
    """

    def gate(self, costs: Mapping[str, float], *, noise: float = 0.05, seed: int = 11):
        cfg = config(max_rounds=40)
        control_costs = dict.fromkeys(costs, 1.0)
        control, _ = run(
            control_costs, cfg=cfg, noise=noise, seed=seed, cell_id="aa", control=True
        )
        measured, _ = run(costs, cfg=cfg, noise=noise, seed=seed + 1, cell_id="encrypt")
        return analyze([control, measured], cfg)

    def test_both_candidates_are_gated_against_the_reference(self):
        gate = self.gate({REF: 1.0, "slow": 1.3, "quick": 1.0})
        assert gate.should_fail
        assert key("encrypt", "wall", b="slow") in gate.regressions
        assert key("encrypt", "wall", b="quick") not in gate.regressions

    def test_a_head_to_head_gap_never_fails_the_build(self):
        # Neither candidate regressed against the reference; one is simply
        # slower than the other. That is a ranking, and rankings do not turn
        # the build red -- invariant #9.
        gate = self.gate({REF: 1.3, "slow": 1.3, "quick": 1.0})
        h2h = key("encrypt", "wall", a="slow", b="quick")
        assert gate.comparisons[h2h].verdict is stats.Verdict.FASTER
        assert not gate.should_fail
        assert h2h not in gate.regressions and h2h not in gate.improvements

    def test_a_head_to_head_is_judged_symmetrically(self):
        # The one-sided vocabulary would call this PASS or REGRESSION, both of
        # which presume an incumbent. Between two candidates there is none.
        gate = self.gate({REF: 1.0, "a": 1.0, "b": 1.3})
        h2h = gate.comparisons[key("encrypt", "wall", a="a", b="b")]
        assert h2h.verdict is stats.Verdict.SLOWER
        assert h2h.verdict not in {stats.Verdict.PASS, stats.Verdict.REGRESSION}

    def test_indistinguishable_candidates_are_tied_not_passed(self):
        # PASS is a one-sided claim -- "not slower". For a bake-off the answer
        # worth reporting is that the two are the same, and TIED says so.
        gate = self.gate({REF: 1.0, "a": 1.0, "b": 1.0}, noise=0.01)
        assert (
            gate.comparisons[key("encrypt", "wall", a="a", b="b")].verdict
            is stats.Verdict.TIED
        )

    def test_head_to_head_covers_ungated_metrics_too(self):
        # "Which arm is faster" has no privileged direction on cpu either, and
        # none of these gate, so they all share the symmetric vocabulary.
        gate = self.gate({REF: 1.0, "a": 1.0, "b": 1.3})
        assert gate.comparisons[key("encrypt", "cpu", a="a", b="b")].verdict in {
            stats.Verdict.FASTER,
            stats.Verdict.SLOWER,
            stats.Verdict.TIED,
            stats.Verdict.INCONCLUSIVE,
        }

    def test_a_decided_head_to_head_is_recorded_for_ranking(self):
        gate = self.gate({REF: 1.0, "slow": 1.4, "quick": 1.0})
        # ``ranked`` carries the material a report turns into a winner; it is
        # keys only, because at this layer an arm id is opaque.
        assert key("encrypt", "wall", a="slow", b="quick") in gate.ranked
        assert not any(
            k in gate.regressions or k in gate.improvements for k in gate.ranked
        )

    def test_the_control_yields_one_contrast_per_pair(self):
        gate = self.gate({REF: 1.0, "a": 1.0, "b": 1.0})
        aa = [
            k for k in gate.comparisons if k.startswith("aa/") and k.endswith("/wall")
        ]
        assert len(aa) == 3, "C(3,2) pairs, not one -- arm 3 drifts further than arm 2"

    def test_the_noise_floor_is_the_worst_control_pair(self):
        # A 2-arm control measures adjacent invocations only, and so understates
        # the drift carried by the widest contrast the run actually judges.
        gate = self.gate({REF: 1.0, "a": 1.0, "b": 1.0})
        aa = [
            k for k in gate.comparisons if k.startswith("aa/") and k.endswith("/wall")
        ]
        assert len(gate.noise_by_control) == 1, "exactly one of the pairs is the floor"
        assert gate.noise is not None
        widest = max(
            stats.assess_noise_floor(gate.comparisons[k]).width_ratio for k in aa
        )
        assert gate.noise.width_ratio == pytest.approx(widest)
