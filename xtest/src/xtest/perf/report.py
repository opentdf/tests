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
from perf.runner import BenchConfig, CellResult, analyze

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


def to_dict(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> dict[str, object]:
    """Serialize a whole run, raw samples included."""
    return {
        "schema": 1,
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
        "summary": gate.summary,
        "skipped": recorder.skipped,
        "cells": [
            {
                "id": r.cell_id,
                "baseline": r.baseline_label,
                "candidate": r.candidate_label,
                "control": r.control,
                "n_rounds": r.n_rounds,
                "n_warmup": r.n_warmup,
                "elapsed_s": round(r.elapsed_s, 3),
                "stopped_because": r.stopped_because,
                "rss_floor_bytes": r.rss_floor_bytes,
                "samples": r.samples,
                "metrics": {
                    m: _comparison_dict(gate.comparisons[f"{r.cell_id}/{m}"])
                    for m in METRICS
                    if f"{r.cell_id}/{m}" in gate.comparisons
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


def markdown(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> str:
    """Render the run as a GitHub step summary."""
    threshold_pct = (config.threshold - 1) * 100
    lines = [
        "## SDK performance regression benchmark",
        "",
        f"Paired A/B on one runner. A cell fails only if the 95% CI lower "
        f"bound exceeds **{config.threshold:.2f}x** (+{threshold_pct:.0f}%) "
        f"*and* the BH-adjusted p < {stats.DEFAULT_ALPHA}.",
        "",
        f"**{gate.summary}**",
        "",
    ]

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
        "| cell | metric | baseline | candidate | ratio (95% CI) | p (BH) | n | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in recorder.results:
        for metric in METRICS:
            key = f"{result.cell_id}/{metric}"
            c = gate.comparisons.get(key)
            if c is None:
                continue
            gated = metric in config.gated_metrics and not result.control
            label = METRIC_LABELS[metric][0] + ("" if gated else " (ungated)")
            lines.append(
                f"| {result.cell_id} | {label} "
                f"| {format_metric(metric, c.baseline_median)} "
                f"| {format_metric(metric, c.candidate_median)} "
                f"| {_ratio_cell(c)} | {_p_cell(c)} | {c.n_rounds} "
                f"| {_verdict_cell(c)} |"
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
