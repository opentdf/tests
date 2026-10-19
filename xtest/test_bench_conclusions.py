"""Unit tests for candidate-to-candidate conclusions and winner eligibility.

Most cases build the analysed result directly, so each rule is pinned by the
verdicts it reads rather than by whatever a simulated runner happened to
produce. One end-to-end case checks the whole path from samples.
"""

from __future__ import annotations

import math
import random

import pytest

from perf import stats
from perf.conclusions import conclude
from perf.runner import BenchConfig, CellResult, analyze, contrast_key

V = stats.Verdict
CFG = BenchConfig(n_resamples=300, gated_metrics=("wall",))


def cell(*candidates: str, cell_id: str = "go-encrypt") -> CellResult:
    ids = ("ref", *candidates)
    return CellResult(
        cell_id=cell_id,
        arm_ids=ids,
        arm_labels={a: f"go@{a}" for a in ids},
        reference="ref",
        samples={a: {"wall": [], "cpu": [], "rss": []} for a in ids},
        n_warmup=0,
        elapsed_s=0.0,
        stopped_because="precision",
        sdk="go",
    )


def comparison(verdict: stats.Verdict, ratio: float = 1.0) -> stats.PairedComparison:
    return stats.PairedComparison(
        n_rounds=30,
        baseline_median=1.0,
        candidate_median=ratio,
        ratio=ratio,
        ci_low=ratio * 0.97,
        ci_high=ratio * 1.03,
        p_value=0.5,
        p_value_faster=0.5,
        verdict=verdict,
    )


def gate(
    result: CellResult,
    pairs: dict[tuple[str, str], stats.Verdict],
    *,
    trustworthy: bool = True,
) -> stats.GateResult:
    g = stats.GateResult(trustworthy=trustworthy, has_candidate_comparisons=True)
    for (a, b), verdict in pairs.items():
        g.comparisons[contrast_key(result.cell_id, a, b, "wall")] = comparison(verdict)
    return g


def only(result: CellResult, g: stats.GateResult):
    (conclusion,) = conclude([result], CFG, g)
    return conclusion


class TestWinner:
    def test_a_clear_difference_names_the_faster_candidate(self):
        r = cell("a", "b")
        c = only(r, gate(r, {("a", "b"): V.FASTER}))
        assert c.winner == "b"
        assert [p.faster() for p in c.pairwise] == ["b"]

    def test_a_tie_has_no_unique_winner(self):
        r = cell("a", "b")
        c = only(r, gate(r, {("a", "b"): V.TIED}))
        assert c.winner is None
        assert "tied" in c.reason

    def test_an_unresolved_third_competitor_blocks_the_winner(self):
        # `a` beats `b`, which is all a point-estimate ranking of the top two
        # would look at. But `a` vs `c` is unresolved, and `c` may be faster.
        r = cell("a", "b", "c")
        c = only(
            r,
            gate(
                r,
                {
                    ("a", "b"): V.SLOWER,
                    ("a", "c"): V.INCONCLUSIVE,
                    ("b", "c"): V.SLOWER,
                },
            ),
        )
        assert c.winner is None
        assert "unresolved" in c.reason and "`c` vs `a`" in c.reason

    def test_beating_every_other_candidate_wins_at_three(self):
        r = cell("a", "b", "c")
        c = only(
            r,
            gate(r, {("a", "b"): V.FASTER, ("a", "c"): V.FASTER, ("b", "c"): V.SLOWER}),
        )
        assert c.winner == "b"

    def test_a_tripped_control_suppresses_the_winner(self):
        # Even with a decisive contrast: a biased harness can produce a
        # narrow interval that looks like a result.
        r = cell("a", "b")
        c = only(r, gate(r, {("a", "b"): V.FASTER}, trustworthy=False))
        assert c.winner is None
        assert "A/A control" in c.reason
        # The pairwise result is still reported, with the limitation.
        assert c.pairwise[0].verdict is V.FASTER

    def test_a_two_arm_run_has_nothing_to_conclude(self):
        r = cell("a")
        assert conclude([r], CFG, gate(r, {})) == []

    def test_control_cells_are_not_concluded_on(self):
        r = cell("a", "b", cell_id="go-aa")
        r.control = True
        assert conclude([r], CFG, gate(r, {("a", "b"): V.FASTER})) == []


def sampled(
    cell_id: str, costs: dict[str, float], *, control: bool, noise: float, seed: int
) -> CellResult:
    rng = random.Random(seed)
    n = 40
    ids = tuple(costs)
    return CellResult(
        cell_id=cell_id,
        arm_ids=ids,
        arm_labels={a: f"go@{a}" for a in ids},
        reference=ids[0],
        samples={
            a: {
                m: [c * math.exp(rng.gauss(0, noise)) for _ in range(n)]
                for m in ("wall", "cpu", "rss")
            }
            for a, c in costs.items()
        },
        n_warmup=0,
        elapsed_s=0.0,
        stopped_because="precision",
        control=control,
        sdk="go",
    )


class TestFromSamples:
    def run(self, costs: dict[str, float], *, with_control: bool = True):
        cfg = BenchConfig(n_resamples=400)
        cells = [sampled("go-encrypt", costs, control=False, noise=0.02, seed=5)]
        if with_control:
            copies = {f"ref#{i}": 1.0 for i in range(len(costs))}
            cells.insert(0, sampled("go-aa", copies, control=True, noise=0.02, seed=4))
        g = analyze(cells, cfg)
        return g, conclude(cells, cfg, g)

    def test_a_clear_winner_is_named_and_the_build_does_not_fail(self):
        g, conclusions = self.run({"ref": 1.0, "a": 1.0, "b": 0.6})
        wall = next(c for c in conclusions if c.metric == "wall")
        assert wall.winner == "b"
        assert not g.should_fail

    def test_no_control_leaves_every_comparison_unresolved(self):
        g, conclusions = self.run({"ref": 1.0, "a": 1.0, "b": 0.6}, with_control=False)
        for c in conclusions:
            assert c.winner is None
            assert all(p.verdict is V.INCONCLUSIVE for p in c.pairwise)


class TestSymmetricRule:
    def comparisons(self, slower: float, *, seed: int = 9):
        rng = random.Random(seed)
        a = [math.exp(rng.gauss(0, 0.02)) for _ in range(40)]
        b = [slower * math.exp(rng.gauss(0, 0.02)) for _ in range(40)]
        return (
            stats.compare(a, b, seed=1, n_resamples=400),
            stats.compare(b, a, seed=1, n_resamples=400),
        )

    def floor(self) -> stats.PairedComparison:
        quiet = [1.0 + 0.001 * i for i in range(40)]
        return stats.compare(quiet, list(reversed(quiet)), seed=1, n_resamples=400)

    @pytest.mark.parametrize(
        ("slower", "forward", "backward"),
        [(1.4, V.SLOWER, V.FASTER), (1.0, V.TIED, V.TIED)],
    )
    def test_reversing_the_direction_preserves_the_conclusion(
        self, slower: float, forward: stats.Verdict, backward: stats.Verdict
    ):
        ab, ba = self.comparisons(slower)
        g = stats.apply_multiplicity_control(
            {"ab": ab, "ba": ba, "aa": self.floor()},
            gated=set(),
            symmetric={"ab", "ba"},
            controls={"ab": "aa", "ba": "aa"},
            control_keys={"aa"},
        )
        assert g.comparisons["ab"].verdict is forward
        assert g.comparisons["ba"].verdict is backward

    def test_candidate_contrasts_do_not_change_the_gates_correction(self):
        ab, _ = self.comparisons(1.2)
        gated_only = stats.apply_multiplicity_control(
            {"gate": ab}, gated={"gate"}, symmetric=set()
        )
        extra = {f"h2h{i}": self.comparisons(1.0 + i / 10, seed=i)[0] for i in range(5)}
        with_pairs = stats.apply_multiplicity_control(
            {"gate": ab} | extra, gated={"gate"}, symmetric=set(extra)
        )
        assert with_pairs.comparisons["gate"].p_adjusted == pytest.approx(
            gated_only.comparisons["gate"].p_adjusted
        )

    def test_each_tail_is_tested_at_half_alpha(self):
        # Two-sided: a difference significant only at alpha in one tail is
        # not enough to rank two candidates with no privileged direction.
        c = stats.PairedComparison(
            n_rounds=30,
            baseline_median=1.0,
            candidate_median=1.5,
            ratio=1.5,
            ci_low=1.3,
            ci_high=1.7,
            p_value=0.04,
            p_value_faster=0.96,
        )
        noise = stats.assess_noise_floor(self.floor())
        verdict, _ = stats._symmetric_verdict_for(  # pyright: ignore[reportPrivateUsage]
            c, 0.04, 0.96, threshold=1.15, alpha=0.05, noise=noise
        )
        assert verdict is V.INCONCLUSIVE
        verdict, _ = stats._symmetric_verdict_for(  # pyright: ignore[reportPrivateUsage]
            c, 0.02, 0.98, threshold=1.15, alpha=0.05, noise=noise
        )
        assert verdict is V.SLOWER
