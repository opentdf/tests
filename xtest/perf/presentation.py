"""The decision-first benchmark summary: what changed, how sure, and from what.

This is presentation only. It reads the recorder, the analysed gate and the
candidate conclusions and lays them out for a reader; it never decides a
verdict, a gate status, a correction family or a winner. Those are settled in
:mod:`perf.stats`, :mod:`perf.runner` and :mod:`perf.conclusions`, so this
module can be rewritten freely without moving any result. The plain table in
:func:`perf.report.markdown` and the JSON artifact stay usable without it.

The summary is rendered as a *template*: any link to the uploaded artifact is
written as :data:`ARTIFACT_URL` and filled in by :func:`publish`, once the
upload has produced a URL. Locally there is no URL, and :func:`publish` drops
those links rather than leaving a placeholder behind. Provenance -- which
commit each arm is -- comes from the installation manifest, the same record
in both environments.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from perf import stats
from perf.conclusions import Conclusion
from perf.measure import METRIC_LABELS, METRICS, format_metric
from perf.report import (
    BenchmarkRecorder,
    headline,
    neutral,
    p_cell,
    ratio_cell,
    verdict_cell,
)
from perf.runner import BenchConfig, CellResult, contrast_key

#: Stands in for the uploaded artifact's URL until :func:`publish` knows it.
ARTIFACT_URL = "{{BENCH_ARTIFACT_URL}}"


@dataclass(frozen=True, slots=True)
class Row:
    """One contrast and metric, with what is needed to render it."""

    result: CellResult
    a: str
    b: str
    metric: str
    comparison: stats.PairedComparison
    gated: bool

    @property
    def candidate_pair(self) -> bool:
        return not self.result.is_reference_pair(self.a, self.b)


def render(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> str:
    """The step-summary template for one run; pass it through :func:`publish`."""
    rows = _rows(recorder, config, gate)
    gated = [r for r in rows if r.gated]
    attention = sorted(
        (
            r
            for r in gated
            if r.comparison.verdict
            in (
                stats.Verdict.REGRESSION,
                stats.Verdict.INCONCLUSIVE,
                stats.Verdict.IMPROVED,
            )
        ),
        key=_attention_order,
    )
    conclusions = recorder.conclusions(config, gate)
    sdk = next((r.sdk for r in recorder.results if r.sdk), "") or _installed_sdk(
        recorder.metadata
    )
    status, detail = status_line(recorder, gate, gated)

    lines = [
        f"## {(sdk or 'SDK').upper()} SDK performance — {status}",
        "",
        f"> **{_md(detail)}**",
        ">",
        f"> {_md(headline(recorder, gate))}",
        "",
    ]
    lines += _links(recorder.metadata)
    lines += _provenance(recorder)
    warning = underpowered_warning(recorder, config, gate)
    if warning:
        lines += ["> [!WARNING]", f"> {warning}", ""]
    if gate.noise is not None and gate.noise.detail and not neutral(recorder):
        lines += [f"> {_md(gate.noise.detail)}", ""]

    lines += ["### What changed", ""]
    if neutral(recorder):
        lines += [
            "Nothing was compared: the requested refs are the same source commit.",
            "",
        ]
    elif gate.nothing_measured:
        lines += [
            "No comparison ran. **Not measured** below gives each cell's reason; "
            "this is not a passing result.",
            "",
        ]
    elif attention:
        lines += [
            "Gated regressions, unresolved measurements and confirmed improvements. "
            "Clean rows and ungated metrics are under **All measurements**.",
            "",
            "| measurement | build | observed cost | change (95% CI) | gate margin | result |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
        for row in attention:
            c = row.comparison
            lines.append(
                f"| {_md(_cell_label(row.result))} · {METRIC_LABELS[row.metric][0]} "
                f"| {_arm(row.result, row.b)} | {_cost_change(row.metric, c)} "
                f"| {_percent_change(c)} | {_gate_margin(c, config.threshold)} "
                f"| {verdict_cell(c)} |"
            )
        lines += effect_overview(attention, config.threshold)
    else:
        lines += [
            "No gated comparison needs attention: every measured gated contrast "
            "passed with enough precision.",
            "",
        ]

    lines += _candidates(conclusions, recorder)
    lines += _stability(attention, config)
    lines += _all_measurements(rows)
    lines += _not_measured(recorder)
    lines += _method(config, max((len(r.arm_ids) for r in recorder.results), default=2))
    lines += _run_facts(recorder, config, gate)
    return "\n".join(lines) + "\n"


def publish(template: str, artifact_url: str = "") -> str:
    """Fill in the artifact URL, or drop the links that needed one.

    Never returns a placeholder: a summary that links to ``{{...}}`` is worse
    than one with no link at all.
    """
    if artifact_url:
        return template.replace(ARTIFACT_URL, artifact_url)
    kept = []
    for line in template.splitlines(keepends=True):
        if ARTIFACT_URL not in line:
            kept.append(line)
            continue
        # A links line keeps its other links; a table cell falls back to text.
        parts = [p for p in line.rstrip("\n").split(" · ") if ARTIFACT_URL not in p]
        if parts and line.startswith("["):
            kept.append(" · ".join(parts) + "\n")
        elif "|" in line:
            kept.append(line.replace(f"[JSON + HTML]({ARTIFACT_URL})", "local output"))
    return "".join(kept)


def status_line(
    recorder: BenchmarkRecorder, gate: stats.GateResult, gated: list[Row]
) -> tuple[str, str]:
    """One status word and a sentence, distinct for every kind of outcome."""
    inconclusive = sum(
        r.comparison.verdict is stats.Verdict.INCONCLUSIVE for r in gated
    )
    improved = sum(r.comparison.verdict is stats.Verdict.IMPROVED for r in gated)
    skipped = len(recorder.skipped)
    if neutral(recorder):
        return "NEUTRAL", "Same commit: there is no code difference to benchmark."
    if gate.nothing_measured:
        return "NOTHING MEASURED", "The benchmark produced no comparisons."
    if not gate.trustworthy:
        return (
            "UNTRUSTWORTHY",
            "The A/A control detected bias; results are shown but cannot fail "
            "the build.",
        )
    if gate.regressions:
        return (
            "REGRESSION",
            f"{len(gate.regressions)} confirmed regression(s); {inconclusive} "
            f"unresolved and {improved} improved gated comparison(s).",
        )
    if inconclusive:
        return (
            "INCONCLUSIVE",
            f"No confirmed regressions, but {inconclusive} gated comparison(s) "
            "could not be resolved.",
        )
    if skipped:
        return (
            "PARTIAL",
            f"No regressions in what was measured, but {skipped} cell(s) did not "
            "run; coverage is incomplete.",
        )
    return "PASS", f"No confirmed regressions; {improved} gated comparison(s) improved."


def underpowered_warning(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> str | None:
    """Say so when the run did not buy the precision it was asked for.

    A K-arm round costs K invocations, so at a fixed budget the round count
    falls as arms are added and every interval widens. Without this, too
    small a budget comes back as a wall of INCONCLUSIVE with nothing saying
    that more time was the missing ingredient. Returns None when every gated
    contrast reached the precision target.
    """
    widest, rounds = 0.0, 0
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
    # Width falls as 1/sqrt(n), so closing a factor-f gap costs f^2 the rounds.
    shortfall = (widest / target) ** 2
    return (
        f"Underpowered: the widest contrast reached "
        f"+/-{(math.exp(widest) - 1) * 100:.1f}% after {rounds} rounds, against a "
        f"+/-{(math.exp(target) - 1) * 100:.1f}% target. A {n_arms}-arm round costs "
        f"{n_arms} invocations; reaching the target needs about {shortfall:.1f}x the "
        f"rounds, so roughly {config.budget_seconds * shortfall:.0f}s of budget "
        f"(currently {config.budget_seconds:.0f}s) and max-rounds above "
        f"{math.ceil(rounds * shortfall)}."
    )


# --- Rows -------------------------------------------------------------------


def _rows(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
) -> list[Row]:
    rows: list[Row] = []
    for result in recorder.results:
        for a, b in result.contrast_pairs():
            for metric in METRICS:
                c = gate.comparisons.get(contrast_key(result.cell_id, a, b, metric))
                if c is None:
                    continue
                rows.append(
                    Row(
                        result=result,
                        a=a,
                        b=b,
                        metric=metric,
                        comparison=c,
                        gated=metric in config.gated_metrics
                        and not result.control
                        and result.is_reference_pair(a, b),
                    )
                )
    return rows


def _attention_order(row: Row) -> tuple[int, float, str, int]:
    order = {
        stats.Verdict.REGRESSION: 0,
        stats.Verdict.INCONCLUSIVE: 1,
        stats.Verdict.IMPROVED: 2,
    }
    ratio = row.comparison.ratio
    magnitude = abs(math.log(ratio)) if math.isfinite(ratio) and ratio > 0 else 0.0
    return (
        order.get(row.comparison.verdict, 3),
        -round(magnitude, 3),
        row.result.cell_id,
        METRICS.index(row.metric),
    )


# --- Provenance -------------------------------------------------------------


def _installation(metadata: Mapping[str, object]) -> Mapping[str, object]:
    installed = metadata.get("installation")
    return installed if isinstance(installed, Mapping) else {}


def _installed_sdk(metadata: Mapping[str, object]) -> str:
    return str(_installation(metadata).get("sdk", ""))


def _sources(metadata: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    """Installed arms by dist tag, which is what an arm id is."""
    arms = _installation(metadata).get("arms", [])
    if not isinstance(arms, list):
        return {}
    return {
        str(a["installed_tag"]): a
        for a in arms
        if isinstance(a, Mapping) and a.get("installed_tag")
    }


def _repo_url(source: Mapping[str, object] | None) -> str:
    if source is None:
        return ""
    repo = str(source.get("repository", ""))
    if not repo.startswith("https://"):
        return ""
    return repo.removesuffix(".git").rstrip("/")


def _commit_link(source: Mapping[str, object] | None) -> str:
    repo = _repo_url(source)
    sha = str(source.get("commit_sha", "")) if source else ""
    if not (repo and sha):
        return "—"
    return f"[`{sha[:8]}`]({repo}/commit/{sha})"


def _compare_link(
    reference: Mapping[str, object] | None, candidate: Mapping[str, object] | None
) -> str:
    repo = _repo_url(reference)
    if not repo or repo != _repo_url(candidate):
        return "—"
    a = str(reference.get("commit_sha", "")) if reference else ""
    b = str(candidate.get("commit_sha", "")) if candidate else ""
    return f"[diff]({repo}/compare/{a}...{b})" if a and b else "—"


def _provenance(recorder: BenchmarkRecorder) -> list[str]:
    """The compared builds: what was asked for and which commit it was."""
    sources = _sources(recorder.metadata)
    result = next((r for r in recorder.results if not r.control), None)
    lines = [
        "### Compared builds",
        "",
        "| arm | role | requested | commit | compare to reference |",
        "| --- | --- | --- | --- | --- |",
    ]
    if result is None:
        if not sources:
            return []
        for i, (tag, source) in enumerate(sources.items()):
            lines.append(
                f"| `{_md(tag)}` | {'**reference**' if i == 0 else 'candidate'} "
                f"| {_md(str(source.get('requested_alias', tag)))} "
                f"| {_commit_link(source)} | — |"
            )
        return lines + [""]
    reference = sources.get(result.reference)
    for arm in result.arm_ids:
        source = sources.get(arm)
        role = "**reference**" if arm == result.reference else _role(result, arm)
        requested = (
            _md(str(source.get("requested_alias", arm)))
            if source
            else "provenance unavailable"
        )
        compare = "—" if arm == result.reference else _compare_link(reference, source)
        lines.append(
            f"| {_arm(result, arm)} | {role} | {requested} "
            f"| {_commit_link(source)} | {compare} |"
        )
    return lines + [""]


def _links(metadata: Mapping[str, object]) -> list[str]:
    links = [f"[Raw samples and HTML report]({ARTIFACT_URL})"]
    run_url = str(metadata.get("github_run_url", ""))
    if run_url:
        links.append(f"[Workflow run]({run_url})")
    return [" · ".join(links), ""]


# --- Effects ----------------------------------------------------------------


def effect_overview(rows: list[Row], threshold: float) -> list[str]:
    """A shared-scale CI strip per attention row, readable in a monospace block."""
    labels = [f"{_cell_label(r.result)} {METRIC_LABELS[r.metric][0]}" for r in rows]
    roles = [_role(r.result, r.b) for r in rows]
    label_width = min(30, max(map(len, labels), default=0))
    role_width = max(map(len, roles), default=0)
    width = 57
    threshold_log = math.log(threshold)
    observed = [
        abs(math.log(v))
        for r in rows
        for v in (r.comparison.ratio, r.comparison.ci_low, r.comparison.ci_high)
        if math.isfinite(v) and v > 0
    ]
    span = max(3 * threshold_log, max(observed, default=0.0) * 1.05)
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
        "Shared tail-compressed log-ratio scale: `┆` marks ±the threshold and `│` "
        "no change; `◆` means the CI is narrower than one character.",
        "",
        "```text",
        f"{'arm':<{role_width}}  {'measurement':<{label_width}}  {''.join(axis)}",
    ]
    for role, label, row in zip(roles, labels, rows, strict=True):
        lines.append(
            f"{role:<{role_width}}  {label[:label_width]:<{label_width}}  "
            f"{effect_strip(row.comparison, threshold, width=width, span=span)} "
            f"{_pct(row.comparison.ratio):>7} {row.comparison.verdict}"
        )
    return lines + ["```", ""]


def effect_strip(
    c: stats.PairedComparison,
    threshold: float,
    *,
    width: int = 57,
    span: float | None = None,
) -> str:
    """A fixed-width CI strip on a symmetric, tail-compressed log scale.

    The threshold band keeps a third of the width whatever the largest effect,
    so a 3x outlier cannot flatten every ordinary effect into one character.
    """
    chars = [" "] * width
    threshold_log = math.log(threshold)
    span = span or 3 * threshold_log

    def unit(value: float) -> float:
        magnitude = abs(value)
        if magnitude <= threshold_log:
            scaled = magnitude / threshold_log / 3
        else:
            tail = max(span - threshold_log, 1e-12)
            # Ten percent of either edge stays free, so the largest effect
            # looks extreme without looking clipped.
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
    collapsed: int | None = None
    if math.isfinite(c.ci_low) and math.isfinite(c.ci_high):
        lo, hi = sorted((pos(c.ci_low), pos(c.ci_high)))
        if lo == hi:
            collapsed = lo
            chars[lo] = "◆"
        else:
            for i in range(lo, hi + 1):
                if chars[i] == " ":
                    chars[i] = "━"
            chars[lo], chars[hi] = "[", "]"
    if math.isfinite(c.ratio) and c.ratio > 0:
        point = pos(c.ratio)
        chars[point] = "◆" if point == collapsed else "●"
    return "".join(chars)


def braille_trace(
    values: Iterable[float], threshold: float, *, max_chars: int = 24
) -> str:
    """Per-round ratios as a compact trace, two rounds per Braille glyph."""
    logs = [math.log(v) for v in values if math.isfinite(v) and v > 0]
    if not logs:
        return "—"
    limit = max_chars * 2
    if len(logs) > limit:
        # Median bins keep the robust character of the reported estimator.
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
            # Braille rows run top to bottom; slower belongs at the top.
            level = max(0, min(3, round((span - value) / (2 * span) * 3)))
            bits |= 1 << dot_bits[column][level]
        glyphs.append(chr(0x2800 + bits))
    return "".join(glyphs)


def _stability(attention: list[Row], config: BenchConfig) -> list[str]:
    if not attention:
        return []
    lines = [
        "<details>",
        "<summary><strong>Round stability for the rows above</strong></summary>",
        "",
        "Each Braille glyph is two rounds at four levels, centred on no change "
        "and never tighter than the threshold.",
        "",
        "```text",
    ]
    for row in attention:
        a = row.result.samples.get(row.a, {}).get(row.metric, [])
        b = row.result.samples.get(row.b, {}).get(row.metric, [])
        ratios = [y / x for x, y in zip(a, b, strict=True) if x > 0 and y > 0]
        if not ratios:
            continue
        slower = sum(r > 1 for r in ratios)
        label = f"{_cell_label(row.result)} {METRIC_LABELS[row.metric][0]}"
        lines.append(
            f"{label[:28]:<28} {braille_trace(ratios, config.threshold):<24} "
            f"{slower}/{len(ratios)} rounds slower; median "
            f"{_pct(statistics.median(ratios))}"
        )
    return lines + ["```", "", "</details>", ""]


# --- Sections ---------------------------------------------------------------


def _candidates(
    conclusions: list[Conclusion], recorder: BenchmarkRecorder
) -> list[str]:
    if not conclusions:
        return []
    results = {r.cell_id: r for r in recorder.results}
    lines = [
        "### Candidate comparisons",
        "",
        "Never fail the build. A winner needs to be faster than every other "
        "candidate, with the A/A control intact.",
        "",
    ]
    for c in conclusions:
        result = results[c.cell_id]
        label = f"**{_md(_cell_label(result))}** ({METRIC_LABELS[c.metric][0]})"
        if c.winner is not None:
            lines.append(f"- {label}: {_arm(result, c.winner)} wins — {_md(c.reason)}.")
        else:
            lines.append(f"- {label}: {_md(c.reason)}.")
        for p in c.pairwise:
            interval = (
                f"{_pct(p.ratio)} [{_pct(p.ci_low)}, {_pct(p.ci_high)}]"
                if math.isfinite(p.ci_low) and math.isfinite(p.ci_high)
                else "no usable interval"
            )
            lines.append(
                f"  - {_arm(result, p.b)} vs {_arm(result, p.a)}: "
                f"{str(p.verdict).lower()}, {interval}"
            )
    return lines + [""]


def _all_measurements(rows: list[Row]) -> list[str]:
    if not rows:
        return []
    lines = [
        "<details>",
        "<summary><strong>All measurements, controls and statistics</strong></summary>",
        "",
        "| cell | contrast | metric | a median | b median | ratio b/a (95% CI) | p (BH) | n | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        c = row.comparison
        qualifier = (
            "A/A control"
            if row.result.control
            else "candidates"
            if row.candidate_pair
            else ""
            if row.gated
            else "ungated"
        )
        label = METRIC_LABELS[row.metric][0] + (f" ({qualifier})" if qualifier else "")
        lines.append(
            f"| {_md(row.result.cell_id)} "
            f"| {_arm(row.result, row.b)} vs {_arm(row.result, row.a)} | {label} "
            f"| {format_metric(row.metric, c.baseline_median)} "
            f"| {format_metric(row.metric, c.candidate_median)} "
            f"| {ratio_cell(c)} | {p_cell(c)} | {c.n_rounds} | {verdict_cell(c)} |"
        )
    return lines + ["", "</details>", ""]


def _not_measured(recorder: BenchmarkRecorder) -> list[str]:
    if not recorder.skipped:
        return []
    title = "Cells not run (same commit)" if neutral(recorder) else "Not measured"
    lines = ["<details open>", f"<summary><strong>{title}</strong></summary>", ""]
    lines += [
        f"- `{_md(cid)}`: {_md(why)}" for cid, why in sorted(recorder.skipped.items())
    ]
    return lines + ["", "</details>", ""]


def _method(config: BenchConfig, n_arms: int) -> list[str]:
    threshold_pct = (config.threshold - 1) * 100
    return [
        "<details>",
        "<summary><strong>How to read this</strong></summary>",
        "",
        f"A paired {n_arms}-arm comparison: every build ran in the same randomized "
        "rounds on one runner. A candidate regresses only when its 95% CI against "
        f"the reference is wholly beyond +{threshold_pct:.0f}% and its BH-adjusted "
        f"p is below {stats.DEFAULT_ALPHA}. The loop stops on interval width, never "
        "on significance. PASS means the run could have found an effect of that "
        "size; INCONCLUSIVE does not mean no change.",
        "",
        "</details>",
        "",
    ]


def _run_facts(
    recorder: BenchmarkRecorder, config: BenchConfig, gate: stats.GateResult
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
    round_text = f"{min(rounds)}–{max(rounds)}" if rounds else "0"
    return [
        "### Run facts",
        "",
        "| result cells | rounds/cell | elapsed | A/A noise | platform | runner | evidence |",
        "| ---: | ---: | ---: | ---: | --- | --- | --- |",
        f"| {len(rounds)} | {round_text} | {elapsed:.0f}s | {noise_text} "
        f"| {_md(str(metadata.get('platform_version', 'unknown')))} "
        f"| {_md(str(metadata.get('runner_os') or metadata.get('platform', 'unknown')))} "
        f"| [JSON + HTML]({ARTIFACT_URL}) |",
        "",
        f"<sub>seed {config.seed}; {config.warmup} warm-up rounds; "
        f"{config.min_rounds}–{config.max_rounds} measured rounds allowed; "
        f"{len(recorder.skipped)} cell(s) skipped.</sub>",
    ]


# --- Small formatting helpers -----------------------------------------------


def _md(value: str) -> str:
    """Neutralize characters that would break a table cell or a link."""
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "'")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", " ")
    )


def _arm(result: CellResult, arm: str) -> str:
    """An arm by its build label; A/A copies say which copy they are."""
    _, sep, copy = arm.partition("#")
    label = result.arm_labels.get(arm, arm)
    text = f"{label} copy {copy}" if sep else label
    return f"`{text.replace('`', "'")}`"


def _role(result: CellResult, arm: str) -> str:
    if arm == result.reference:
        return "reference"
    try:
        return f"candidate {chr(ord('A') + result.candidates.index(arm))}"
    except ValueError:
        return arm


def _cell_label(result: CellResult) -> str:
    return result.cell_id.removeprefix(f"{result.sdk}-").replace("-", " / ")


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
    return f"{(ratio - 1) * 100:+.1f}%" if math.isfinite(ratio) else "—"


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
