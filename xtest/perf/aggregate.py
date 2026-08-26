"""Pure-stdlib cross-SDK renderer for benchmark JSON artifacts.

The workflow runs this after downloading every matrix artifact. It has no
third-party imports, so the roll-up needs no dependency sync and can still
explain a partially failed matrix whose artifact set is incomplete. It does
run through xtest's pinned interpreter: stdlib-only does not imply that a
hosted runner's older Python understands the repository's target syntax.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Run:
    sdk: str
    document: dict[str, Any]

    @property
    def gated(self) -> list[tuple[str, str, dict[str, Any]]]:
        metrics = set(self.document.get("config", {}).get("gated_metrics", []))
        rows: list[tuple[str, str, dict[str, Any]]] = []
        for cell in self.document.get("cells", []):
            if cell.get("control"):
                continue
            reference = cell.get("reference")
            for name, by_metric in cell.get("contrasts", {}).items():
                if not name.endswith(f"_vs_{reference}"):
                    continue
                for metric, comparison in by_metric.items():
                    if metric in metrics:
                        rows.append((str(cell.get("id", "")), metric, comparison))
        return rows

    @property
    def inconclusive(self) -> int:
        return sum(c.get("verdict") == "INCONCLUSIVE" for _, _, c in self.gated)

    @property
    def improvements(self) -> int:
        return sum(c.get("verdict") == "IMPROVED" for _, _, c in self.gated)

    @property
    def regressions(self) -> list[tuple[str, str, dict[str, Any]]]:
        return [r for r in self.gated if r[2].get("verdict") == "REGRESSION"]

    @property
    def status(self) -> str:
        if self.document.get("nothing_measured") or not self.gated:
            return "NOTHING MEASURED"
        if not self.document.get("trustworthy", True):
            return "UNTRUSTWORTHY"
        if self.regressions:
            return "REGRESSION"
        if self.inconclusive:
            return "INCONCLUSIVE"
        return "PASS"


def load_runs(root: Path) -> list[Run]:
    runs: list[Run] = []
    for path in root.rglob("*.json"):
        try:
            document = json.loads(path.read_text())
        except OSError, json.JSONDecodeError:
            continue
        if not isinstance(document, dict) or "config" not in document:
            continue
        metadata = document.get("metadata", {})
        sdk = str(metadata.get("sdk", "")) if isinstance(metadata, dict) else ""
        if not sdk:
            cells = document.get("cells", [])
            cell_id = str(cells[0].get("id", "")) if cells else path.stem
            sdk = cell_id.split("-", 1)[0]
        runs.append(Run(sdk=sdk, document=document))
    order = {"go": 0, "java": 1, "js": 2}
    return sorted(runs, key=lambda r: (order.get(r.sdk, 99), r.sdk))


def markdown(
    runs: list[Run],
    *,
    artifact_urls: dict[str, str] | None = None,
    run_url: str = "",
    expected_sdks: list[str] | None = None,
) -> str:
    artifact_urls = artifact_urls or {}
    expected = expected_sdks or [run.sdk for run in runs]
    missing = [sdk for sdk in expected if sdk not in {run.sdk for run in runs}]
    overall = _overall_status(runs, missing)
    lines = [
        f"# SDK performance benchmark roll-up — {overall}",
        "",
        "### TL;DR",
        "",
        f"> **{_overall_headline(runs, missing)}**",
        "",
    ]
    if run_url:
        lines += [f"[Workflow run]({run_url})", ""]
    if not runs:
        return "\n".join(
            lines
            + [
                "> [!WARNING]",
                "> No benchmark JSON artifacts were available. The matrix may have "
                "failed before session-final reporting.",
                "",
            ]
        )

    lines += [
        "| SDK | outcome | compared builds | regressions | unresolved | improvements | A/A noise | evidence |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for run in runs:
        noise = run.document.get("noise_floor", {})
        width = noise.get("width_ratio") if isinstance(noise, dict) else None
        noise_text = (
            f"±{(float(width) - 1) * 100:.1f}%"
            if isinstance(width, (int, float)) and math.isfinite(width)
            else "—"
        )
        evidence = (
            f"[artifact]({artifact_urls[run.sdk]})"
            if artifact_urls.get(run.sdk)
            else "—"
        )
        lines.append(
            f"| **{run.sdk}** | **{run.status}** | {_arms(run)} "
            f"| {len(run.regressions)} | {run.inconclusive} | {run.improvements} "
            f"| {noise_text} | {evidence} |"
        )
    for sdk in missing:
        lines.append(f"| **{sdk}** | **MISSING** | — | — | — | — | — | — |")

    regressions = [(run, *row) for run in runs for row in run.regressions]
    if regressions:
        lines += [
            "",
            "### Confirmed regressions",
            "",
            "| SDK | measurement | metric | change (95% CI) |",
            "| --- | --- | --- | --- |",
        ]
        for run, cell, metric, comparison in regressions:
            lines.append(f"| {run.sdk} | `{cell}` | {metric} | {_change(comparison)} |")

    lines += [
        "",
        "### Combined run facts",
        "",
        "| matrix results | measured cells | skipped cells | total measured time | platform versions |",
        "| ---: | ---: | ---: | ---: | --- |",
        f"| {len(runs)}/{len(expected)} | {sum(_measured_cells(r) for r in runs)} "
        f"| {sum(len(r.document.get('skipped', {})) for r in runs)} "
        f"| {sum(_elapsed(r) for r in runs):.0f}s "
        f"| {', '.join(_platform_versions(runs)) or 'unknown'} |",
        "",
        "<sub>Each SDK was measured on its own runner. Absolute timings are not "
        "compared across SDKs; this block combines verdicts and run health only.</sub>",
    ]
    return "\n".join(lines) + "\n"


def _overall_status(runs: list[Run], missing: list[str]) -> str:
    for status in ("REGRESSION", "UNTRUSTWORTHY", "NOTHING MEASURED"):
        if any(r.status == status for r in runs):
            return status
    if missing:
        return "INCOMPLETE"
    if any(r.status == "INCONCLUSIVE" for r in runs):
        return "INCONCLUSIVE"
    return "PASS" if runs else "NO RESULTS"


def _overall_headline(runs: list[Run], missing: list[str]) -> str:
    if not runs:
        return "No benchmark result artifacts were found."
    regressions = sum(len(r.regressions) for r in runs)
    unresolved = sum(r.inconclusive for r in runs)
    outcomes = ", ".join(f"{r.sdk}: {r.status}" for r in runs)
    missing_text = f" Missing result(s): {', '.join(missing)}." if missing else ""
    return (
        f"{regressions} confirmed regression(s), {unresolved} unresolved gated "
        f"comparison(s) across {len(runs)} available SDK result(s). {outcomes}."
        f"{missing_text}"
    )


def _arms(run: Run) -> str:
    sources = run.document.get("metadata", {}).get("arm_sources", [])
    if isinstance(sources, list) and sources:
        return " → ".join(
            f"`{s.get('tag', '?')}`" for s in sources if isinstance(s, dict)
        )
    cells = [c for c in run.document.get("cells", []) if not c.get("control")]
    return " → ".join(f"`{a}`" for a in cells[0].get("arms", [])) if cells else "—"


def _change(comparison: dict[str, Any]) -> str:
    def pct(value: object) -> str:
        return (
            f"{(float(value) - 1) * 100:+.1f}%"
            if isinstance(value, (int, float))
            else "—"
        )

    return (
        f"{pct(comparison.get('ratio'))} "
        f"[{pct(comparison.get('ci_low'))}, {pct(comparison.get('ci_high'))}]"
    )


def _measured_cells(run: Run) -> int:
    return sum(not c.get("control") for c in run.document.get("cells", []))


def _elapsed(run: Run) -> float:
    return sum(float(c.get("elapsed_s", 0)) for c in run.document.get("cells", []))


def _platform_versions(runs: list[Run]) -> list[str]:
    return sorted(
        {
            str(r.document.get("metadata", {}).get("platform_version", ""))
            for r in runs
            if r.document.get("metadata", {}).get("platform_version")
        }
    )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: aggregate.py RESULTS_DIR", file=sys.stderr)
        return 2
    try:
        urls = json.loads(os.environ.get("BENCH_ARTIFACT_URLS", "{}"))
    except json.JSONDecodeError:
        urls = {}
    try:
        expected = json.loads(os.environ.get("BENCH_EXPECTED_SDKS", "[]"))
    except json.JSONDecodeError:
        expected = []
    print(
        markdown(
            load_runs(Path(args[0])),
            artifact_urls=urls if isinstance(urls, dict) else {},
            run_url=os.environ.get("BENCH_RUN_URL", ""),
            expected_sdks=(
                [str(sdk) for sdk in expected] if isinstance(expected, list) else []
            ),
        ),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
