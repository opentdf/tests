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
from collections.abc import Callable
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
    run_cell,
)

BASELINE_WALL_S = 1.0
BASELINE_RSS = 100_000_000
BASELINE_CPU = 0.8


def arm(role: str, key: str, output: Path | None = None) -> Arm:
    """An arm whose argv is a single token, so ``FakeRuns`` can recognize it.

    ``role`` is what the runner keys samples by ("baseline"/"candidate");
    ``key`` is the stand-in for the build.
    """
    return Arm(role, f"sdk@{key}", Invocation([key], {}, output))


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
    ratio: float,
    *,
    cfg: BenchConfig | None = None,
    noise: float = 0.05,
    seed: int = 7,
    cell_id: str = "cell",
    control: bool = False,
    sdk: str = "",
    rss_floor: int = 0,
):
    """Run one cell where the candidate costs ``ratio`` times the baseline."""
    runs = FakeRuns(
        {"base": 1.0, "cand": ratio}, noise=noise, seed=seed, rss_floor=rss_floor
    )
    result = run_cell(
        cell_id,
        arm("baseline", "base"),
        arm("candidate", "cand"),
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
        assert runs.calls.count("base") == runs.calls.count("cand")
        # Every consecutive pair holds one of each: that is what pairing means.
        pairs = [set(runs.calls[i : i + 2]) for i in range(0, len(runs.calls), 2)]
        assert all(p == {"base", "cand"} for p in pairs)

    def test_order_within_rounds_is_shuffled(self):
        _, runs = run(1.0)
        firsts = runs.calls[::2]
        assert "base" in firsts and "cand" in firsts, (
            "a fixed within-round order lets the second arm inherit the first "
            "one's cache state"
        )

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
        runs = FakeRuns({"base": 1.0, "cand": 1.0})

        def observe(argv: list[str], env: dict[str, str], **kwargs: object) -> Sample:
            if argv[0] == "base":
                # What the arm that owns this output sees when it starts.
                seen.append(out.exists())
                out.write_bytes(b"produced")
            return runs(argv, env, **kwargs)

        run_cell(
            "cell",
            arm("baseline", "base", out),
            arm("candidate", "cand"),
            config(max_rounds=stats.MIN_USABLE_ROUNDS),
            clock=clock_from(runs),
            run=observe,
        )
        assert not any(seen), "a stale output makes round 2 measure an overwrite"

    def test_samples_are_collected_for_every_metric(self):
        result, _ = run(1.0)
        for name in ("baseline", "candidate"):
            for metric in ("wall", "cpu", "rss"):
                assert len(result.samples[name][metric]) == result.n_rounds


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

    def test_deadline_stops_the_loop(self):
        runs = FakeRuns({"base": 1.0, "cand": 1.0}, noise=0.3)
        clock = clock_from(runs)
        result = run_cell(
            "cell",
            arm("baseline", "base"),
            arm("candidate", "cand"),
            config(warmup=0, max_rounds=200),
            deadline=clock() + 60.0,  # each round costs ~2 simulated seconds
            clock=clock,
            run=runs,
        )
        assert result.stopped_because == "budget"
        assert result.elapsed_s <= 60.0, "a round we could not finish was started"

    def test_warmup_gives_up_when_the_budget_runs_out(self):
        # The budget's end is absolute, so warm-ups that run past it are
        # spending the *following* cells' time -- and then reaching the
        # measured loop with nothing left, paying the whole cost of the cell
        # for no data at all. Stop at the deadline and say where it went.
        runs = FakeRuns({"base": 1.0, "cand": 1.0})
        clock = clock_from(runs)
        with pytest.raises(BudgetExhausted, match="warm-up"):
            run_cell(
                "cell",
                arm("baseline", "base"),
                arm("candidate", "cand"),
                config(warmup=10),
                deadline=clock() + 4.0,  # each round costs ~2 simulated seconds
                clock=clock,
                run=runs,
            )
        assert len(runs.calls) < 2 * 10, "warm-up ran past its own deadline"

    def test_budget_below_min_usable_rounds_refuses_a_verdict(self):
        runs = FakeRuns({"base": 1.0, "cand": 1.0})
        clock = clock_from(runs)
        with pytest.raises(BudgetExhausted, match="below the"):
            run_cell(
                "cell",
                arm("baseline", "base"),
                arm("candidate", "cand"),
                config(warmup=0),
                deadline=clock() + 4.0,
                clock=clock,
                run=runs,
            )

    def test_budget_below_configured_minimum_refuses_a_verdict(self):
        runs = FakeRuns({"base": 1.0, "cand": 1.0}, noise=0.0)
        clock = clock_from(runs)
        with pytest.raises(BudgetExhausted, match="configured minimum of 10"):
            run_cell(
                "cell",
                arm("baseline", "base"),
                arm("candidate", "cand"),
                config(min_rounds=10, warmup=0),
                # Five complete rounds fit. That clears the statistical hard
                # floor but not the configured minimum for this experiment.
                deadline=11.0,
                clock=clock,
                run=runs,
            )

    def test_deadline_caps_invocations_and_discards_a_partial_round(self):
        elapsed = [0.0]
        calls: list[str] = []
        timeouts: list[float] = []
        candidate_walls = iter((0.5, 2.0, 0.6, 1.8, 1.0, 1.0))

        def scripted_run(
            argv: list[str],
            _env: dict[str, str],
            *,
            timeout_s: float,
        ) -> Sample:
            calls.append(argv[0])
            timeouts.append(timeout_s)
            # Five ordinary two-second rounds, then the first arm of round six
            # overruns what remains. That incomplete round must be discarded.
            elapsed[0] += 1.0 if len(calls) <= 10 else 3.0
            wall = 1.0 if argv[0] == "base" else next(candidate_walls)
            return Sample(
                wall_ns=int(wall * 1e9),
                cpu_s=wall,
                max_rss_bytes=int(BASELINE_RSS * wall),
                exit_code=0,
            )

        result = run_cell(
            "cell",
            arm("baseline", "base"),
            arm("candidate", "cand"),
            config(warmup=0, max_rounds=6),
            deadline=12.5,
            clock=lambda: elapsed[0],
            run=scripted_run,
        )

        assert result.stopped_because == "budget"
        assert result.n_rounds == 5
        assert len(calls) == 11, "round six started but only one arm completed"
        assert timeouts[-1] == pytest.approx(2.5), "timeout is remaining budget"


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
        assert "encrypt/wall" in gate.regressions
        c = gate.comparisons["encrypt/wall"]
        assert c.verdict is stats.Verdict.REGRESSION
        assert c.ci_low > 1.15, "the interval must exclude the threshold, not just 1.0"
        assert c.ratio == pytest.approx(1.25, rel=0.1)

    def test_planted_3_percent_slowdown_is_ignored(self):
        gate = self.gate(1.03)
        assert not gate.should_fail
        assert gate.comparisons["encrypt/wall"].verdict is not stats.Verdict.REGRESSION

    def test_no_effect_does_not_fire(self):
        gate = self.gate(1.0)
        assert not gate.should_fail
        assert not gate.regressions

    def test_planted_speedup_is_reported_not_failed(self):
        gate = self.gate(0.7)
        assert not gate.should_fail
        assert gate.comparisons["encrypt/wall"].verdict is stats.Verdict.IMPROVED
        assert "encrypt/wall" in gate.improvements

    def test_the_control_cell_never_fails_the_build(self):
        # Both arms of the control are the same build, so any verdict it
        # reaches is the harness's own error, not a regression in anything.
        gate = self.gate(1.25)
        assert not any(k.startswith("aa/") for k in gate.regressions)

    def test_control_only_run_measured_nothing_about_the_candidate(self):
        cfg = config(max_rounds=40)
        control, _ = run(1.0, cfg=cfg, cell_id="aa", control=True, sdk="go")
        gate = analyze([control], cfg)

        assert gate.nothing_measured
        assert "NOTHING MEASURED" in gate.summary

    def test_control_plus_candidate_counts_as_measured(self):
        cfg = config(max_rounds=40)
        control, _ = run(1.0, cfg=cfg, cell_id="aa", control=True, sdk="go")
        measured, _ = run(1.0, cfg=cfg, cell_id="encrypt", sdk="go")
        gate = analyze([control, measured], cfg)

        assert not gate.nothing_measured

    def test_a_regression_in_an_ungated_metric_does_not_fail(self):
        cfg = config(max_rounds=40, gated_metrics=("wall",))
        control, _ = run(1.0, cfg=cfg, cell_id="aa", control=True)
        measured, _ = run(1.4, cfg=cfg, seed=12, cell_id="encrypt")
        gate = analyze([control, measured], cfg)
        # CPU time moved with everything else and is reported as such; it
        # simply is not allowed to turn the build red.
        assert gate.comparisons["encrypt/cpu"].verdict is stats.Verdict.REGRESSION
        assert "encrypt/cpu" not in gate.regressions
        assert "encrypt/wall" in gate.regressions

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

        rss = gate.comparisons["encrypt/rss"]
        assert rss.ratio == pytest.approx(1.0), "the floor clipped both arms"
        assert rss.verdict is stats.Verdict.INCONCLUSIVE
        assert "floor" in rss.note
        assert "encrypt/rss" not in gate.regressions
        assert "encrypt/rss" not in gate.improvements
        # Wall clock is untouched by a memory floor and still does its job.
        assert "encrypt/wall" in gate.regressions

    def test_rss_above_the_floor_is_still_gated(self):
        cfg = config(max_rounds=40)
        control, _ = run(
            1.0, cfg=cfg, cell_id="aa", control=True, rss_floor=BASELINE_RSS // 10
        )
        measured, _ = run(
            1.25, cfg=cfg, seed=12, cell_id="encrypt", rss_floor=BASELINE_RSS // 10
        )
        gate = analyze([control, measured], cfg)
        assert "encrypt/rss" in gate.regressions

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
        assert gate.comparisons["go-encrypt/wall"].verdict is stats.Verdict.PASS
        assert (
            gate.comparisons["java-encrypt/wall"].verdict is stats.Verdict.INCONCLUSIVE
        ), "java's own control had no power, whatever go's control managed"

    def test_a_run_with_no_control_cannot_report_pass(self):
        cfg = config(max_rounds=40)
        measured, _ = run(1.0, cfg=cfg, cell_id="encrypt")
        gate = analyze([measured], cfg)
        assert gate.noise is not None and gate.noise.underpowered
        assert gate.comparisons["encrypt/wall"].verdict is stats.Verdict.INCONCLUSIVE
        assert not gate.should_fail, "an unassessed run warns; it does not fail"
