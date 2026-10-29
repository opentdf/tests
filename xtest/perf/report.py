"""Collecting benchmark results and turning them into artifacts.

Cells do not assert. Each one records its raw samples here and moves on,
because the decision rule needs every cell before it can decide anything:
the multiplicity correction is computed across the run, and the A/A control
can invalidate the whole thing. The gate therefore runs once, at session
finish, from :meth:`BenchmarkRecorder.gate`.

Two artifacts come out:

- A JSON file per run, holding **every raw per-round sample** alongside the
  derived statistics, under an explicit ``schema`` version (see
  :data:`SCHEMA_VERSION`). Re-analysing a surprising result offline is the
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
from perf.conclusions import Conclusion, conclude
from perf.measure import METRIC_LABELS, METRICS, format_metric
from perf.runner import BenchConfig, CellResult, analyze, contrast_key

#: Version of the JSON artifact's shape; consumers of version 1 must check it.
#: Version 2 added multi-arm cells. Each cell names its ``arms`` (id, label)
#: and ``reference`` arm id, and keys ``samples`` by arm id. Statistics live
#: under ``contrasts`` -- one per pair of arms, with ``a``, ``b`` and
#: ``metrics`` -- not one ``metrics`` block, and medians are
#: ``a_median``/``b_median``, not ``baseline_median``/``candidate_median``.
#: Candidate comparisons are summarized under the top-level ``conclusions``.
#: Only two-arm cells keep the ``baseline``/``candidate`` labels.
#: ``regressions``, ``improvements`` and ``noise_floor_by_control`` are keyed
#: ``<cell>/<b>_vs_<a>/<metric>``, not ``<cell>/<metric>``. The top level adds
#: ``nothing_measured``.
SCHEMA_VERSION = 2

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

    def conclusions(
        self, config: BenchConfig, gate: stats.GateResult
    ) -> list[Conclusion]:
        return conclude(self.results, config, gate)


def to_dict(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> dict[str, object]:
    """Serialize a whole run, raw samples included."""
    return {
        "schema": SCHEMA_VERSION,
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
        "nothing_measured": gate.nothing_measured,
        "regressions": gate.regressions,
        "improvements": gate.improvements,
        "summary": gate.summary,
        "conclusions": [c.to_dict() for c in recorder.conclusions(config, gate)],
        "skipped": recorder.skipped,
        "cells": [_cell_dict(r, gate) for r in recorder.results],
    }


def _cell_dict(r: CellResult, gate: stats.GateResult) -> dict[str, object]:
    cell: dict[str, object] = {
        "id": r.cell_id,
        "sdk": r.sdk,
        "control": r.control,
        "reference": r.reference,
        "arms": [{"id": a, "label": r.arm_labels[a]} for a in r.arm_ids],
    }
    if len(r.candidates) == 1:
        # The two-arm convenience labels. Omitted above two arms, where "the
        # candidate" would silently mean only the first of several.
        cell["baseline"] = r.arm_labels[r.reference]
        cell["candidate"] = r.arm_labels[r.candidates[0]]
    cell |= {
        "n_rounds": r.n_rounds,
        "n_warmup": r.n_warmup,
        "elapsed_s": round(r.elapsed_s, 3),
        "stopped_because": r.stopped_because,
        "rss_floor_bytes": r.rss_floor_bytes,
        "samples": r.samples,
        # `analyze` stores every contrast_pairs() x METRICS key, so a missing
        # one is a wrongly built key: raise rather than drop it from the JSON.
        "contrasts": [
            {
                "a": a,
                "b": b,
                "metrics": {
                    m: _comparison_dict(
                        gate.comparisons[contrast_key(r.cell_id, a, b, m)]
                    )
                    for m in METRICS
                },
            }
            for a, b in r.contrast_pairs()
        ],
    }
    return cell


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
        "a_median": _jsonable(c.a_median),
        "b_median": _jsonable(c.b_median),
        "ratio": _jsonable(c.ratio),
        "ci_low": _jsonable(c.ci_low),
        "ci_high": _jsonable(c.ci_high),
        "p_value": _jsonable(c.p_value),
        "p_adjusted": _jsonable(c.p_adjusted),
        # Both directions are carried explicitly: the faster tail is its own
        # test, not the slower one read backwards.
        "p_value_faster": _jsonable(c.p_value_faster),
        "p_adjusted_faster": _jsonable(c.p_adjusted_faster),
        "verdict": str(c.verdict),
        "note": c.note,
    }


def _jsonable(v: float | None) -> float | None:
    """JSON has no NaN or infinity; emit null rather than invalid JSON."""
    if v is None or not math.isfinite(v):
        return None
    return v


def neutral(recorder: BenchmarkRecorder) -> bool:
    """True if preparation found every requested build at one commit."""
    return recorder.metadata.get("preparation") == "neutral"


def headline(recorder: BenchmarkRecorder, gate: stats.GateResult) -> str:
    """The run's one-line answer, shared by the terminal and the summary.

    A neutral preparation measured nothing on purpose, so it gets its own
    answer instead of the gate's NOTHING MEASURED, which is a failure.
    """
    if not neutral(recorder):
        return gate.summary
    installed = recorder.metadata.get("installation")
    message = installed.get("status_message", "") if isinstance(installed, dict) else ""
    return (
        "NEUTRAL: the requested builds are the same commit, so there was "
        f"nothing to compare. {message}"
    ).rstrip()


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
    """Render the run as a GitHub step summary.

    One row per candidate, cell and metric, each against that cell's
    reference. Deliberately plain: it is a view of the JSON, not a separate
    source, and every value in it can be found there.
    """
    threshold_pct = (config.threshold - 1) * 100
    lines = [
        "## SDK performance regression benchmark",
        "",
        f"Paired comparison on one runner: every build runs once per round, "
        f"and each candidate is compared with the reference. A cell fails only "
        f"if the 95% CI lower bound exceeds **{config.threshold:.2f}x** "
        f"(+{threshold_pct:.0f}%) *and* the BH-adjusted p < {stats.DEFAULT_ALPHA}.",
        "",
    ]
    lines += [f"**{headline(recorder, gate)}**", ""]

    noise = gate.noise
    if neutral(recorder):
        # No control ran because nothing was going to be compared; saying so
        # would read as a second problem.
        pass
    elif noise is not None and noise.detail:
        lines += [f"> {noise.detail}", ""]
    elif noise is not None and math.isfinite(noise.width_ratio):
        lines += [
            f"A/A noise floor: +/-{(noise.width_ratio - 1) * 100:.1f}% "
            f"(the smallest effect this run could resolve).",
            "",
        ]

    lines += [
        "| cell | candidate | metric | reference median | candidate median "
        "| ratio (95% CI) | p (BH) | n | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in recorder.results:
        for a, b in result.contrast_pairs():
            if not result.is_reference_pair(a, b):
                continue
            candidate = f"A/A {b}" if result.control else f"`{result.arm_labels[b]}`"
            for metric in METRICS:
                c = gate.comparisons[contrast_key(result.cell_id, a, b, metric)]
                gated = metric in config.gated_metrics and not result.control
                label = METRIC_LABELS[metric][0] + ("" if gated else " (ungated)")
                lines.append(
                    f"| {result.cell_id} | {candidate} | {label} "
                    f"| {format_metric(metric, c.a_median)} "
                    f"| {format_metric(metric, c.b_median)} "
                    f"| {_ratio_cell(c)} | {_p_cell(c)} | {c.n_rounds} "
                    f"| {_verdict_cell(c)} |"
                )

    lines += _candidate_comparisons(recorder.conclusions(config, gate))

    references = sorted(
        {r.arm_labels[r.reference] for r in recorder.results if not r.control}
    )
    if references:
        lines += ["", f"Reference: {', '.join(f'`{ref}`' for ref in references)}."]

    if recorder.skipped:
        lines += ["", "### Not measured", ""]
        lines += [f"- `{cid}`: {why}" for cid, why in sorted(recorder.skipped.items())]

    lines += [
        "",
        f"<sub>seed {config.seed}; warm-up {config.warmup} rounds; "
        f"{config.min_rounds}-{config.max_rounds} measured rounds per cell; "
        "stopping on attained CI width, never on significance; "
        "p is one-sided, in the direction of the observed ratio.</sub>",
    ]
    return "\n".join(lines) + "\n"


def _candidate_comparisons(conclusions: list[Conclusion]) -> list[str]:
    """The candidate-to-candidate section: pairwise verdicts, then any winner."""
    if not conclusions:
        return []
    lines = [
        "",
        "### Candidate comparisons",
        "",
        "Each pair of candidates, compared directly. These never fail the build. "
        "A winner is named only when it is faster than every other candidate "
        "and the A/A control held.",
        "",
        "| cell | metric | comparison | ratio (95% CI) | verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in conclusions:
        for p in c.pairwise:
            interval = (
                f"{p.ratio:.3f}x [{p.ci_low:.3f}, {p.ci_high:.3f}]"
                if math.isfinite(p.ci_low) and math.isfinite(p.ci_high)
                else "-"
            )
            verdict = f"{p.verdict} ({p.note})" if p.note else str(p.verdict)
            lines.append(
                f"| {c.cell_id} | {METRIC_LABELS[c.metric][0]} "
                f"| `{c.labels[p.b]}` vs `{c.labels[p.a]}` | {interval} | {verdict} |"
            )
    lines.append("")
    lines += [conclusion_line(c) for c in conclusions]
    return lines


def conclusion_line(c: Conclusion) -> str:
    """One line per cell and metric: the winner, or why there is none."""
    head = f"- **{c.cell_id}** ({METRIC_LABELS[c.metric][0]}): "
    if c.winner is not None:
        return head + f"`{c.labels[c.winner]}` wins, {c.reason}."
    return head + f"{c.reason}."


def _ratio_cell(c: stats.PairedComparison) -> str:
    if not math.isfinite(c.ratio):
        return "-"
    if not (math.isfinite(c.ci_low) and math.isfinite(c.ci_high)):
        return f"{c.ratio:.3f}x"
    return f"{c.ratio:.3f}x [{c.ci_low:.3f}, {c.ci_high:.3f}]"


def _p_cell(c: stats.PairedComparison) -> str:
    # Show the one-sided tail matching the observed effect. Below one that is
    # the explicit faster-tail test: a BH-adjusted slower-tail p-value cannot
    # be read backwards as evidence of improvement, and printing it beside an
    # IMPROVED verdict shows ~1.000 next to a significant result.
    if c.ratio < 1:
        p = c.p_adjusted_faster if c.p_adjusted_faster is not None else c.p_value_faster
    else:
        p = c.p_adjusted if c.p_adjusted is not None else c.p_value
    if p is None or not math.isfinite(p):
        return "-"
    return f"{p:.3f}" if p >= 0.001 else "<0.001"


_VERDICT_ICONS = {
    stats.Verdict.PASS: "PASS",
    stats.Verdict.REGRESSION: "**REGRESSION**",
    stats.Verdict.IMPROVED: "IMPROVED",
    stats.Verdict.INCONCLUSIVE: "inconclusive",
    stats.Verdict.FASTER: "FASTER",
    stats.Verdict.SLOWER: "SLOWER",
    stats.Verdict.TIED: "TIED",
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
