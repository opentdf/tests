"""Collecting benchmark results and turning them into artifacts.

Cells do not assert. Each one records its raw samples here and moves on,
because the decision rule needs every cell before it can decide anything:
the multiplicity correction is computed across the run, and the A/A control
can invalidate the whole thing. The gate therefore runs once, at session
finish, from :meth:`BenchmarkRecorder.gate`.

Two artifacts come out:

- A JSON file per run, holding **every raw per-round sample** alongside the
  derived statistics. Re-analysing a surprising result offline is the
  difference between understanding a red build and re-running a 30-minute job
  to look at the same numbers again.
- A markdown table for ``$GITHUB_STEP_SUMMARY``, so the answer is on the job
  page rather than buried in log output.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from perf import stats
from perf.cells import BenchCell
from perf.measure import METRIC_LABELS, METRICS, format_metric
from perf.runner import BenchConfig, CellResult, analyze, contrast_key

#: Cells the session intends to run. Set by the conftest parametrizer, read by
#: the budget and arm-resolution fixtures.
CELLS_KEY: pytest.StashKey[list[BenchCell]] = pytest.StashKey()

#: The session's recorder, reachable from both fixtures and session hooks.
RECORDER_KEY: pytest.StashKey[BenchmarkRecorder] = pytest.StashKey()


def recorder_for(config: pytest.Config) -> BenchmarkRecorder:
    """Return the session's recorder, creating it on first use."""
    existing = config.stash.get(RECORDER_KEY, None)
    if existing is not None:
        return existing
    recorder = BenchmarkRecorder()
    config.stash[RECORDER_KEY] = recorder
    return recorder


@dataclass(slots=True)
class BenchmarkRecorder:
    """Session-wide collector for cell results, skips, and failures."""

    results: list[CellResult] = field(default_factory=list)
    #: cell id -> why it did not run. Reported so a quiet run is visibly
    #: quiet rather than indistinguishable from a clean one.
    skipped: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def record(self, result: CellResult) -> None:
        self.results.append(result)

    def skip(self, cell_id: str, reason: str) -> None:
        self.skipped[cell_id] = reason

    def gate(self, config: BenchConfig) -> stats.GateResult:
        return analyze(self.results, config)


@dataclass(frozen=True, slots=True)
class BakeOff:
    """One cell's head-to-head ranking of the non-reference arms.

    The gate answers "did anything get slower than the reference". A bake-off
    answers a different question -- "of these candidate implementations, which
    should we merge" -- and it is deliberately kept out of the gate: ranking
    two candidates against each other says nothing about whether either is a
    regression, and a build must not go red because the runner-up lost.
    """

    cell_id: str
    metric: str
    #: Candidate arm ids, best first, ordered by ratio against the reference.
    order: list[str]
    #: The contrast between the top two candidates, as configured order.
    head_to_head: str
    verdict: stats.Verdict
    #: The winning arm id, or None when the top two could not be separated.
    winner: str | None
    detail: str


def bake_offs(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> list[BakeOff]:
    """Rank the candidates in every cell that ran more than one of them.

    Empty for a two-arm run, which has nothing to rank: there is one candidate
    and the gate has already said everything there is to say about it.

    A winner is named only when the top pair's own contrast came back FASTER
    or SLOWER. A TIED top pair reports that the two are indistinguishable,
    which is a real answer and frequently the correct one -- picking the arm
    whose point estimate happened to land lower would be reading noise as a
    result.
    """
    out: list[BakeOff] = []
    for r in recorder.results:
        candidates = [a for a in r.arm_ids if a != r.reference]
        if r.control or len(candidates) < 2:
            continue
        for metric in config.gated_metrics:
            ranked = _rank_candidates(r, candidates, metric, gate)
            if len(ranked) < 2:
                continue
            # Head-to-head keys exist in configured order only, so recover
            # that order for the top two rather than assuming the ranking's.
            top = [a for a in candidates if a in ranked[:2]]
            key = contrast_key(r.cell_id, top[0], top[1], metric)
            c = gate.comparisons.get(key)
            if c is None:
                continue
            winner = {
                stats.Verdict.FASTER: top[1],
                stats.Verdict.SLOWER: top[0],
            }.get(c.verdict)
            out.append(
                BakeOff(
                    cell_id=r.cell_id,
                    metric=metric,
                    order=ranked,
                    head_to_head=f"{top[1]}_vs_{top[0]}",
                    verdict=c.verdict,
                    winner=winner,
                    detail=_bake_off_detail(c, top, winner),
                )
            )
    return out


def _rank_candidates(
    r: CellResult, candidates: list[str], metric: str, gate: stats.GateResult
) -> list[str]:
    """Candidate ids ordered by their ratio against the reference, best first.

    Candidates whose reference contrast produced no usable ratio are dropped:
    an unmeasurable arm has no place in a ranking, and sorting NaN would put
    it wherever the sort happened to leave it.
    """
    ratios: dict[str, float] = {}
    for arm in candidates:
        c = gate.comparisons.get(contrast_key(r.cell_id, r.reference, arm, metric))
        if c is not None and math.isfinite(c.ratio):
            ratios[arm] = c.ratio
    return sorted(ratios, key=lambda a: ratios[a])


def _bake_off_detail(
    c: stats.PairedComparison, top: list[str], winner: str | None
) -> str:
    interval = (
        f"{c.ratio:.3f}x [{c.ci_low:.3f}, {c.ci_high:.3f}]"
        if math.isfinite(c.ci_low) and math.isfinite(c.ci_high)
        else "no usable interval"
    )
    pair = f"`{top[1]}` vs `{top[0]}` {interval}"
    if winner is not None:
        return f"`{winner}` wins: {pair}"
    if c.verdict is stats.Verdict.TIED:
        return f"no measurable difference between `{top[0]}` and `{top[1]}`: {pair}"
    return f"cannot separate `{top[0]}` and `{top[1]}`: {pair}"


def _bake_off_dict(b: BakeOff) -> dict[str, object]:
    return {
        "cell": b.cell_id,
        "metric": b.metric,
        "order": b.order,
        "head_to_head": b.head_to_head,
        "verdict": str(b.verdict),
        "winner": b.winner,
        "detail": b.detail,
    }


def to_dict(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> dict[str, object]:
    """Serialize a whole run, raw samples included."""
    return {
        # 2: cells hold K arms. `samples` is keyed by arm id rather than by
        # `"baseline"`/`"candidate"`, and per-metric statistics moved under
        # `contrasts["<b>_vs_<a>"]`. The `baseline`/`candidate` labels stay for
        # a two-arm run so existing readers keep working.
        "schema": 2,
        "metadata": recorder.metadata,
        "config": {
            "min_rounds": config.min_rounds,
            "max_rounds": config.max_rounds,
            "warmup": config.warmup,
            "budget_seconds": config.budget_seconds,
            "seed": config.seed,
            "threshold": config.threshold,
            "confidence": config.confidence,
            "n_resamples": config.n_resamples,
            "gated_metrics": list(config.gated_metrics),
        },
        "noise_floor": _noise_dict(gate.noise),
        # Per-control floors as well as the run-level worst case: with several
        # SDKs in one run, "which one was noisy" is the first question a
        # surprising verdict raises.
        "noise_floor_by_control": {
            k: _noise_dict(n) for k, n in gate.noise_by_control.items()
        },
        "trustworthy": gate.trustworthy,
        "regressions": gate.regressions,
        "improvements": gate.improvements,
        "ranked": gate.ranked,
        "bake_off": [_bake_off_dict(b) for b in bake_offs(recorder, config, gate)],
        "summary": gate.summary,
        "skipped": recorder.skipped,
        "cells": [
            {
                "id": r.cell_id,
                "arms": list(r.arm_ids),
                "arm_labels": r.arm_labels,
                "reference": r.reference,
                # Kept for two-arm readers that predate the K-arm schema; at
                # K > 2 `arms`/`arm_labels` are the complete picture and these
                # name only the first candidate.
                "baseline": r.baseline_label,
                "candidate": r.candidate_label,
                "control": r.control,
                "n_rounds": r.n_rounds,
                "n_warmup": r.n_warmup,
                "elapsed_s": round(r.elapsed_s, 3),
                "stopped_because": r.stopped_because,
                "rss_floor_bytes": r.rss_floor_bytes,
                "samples": r.samples,
                "contrasts": {
                    f"{b}_vs_{a}": {
                        m: _comparison_dict(gate.comparisons[key])
                        for m in METRICS
                        if (key := contrast_key(r.cell_id, a, b, m)) in gate.comparisons
                    }
                    for a, b in r.contrast_pairs()
                },
            }
            for r in recorder.results
        ],
    }


def _noise_dict(noise: stats.NoiseFloor | None) -> dict[str, object]:
    if noise is None:
        return {"assessed": False}
    return {
        "assessed": True,
        "tripped": noise.tripped,
        "underpowered": noise.underpowered,
        "width_ratio": _jsonable(noise.width_ratio),
        "detail": noise.detail,
    }


def _comparison_dict(c: stats.PairedComparison) -> dict[str, object]:
    return {
        "n_rounds": c.n_rounds,
        "baseline_median": _jsonable(c.baseline_median),
        "candidate_median": _jsonable(c.candidate_median),
        "ratio": _jsonable(c.ratio),
        "ci_low": _jsonable(c.ci_low),
        "ci_high": _jsonable(c.ci_high),
        "p_value": _jsonable(c.p_value),
        "p_adjusted": _jsonable(c.p_adjusted),
        "verdict": str(c.verdict),
        "note": c.note,
    }


def _jsonable(v: float | None) -> float | None:
    """JSON has no NaN or infinity; emit null rather than invalid JSON."""
    if v is None or not math.isfinite(v):
        return None
    return v


def write_json(
    path: Path,
    recorder: BenchmarkRecorder,
    config: BenchConfig,
    gate: stats.GateResult,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(recorder, config, gate), indent=2))
    return path


def underpowered_warning(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> str | None:
    """Say so when the run did not buy the precision it was asked for.

    A K-arm round costs K invocations, so at a fixed time budget the round
    count falls as arms are added and every interval widens by roughly
    ``sqrt(K/2)``. Asking for three arms on a two-arm budget therefore comes
    back as a wall of INCONCLUSIVE after burning the whole runner, with
    nothing in the output saying that more time was the missing ingredient.
    This says it, and says how much more.

    Returns None when every contrast reached the precision target.
    """
    widest = 0.0
    rounds = 0
    for r in recorder.results:
        if r.control:
            continue
        for a, b in r.contrast_pairs():
            for metric in config.gated_metrics:
                c = gate.comparisons.get(contrast_key(r.cell_id, a, b, metric))
                if c is None or not math.isfinite(c.ci_half_width_log):
                    continue
                if c.ci_half_width_log > widest:
                    widest, rounds = c.ci_half_width_log, c.n_rounds

    target = config.target_half_width_log
    if widest <= target or target <= 0:
        return None

    n_arms = max((len(r.arm_ids) for r in recorder.results), default=2)
    # Interval width falls as 1/sqrt(n), so closing a factor-f gap costs f^2
    # times the rounds -- and, at a fixed per-round cost, f^2 times the budget.
    shortfall = (widest / target) ** 2
    return (
        f"Underpowered: the widest contrast reached "
        f"+/-{(math.exp(widest) - 1) * 100:.1f}% after {rounds} rounds, against "
        f"a +/-{(math.exp(target) - 1) * 100:.1f}% target. A {n_arms}-arm round "
        f"costs {n_arms} invocations; holding precision needs about "
        f"{shortfall:.1f}x the rounds, so roughly "
        f"{config.budget_seconds * shortfall:.0f}s of budget (currently "
        f"{config.budget_seconds:.0f}s) and a max-rounds ceiling above "
        f"{math.ceil(rounds * shortfall)}. Contrasts the interval could not "
        f"separate are reported INCONCLUSIVE rather than as no difference."
    )


def markdown(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> str:
    """Render the run as a GitHub step summary."""
    threshold_pct = (config.threshold - 1) * 100
    n_arms = max((len(r.arm_ids) for r in recorder.results), default=2)
    lines = [
        "## SDK performance regression benchmark",
        "",
        f"Paired {n_arms}-arm comparison, all arms in the same rounds on one "
        f"runner. A contrast against the reference fails only if the 95% CI "
        f"lower bound exceeds **{config.threshold:.2f}x** (+{threshold_pct:.0f}%) "
        f"*and* the BH-adjusted p < {stats.DEFAULT_ALPHA}.",
        "",
        f"**{gate.summary}**",
        "",
    ]

    warning = underpowered_warning(recorder, config, gate)
    if warning:
        lines += ["> [!WARNING]", f"> {warning}", ""]

    noise = gate.noise
    if noise is not None and noise.detail:
        lines += [f"> {noise.detail}", ""]
    elif noise is not None and math.isfinite(noise.width_ratio):
        lines += [
            f"A/A noise floor: +/-{(noise.width_ratio - 1) * 100:.1f}% "
            f"(the smallest effect this run could resolve).",
            "",
        ]

    lines += [
        "| cell | contrast | metric | a | b | ratio (95% CI) | p (BH) | n | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in recorder.results:
        for a, b in result.contrast_pairs():
            head_to_head = result.reference not in (a, b)
            for metric in METRICS:
                c = gate.comparisons.get(contrast_key(result.cell_id, a, b, metric))
                if c is None:
                    continue
                gated = (
                    metric in config.gated_metrics
                    and not result.control
                    and not head_to_head
                )
                label = METRIC_LABELS[metric][0] + ("" if gated else " (ungated)")
                lines.append(
                    f"| {result.cell_id} | `{b}` vs `{a}` | {label} "
                    f"| {format_metric(metric, c.baseline_median)} "
                    f"| {format_metric(metric, c.candidate_median)} "
                    f"| {_ratio_cell(c)} | {_p_cell(c)} | {c.n_rounds} "
                    f"| {_verdict_cell(c)} |"
                )

    rankings = bake_offs(recorder, config, gate)
    if rankings:
        lines += [
            "",
            "### Bake-off",
            "",
            "Head-to-head between candidates, measured in the same rounds as "
            "everything else. Ranking only -- these contrasts never fail the "
            "build.",
            "",
        ]
        for bo in rankings:
            order = " < ".join(f"`{a}`" for a in bo.order)
            lines.append(
                f"- **{bo.cell_id}** ({METRIC_LABELS[bo.metric][0]}): "
                f"{order} -- {bo.detail}"
            )

    if recorder.skipped:
        lines += ["", "### Not measured", ""]
        lines += [f"- `{cid}`: {why}" for cid, why in sorted(recorder.skipped.items())]

    lines += [
        "",
        f"<sub>seed {config.seed}; warm-up {config.warmup} rounds; "
        f"{config.min_rounds}-{config.max_rounds} measured rounds per cell; "
        "stopping on attained CI width, never on significance.</sub>",
    ]
    return "\n".join(lines) + "\n"


def _ratio_cell(c: stats.PairedComparison) -> str:
    if not math.isfinite(c.ratio):
        return "-"
    if not (math.isfinite(c.ci_low) and math.isfinite(c.ci_high)):
        return f"{c.ratio:.3f}x"
    return f"{c.ratio:.3f}x [{c.ci_low:.3f}, {c.ci_high:.3f}]"


def _p_cell(c: stats.PairedComparison) -> str:
    p = c.p_adjusted if c.p_adjusted is not None else c.p_value
    if p is None or not math.isfinite(p):
        return "-"
    return f"{p:.3f}" if p >= 0.001 else "<0.001"


_VERDICT_ICONS = {
    stats.Verdict.PASS: "PASS",
    stats.Verdict.REGRESSION: "**REGRESSION**",
    stats.Verdict.IMPROVED: "IMPROVED",
    stats.Verdict.INCONCLUSIVE: "inconclusive",
    # Head-to-head vocabulary. Not bolded: none of these can fail the build,
    # and a SLOWER that looked like a REGRESSION would invite someone to treat
    # it as one.
    stats.Verdict.FASTER: "faster",
    stats.Verdict.SLOWER: "slower",
    stats.Verdict.TIED: "tied",
}


def _verdict_cell(c: stats.PairedComparison) -> str:
    text = _VERDICT_ICONS[c.verdict]
    return f"{text} ({c.note})" if c.note else text


def append_step_summary(text: str) -> None:
    """Append to ``$GITHUB_STEP_SUMMARY`` when running in Actions."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as f:
        f.write(text)
