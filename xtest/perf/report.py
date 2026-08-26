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
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

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

# Replaced by the workflow after upload-artifact returns its authenticated URL.
# Kept conspicuous so a failed substitution cannot look like a real link.
ARTIFACT_URL_PLACEHOLDER = "@@BENCH_ARTIFACT_URL@@"


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


@dataclass(frozen=True, slots=True)
class ReportRow:
    """One reportable contrast/metric with enough context to render it."""

    result: CellResult
    a: str
    b: str
    metric: str
    comparison: stats.PairedComparison
    gated: bool
    head_to_head: bool


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
        "nothing_measured": gate.nothing_measured,
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
        # `p_value`/`p_adjusted` retain their historical meaning: the
        # one-sided "b is slower than a" tail. The faster tail is separate so
        # consumers never have to reverse an adjusted upper-tail probability.
        "p_value": _jsonable(c.p_value),
        "p_adjusted": _jsonable(c.p_adjusted),
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


def write_json(
    path: Path,
    recorder: BenchmarkRecorder,
    config: BenchConfig,
    gate: stats.GateResult,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_dict(recorder, config, gate), indent=2))
    return path


def write_markdown(path: Path, text: str) -> Path:
    """Write a summary template for CI to publish after artifact upload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
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
    recorder: BenchmarkRecorder,
    config: BenchConfig,
    gate: stats.GateResult,
    *,
    artifact_url: str = "",
) -> str:
    """Render a decision-first GitHub job summary with progressive disclosure."""
    rows = _report_rows(recorder, config, gate)
    gated_rows = [r for r in rows if r.gated]
    attention = [
        r
        for r in gated_rows
        if r.comparison.verdict
        in (
            stats.Verdict.REGRESSION,
            stats.Verdict.INCONCLUSIVE,
            stats.Verdict.IMPROVED,
        )
    ]
    attention.sort(key=_attention_sort_key)
    sdk = next((r.sdk for r in recorder.results if r.sdk), "SDK")
    status, headline = _headline(gate, gated_rows)
    n_arms = max((len(r.arm_ids) for r in recorder.results), default=2)

    lines = [
        f"## {sdk.upper()} SDK performance — {status}",
        "",
        "### TL;DR",
        "",
        f"> **{headline}**",
        ">",
        f"> {gate.summary}",
        "",
    ]
    lines += _quick_links(recorder.metadata, artifact_url)
    lines += _provenance(recorder)

    warning = underpowered_warning(recorder, config, gate)
    if warning:
        lines += ["> [!WARNING]", f"> {warning}", ""]
    noise = gate.noise
    if noise is not None and noise.detail:
        lines += [f"> {noise.detail}", ""]

    lines += ["### What changed", ""]
    if attention:
        lines += [
            "Only gated regressions, unresolved measurements, and confirmed "
            "improvements are shown here. Clean rows and diagnostic metrics are below.",
            "",
            "| measurement | contrast | observed cost | change (95% CI) | gate margin | result |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
        for row in attention:
            c = row.comparison
            lines.append(
                f"| {_cell_label(row.result)} · {METRIC_LABELS[row.metric][0]} "
                f"| `{row.b}` vs `{row.a}` | {_cost_change(row.metric, c)} "
                f"| {_percent_change(c)} | {_gate_margin(c, config.threshold)} "
                f"| {_verdict_cell(c)} |"
            )
        lines += _effect_overview(attention, config.threshold)
    else:
        lines += [
            "No gated comparison requires attention: every measured wall-clock and "
            "RSS contrast passed with enough precision.",
            "",
        ]

    lines += _bake_off_section(recorder, config, gate)
    lines += _diagnostics(recorder, attention, config)
    lines += _full_measurements(rows)
    lines += _not_measured(recorder)
    lines += _method(config, n_arms)
    lines += _run_facts(recorder, config, gate, artifact_url)
    return "\n".join(lines) + "\n"


def _report_rows(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> list[ReportRow]:
    rows: list[ReportRow] = []
    for result in recorder.results:
        for a, b in result.contrast_pairs():
            head_to_head = result.reference not in (a, b)
            for metric in METRICS:
                c = gate.comparisons.get(contrast_key(result.cell_id, a, b, metric))
                if c is None:
                    continue
                rows.append(
                    ReportRow(
                        result=result,
                        a=a,
                        b=b,
                        metric=metric,
                        comparison=c,
                        gated=(
                            metric in config.gated_metrics
                            and not result.control
                            and not head_to_head
                        ),
                        head_to_head=head_to_head,
                    )
                )
    return rows


def _headline(gate: stats.GateResult, gated_rows: list[ReportRow]) -> tuple[str, str]:
    inconclusive = sum(
        r.comparison.verdict is stats.Verdict.INCONCLUSIVE for r in gated_rows
    )
    improvements = sum(
        r.comparison.verdict is stats.Verdict.IMPROVED for r in gated_rows
    )
    if gate.nothing_measured:
        return "NOTHING MEASURED", "The benchmark produced no comparisons."
    if not gate.trustworthy:
        return (
            "UNTRUSTWORTHY",
            "The A/A control detected bias; results are visible but cannot fail the build.",
        )
    if gate.regressions:
        return (
            "REGRESSION",
            f"{len(gate.regressions)} confirmed regression(s); "
            f"{inconclusive} unresolved and {improvements} improved gated comparison(s).",
        )
    if inconclusive:
        return (
            "INCONCLUSIVE",
            f"No confirmed regressions, but {inconclusive} gated comparison(s) "
            "could not be resolved.",
        )
    return (
        "PASS",
        f"No confirmed regressions; {improvements} gated comparison(s) improved.",
    )


def _quick_links(metadata: Mapping[str, object], artifact_url: str) -> list[str]:
    links: list[str] = []
    if artifact_url:
        links.append(f"[Download raw samples and HTML report]({artifact_url})")
    run_url = str(metadata.get("github_run_url", ""))
    if run_url:
        links.append(f"[Workflow run]({run_url})")
    return [" · ".join(links), ""] if links else []


def _provenance(recorder: BenchmarkRecorder) -> list[str]:
    result = next((r for r in recorder.results if not r.control), None)
    if result is None:
        result = next(iter(recorder.results), None)
    if result is None:
        return []

    raw_sources = recorder.metadata.get("arm_sources", [])
    sources = (
        {
            str(s.get("tag", "")): s
            for s in raw_sources
            if isinstance(s, dict) and s.get("tag")
        }
        if isinstance(raw_sources, list)
        else {}
    )
    lines = [
        "### Compared builds",
        "",
        "| arm | role | source | commit | compare to reference |",
        "| --- | --- | --- | --- | --- |",
    ]
    reference_source = sources.get(result.reference)
    for arm in result.arm_ids:
        source = sources.get(arm)
        role_name = _arm_role(result, arm)
        role = f"**{role_name}**" if arm == result.reference else role_name
        label = result.arm_labels.get(arm, arm)
        source_link = _source_link(source, label)
        commit_link = _commit_link(source)
        compare_link = (
            "—" if arm == result.reference else _compare_link(reference_source, source)
        )
        lines.append(
            f"| `{_md(arm)}` | {role} | {source_link} | {commit_link} | {compare_link} |"
        )
    lines.append("")
    warning = recorder.metadata.get("arm_sources_warning")
    if warning:
        lines += [f"> Provenance unavailable: {_md(str(warning))}", ""]
    return lines


def _source_link(source: object, fallback: str) -> str:
    if not isinstance(source, dict):
        return _md(fallback)
    repo = str(source.get("repo_url", ""))
    tag = str(source.get("tag", fallback))
    alias = str(source.get("alias", tag))
    pr = str(source.get("pr", ""))
    release = str(source.get("release", ""))
    sha = str(source.get("sha", ""))
    if repo and pr:
        return f"[PR #{_md(pr)}]({repo}/pull/{quote(pr, safe='')}) · `{_md(tag)}`"
    if repo and release:
        return f"[{_md(tag)}]({repo}/releases/tag/{quote(release, safe='')}) · release"
    if repo and sha:
        kind = "branch" if source.get("head") else "commit"
        return f"[{_md(alias)}]({repo}/tree/{quote(sha, safe='')}) · {kind}"
    return _md(fallback)


def _commit_link(source: object) -> str:
    if not isinstance(source, dict):
        return "—"
    repo = str(source.get("repo_url", ""))
    sha = str(source.get("sha", ""))
    if not (repo and sha):
        return "—"
    return f"[`{_md(sha[:7])}`]({repo}/commit/{quote(sha, safe='')})"


def _compare_link(reference: object, candidate: object) -> str:
    if not (isinstance(reference, dict) and isinstance(candidate, dict)):
        return "—"
    repo = str(reference.get("repo_url", ""))
    if not repo or repo != str(candidate.get("repo_url", "")):
        return "—"
    a, b = str(reference.get("sha", "")), str(candidate.get("sha", ""))
    if not (a and b):
        return "—"
    return f"[diff]({repo}/compare/{quote(a, safe='')}...{quote(b, safe='')})"


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _attention_sort_key(row: ReportRow) -> tuple[int, float, str, int]:
    order = {
        stats.Verdict.REGRESSION: 0,
        stats.Verdict.INCONCLUSIVE: 1,
        stats.Verdict.IMPROVED: 2,
    }
    ratio = row.comparison.ratio
    magnitude = abs(math.log(ratio)) if math.isfinite(ratio) and ratio > 0 else 0
    return (
        order.get(row.comparison.verdict, 3),
        -round(magnitude, 3),
        row.result.cell_id,
        METRICS.index(row.metric),
    )


def _cell_label(result: CellResult) -> str:
    return result.cell_id.removeprefix(f"{result.sdk}-").replace("-", " / ")


def _arm_role(result: CellResult, arm: str) -> str:
    """A short, stable role that maps plot rows back to the build table."""
    if arm == result.reference:
        return "reference"
    candidates = [
        candidate for candidate in result.arm_ids if candidate != result.reference
    ]
    try:
        return f"candidate {chr(ord('A') + candidates.index(arm))}"
    except ValueError:
        return arm


def _cost_change(metric: str, c: stats.PairedComparison) -> str:
    if not (math.isfinite(c.baseline_median) and math.isfinite(c.candidate_median)):
        return "—"
    delta = c.candidate_median - c.baseline_median
    sign = "+" if delta >= 0 else "−"
    return (
        f"{format_metric(metric, c.baseline_median)} → "
        f"{format_metric(metric, c.candidate_median)} "
        f"({sign}{format_metric(metric, abs(delta))})"
    )


def _pct(ratio: float) -> str:
    if not math.isfinite(ratio):
        return "—"
    return f"{(ratio - 1) * 100:+.1f}%"


def _percent_change(c: stats.PairedComparison) -> str:
    point = _pct(c.ratio)
    if not (math.isfinite(c.ci_low) and math.isfinite(c.ci_high)):
        return point
    return f"{point} [{_pct(c.ci_low)}, {_pct(c.ci_high)}]"


def _gate_margin(c: stats.PairedComparison, threshold: float) -> str:
    if c.verdict is stats.Verdict.REGRESSION and math.isfinite(c.ci_low):
        return f"+{(c.ci_low - threshold) * 100:.1f} pp"
    if c.verdict is stats.Verdict.IMPROVED and math.isfinite(c.ci_high):
        return f"+{(1 / threshold - c.ci_high) * 100:.1f} pp"
    return "—"


def _effect_overview(rows: list[ReportRow], threshold: float) -> list[str]:
    labels = [f"{_cell_label(r.result)} {METRIC_LABELS[r.metric][0]}" for r in rows]
    roles = [_arm_role(row.result, row.b) for row in rows]
    label_width = min(30, max(map(len, labels), default=0))
    role_width = max(map(len, roles), default=0)
    width = 57
    threshold_log = math.log(threshold)
    observed_logs = [
        abs(math.log(value))
        for row in rows
        for value in (
            row.comparison.ratio,
            row.comparison.ci_low,
            row.comparison.ci_high,
        )
        if math.isfinite(value) and value > 0
    ]
    # Preserve room around the practical band, but expand far enough that the
    # largest interval gets brackets rather than an off-scale arrow. The tail
    # transform in `_effect_strip` prevents an epic result from squeezing the
    # gate markers and every merely-large result into the center character.
    span = max(3 * threshold_log, max(observed_logs, default=0) * 1.05)
    axis = [" "] * width
    for text, start in (
        ("← faster", 0),
        ("no change", (width - len("no change")) // 2),
        ("slower →", width - len("slower →")),
    ):
        axis[start : start + len(text)] = text
    lines = [
        "",
        "#### Effect at a glance",
        "",
        "Shared tail-compressed log-ratio scale; `┆` marks ±the practical "
        "threshold and `│` no change. Candidate letters match the build table; "
        "exact changes are printed at right, and `◆` means the CI is narrower "
        "than one character.",
        "",
        "```text",
        f"{'arm':<{role_width}}  {'measurement':<{label_width}}  {''.join(axis)}",
    ]
    for role, label, row in zip(roles, labels, rows, strict=True):
        lines.append(
            f"{role:<{role_width}}  {label[:label_width]:<{label_width}}  "
            f"{_effect_strip(row.comparison, threshold, width=width, span=span)} "
            f"{_pct(row.comparison.ratio):>7} {row.comparison.verdict}"
        )
    lines += ["```", ""]
    return lines


def _effect_strip(
    c: stats.PairedComparison,
    threshold: float,
    *,
    width: int = 57,
    span: float | None = None,
) -> str:
    """A fixed-width CI forest strip on a symmetric compressed-log scale."""
    chars = [" "] * width
    threshold_log = math.log(threshold)
    span = span or 3 * threshold_log

    def unit(value: float) -> float:
        """Keep the gate at 1/3 width and compress the dynamic tails."""
        magnitude = abs(value)
        if magnitude <= threshold_log:
            scaled = magnitude / threshold_log / 3
        else:
            tail = max(span - threshold_log, 1e-12)
            # Keep ten percent of either edge as breathing room: the largest
            # observed effect should look extreme without masquerading as a
            # clipped value.
            scaled = 1 / 3 + (0.9 - 1 / 3) * (
                math.log1p((magnitude - threshold_log) / threshold_log)
                / math.log1p(tail / threshold_log)
            )
        return math.copysign(max(-1.0, min(1.0, scaled)), value)

    def pos(ratio: float) -> int:
        value = math.log(ratio) if math.isfinite(ratio) and ratio > 0 else 0.0
        return round((unit(value) + 1) * (width - 1) / 2)

    for ratio, marker in ((1 / threshold, "┆"), (1.0, "│"), (threshold, "┆")):
        chars[pos(ratio)] = marker
    collapsed_ci_at: int | None = None
    if math.isfinite(c.ci_low) and math.isfinite(c.ci_high):
        lo, hi = sorted((pos(c.ci_low), pos(c.ci_high)))
        if lo == hi:
            collapsed_ci_at = lo
            chars[lo] = "◆"
        else:
            for i in range(lo, hi + 1):
                if chars[i] == " ":
                    chars[i] = "━"
            chars[lo], chars[hi] = "[", "]"
    if math.isfinite(c.ratio) and c.ratio > 0:
        point = pos(c.ratio)
        chars[point] = "◆" if point == collapsed_ci_at else "●"
        if math.log(c.ratio) < -span:
            chars[0] = "◀"
        elif math.log(c.ratio) > span:
            chars[-1] = "▶"
    return "".join(chars)


def _bake_off_section(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> list[str]:
    rankings = bake_offs(recorder, config, gate)
    if not rankings:
        return []
    lines = [
        "### Bake-off",
        "",
        "Candidate-to-candidate ranking only; these contrasts never fail the build.",
        "",
    ]
    for bo in rankings:
        order = " < ".join(f"`{a}`" for a in bo.order)
        lines.append(
            f"- **{_cell_label(next(r for r in recorder.results if r.cell_id == bo.cell_id))}** "
            f"({METRIC_LABELS[bo.metric][0]}): {order} — {bo.detail}"
        )
    return lines + [""]


def _diagnostics(
    recorder: BenchmarkRecorder,
    attention: list[ReportRow],
    config: BenchConfig,
) -> list[str]:
    if not attention:
        return []
    lines = [
        "<details>",
        "<summary><strong>Round stability for attention rows</strong></summary>",
        "",
        "Each Braille glyph carries two rounds at four vertical levels. The scale "
        "is centered on 1.0 and is never tighter than the practical threshold.",
        "",
        "```text",
    ]
    for row in attention:
        values = _paired_ratios(row)
        if not values:
            continue
        slower = sum(v > 1 for v in values)
        label = f"{_cell_label(row.result)} {METRIC_LABELS[row.metric][0]}"
        lines.append(
            f"{label[:28]:<28} {_braille_sparkline(values, config.threshold):<24} "
            f"{slower}/{len(values)} rounds slower; median {_pct(statistics.median(values))}"
        )
    lines += ["```", "", "</details>", ""]
    return lines


def _paired_ratios(row: ReportRow) -> list[float]:
    baseline = row.result.samples.get(row.a, {}).get(row.metric, [])
    candidate = row.result.samples.get(row.b, {}).get(row.metric, [])
    return [c / b for b, c in zip(baseline, candidate, strict=True) if b > 0 and c > 0]


def _braille_sparkline(
    values: Iterable[float], threshold: float, *, max_chars: int = 24
) -> str:
    """Render positive ratios as a compact two-samples-per-glyph trace."""
    logs = [math.log(v) for v in values if math.isfinite(v) and v > 0]
    if not logs:
        return "—"
    limit = max_chars * 2
    if len(logs) > limit:
        # Median bins retain the robust character of the reported estimator.
        logs = [
            statistics.median(
                logs[round(i * len(logs) / limit) : round((i + 1) * len(logs) / limit)]
            )
            for i in range(limit)
        ]
    span = max(math.log(threshold), max(abs(v) for v in logs), 1e-12)
    dot_bits = ((0, 1, 2, 6), (3, 4, 5, 7))
    glyphs: list[str] = []
    for i in range(0, len(logs), 2):
        bits = 0
        for column, value in enumerate(logs[i : i + 2]):
            # Braille rows run top to bottom; positive/slower belongs at top.
            row = round((span - value) / (2 * span) * 3)
            row = max(0, min(3, row))
            bits |= 1 << dot_bits[column][row]
        glyphs.append(chr(0x2800 + bits))
    return "".join(glyphs)


def _full_measurements(rows: list[ReportRow]) -> list[str]:
    lines = [
        "<details>",
        "<summary><strong>All measurements, controls, and statistical details</strong></summary>",
        "",
        "| cell | contrast | metric | a | b | ratio (95% CI) | p (BH) | n | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        c = row.comparison
        label = METRIC_LABELS[row.metric][0] + ("" if row.gated else " (ungated)")
        lines.append(
            f"| {row.result.cell_id} | `{row.b}` vs `{row.a}` | {label} "
            f"| {format_metric(row.metric, c.baseline_median)} "
            f"| {format_metric(row.metric, c.candidate_median)} "
            f"| {_ratio_cell(c)} | {_p_cell(c)} | {c.n_rounds} "
            f"| {_verdict_cell(c)} |"
        )
    return lines + ["", "</details>", ""]


def _not_measured(recorder: BenchmarkRecorder) -> list[str]:
    if not recorder.skipped:
        return []
    lines = [
        "<details open>",
        "<summary><strong>Not measured</strong></summary>",
        "",
    ]
    lines += [f"- `{cid}`: {why}" for cid, why in sorted(recorder.skipped.items())]
    return lines + ["", "</details>", ""]


def _method(config: BenchConfig, n_arms: int) -> list[str]:
    threshold_pct = (config.threshold - 1) * 100
    return [
        "<details>",
        "<summary><strong>How to read this gate</strong></summary>",
        "",
        f"This is a paired {n_arms}-arm comparison: every arm ran in the same "
        "randomized rounds on one runner. A reference contrast regresses only "
        f"when its 95% CI is wholly beyond +{threshold_pct:.0f}% "
        f"and its directional BH-adjusted p-value is below {stats.DEFAULT_ALPHA}. "
        "The loop stops on attained interval width, never significance.",
        "",
        "PASS means the run was precise enough to have found an effect at the "
        "threshold; INCONCLUSIVE does not mean no change.",
        "",
        "</details>",
        "",
    ]


def _run_facts(
    recorder: BenchmarkRecorder,
    config: BenchConfig,
    gate: stats.GateResult,
    artifact_url: str,
) -> list[str]:
    rounds = [r.n_rounds for r in recorder.results if not r.control]
    elapsed = sum(r.elapsed_s for r in recorder.results)
    noise = gate.noise
    noise_text = (
        f"±{(noise.width_ratio - 1) * 100:.1f}%"
        if noise is not None and math.isfinite(noise.width_ratio)
        else "unavailable"
    )
    metadata = recorder.metadata
    artifact = f"[JSON + HTML]({artifact_url})" if artifact_url else "local output"
    round_text = f"{min(rounds)}–{max(rounds)}" if rounds else "0"
    return [
        "### Run facts",
        "",
        "| result cells | rounds/cell | elapsed | A/A noise | platform | runner | evidence |",
        "| ---: | ---: | ---: | ---: | --- | --- | --- |",
        f"| {sum(not r.control for r in recorder.results)} "
        f"| {round_text} | {elapsed:.0f}s | {noise_text} "
        f"| {_md(str(metadata.get('platform_version', 'unknown')))} "
        f"| {_md(str(metadata.get('runner_os') or metadata.get('platform', 'unknown')))} "
        f"| {artifact} |",
        "",
        f"<sub>seed {config.seed}; {config.warmup} warm-up rounds; "
        f"{config.min_rounds}–{config.max_rounds} measured rounds allowed; "
        f"{len(recorder.skipped)} cells skipped.</sub>",
    ]


def _ratio_cell(c: stats.PairedComparison) -> str:
    if not math.isfinite(c.ratio):
        return "-"
    if not (math.isfinite(c.ci_low) and math.isfinite(c.ci_high)):
        return f"{c.ratio:.3f}x"
    return f"{c.ratio:.3f}x [{c.ci_low:.3f}, {c.ci_high:.3f}]"


def _p_cell(c: stats.PairedComparison) -> str:
    # Show the one-sided tail matching the observed effect. For a ratio below
    # one that is the explicit faster-tail test; adjusted upper-tail p-values
    # cannot be interpreted backwards after BH correction.
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
