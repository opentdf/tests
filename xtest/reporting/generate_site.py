"""Generate the community SDK conformance homepage for GitHub Pages.

Usage (from xtest/ cwd):
  uv run python -m reporting.generate_site \\
    --input-dir test-results \\
    --output-dir site

Expects one subdirectory per Community X-Test artifact under --input-dir,
each containing pytest junit XML files (any depth) and optionally a
capability snapshot (supports.json, written by reporting.export_supports).
Every junit testcase id encodes the encrypt/decrypt pair
(``test_tdf_roundtrip[small-python@main-go@v0.35.0-...]``), which is what
the interop matrix is built from.

Outputs index.html (self-contained, no external assets) and summary.json.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from defusedxml.ElementTree import parse as _safe_xml_parse

OFFICIAL_SDKS = ("go", "java", "js")
COMMUNITY_SDKS = ("python", "rust", "swift")

SDK_REPOS = {
    "python": "https://github.com/b-long/opentdf-python-sdk",
    "rust": "https://github.com/arkavo-org/opentdf-rs",
    "swift": "https://github.com/arkavo-org/OpenTDFKit",
    "go": "https://github.com/opentdf/otdfctl",
}

# encrypt/decrypt peers inside a pytest param id, e.g. "python@main" or
# "go@v0.35.0". Versions are dist channels (main/lts/vX.Y.Z, optional
# -rcN/-betaN suffix); parametrize order guarantees encrypt before decrypt.
_PEER_RE = re.compile(
    r"\b(go|java|js|python|rust|swift)@([\w.+]+(?:-(?:rc|beta|alpha)\.?\d+)?)"
)


@dataclass
class Counts:
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped

    @property
    def run(self) -> int:
        return self.passed + self.failed

    def add(self, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)

    def merge(self, other: Counts) -> None:
        self.passed += other.passed
        self.failed += other.failed
        self.skipped += other.skipped

    def as_dict(self) -> dict[str, int]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
        }


@dataclass
class Report:
    """Aggregated results across every artifact directory."""

    pair_counts: dict[tuple[str, str], Counts] = field(
        default_factory=lambda: defaultdict(Counts)
    )
    sdk_counts: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    snapshots: dict[str, dict] = field(default_factory=dict)
    junit_files: int = 0


def _testcase_outcome(case: ET.Element) -> str:
    for child in case:
        if child.tag in ("failure", "error"):
            return "failed"
        if child.tag == "skipped":
            return "skipped"
    return "passed"


def collect(input_dir: Path) -> Report:
    report = Report()
    for junit in sorted(input_dir.rglob("*.junit.xml")):
        try:
            tree = _safe_xml_parse(junit)
        except ET.ParseError:
            continue
        root = tree.getroot() if tree is not None else None
        if root is None:
            continue
        report.junit_files += 1
        for case in root.iter("testcase"):
            outcome = _testcase_outcome(case)
            peers = _PEER_RE.findall(case.attrib.get("name", ""))
            if len(peers) >= 2:
                enc = f"{peers[0][0]}@{peers[0][1]}"
                dec = f"{peers[1][0]}@{peers[1][1]}"
                report.pair_counts[(enc, dec)].add(outcome)
                for sdk in {peers[0][0], peers[1][0]}:
                    report.sdk_counts[sdk].add(outcome)

    for supports in sorted(input_dir.rglob("supports.json")):
        try:
            snap = json.loads(supports.read_text())
        except json.JSONDecodeError, OSError:
            continue
        sdk = snap.get("sdk")
        if isinstance(sdk, str) and sdk:
            report.snapshots[sdk] = snap
    return report


def _sdk_sort_key(peer: str) -> tuple[int, str]:
    name = peer.split("@", 1)[0]
    return (0 if name in COMMUNITY_SDKS else 1, peer)


def _esc(value: object) -> str:
    return html.escape(str(value))


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """
:root {
  --surface: #fcfcfb; --panel: #f4f4f1; --ink: #0b0b0b; --ink-2: #52514e;
  --line: #e3e2dd; --accent: #2a78d6;
  --good: #0ca30c; --bad: #d03b3b; --warn: #b97f00;
  --good-bg: rgba(12, 163, 12, 0.11); --bad-bg: rgba(208, 59, 59, 0.11);
  --warn-bg: rgba(250, 178, 25, 0.16); --skip-bg: rgba(82, 81, 78, 0.08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface: #1a1a19; --panel: #222220; --ink: #ffffff; --ink-2: #c3c2b7;
    --line: #373633; --accent: #3987e5; --warn: #fab219;
    --good-bg: rgba(12, 163, 12, 0.22); --bad-bg: rgba(208, 59, 59, 0.24);
    --warn-bg: rgba(250, 178, 25, 0.18); --skip-bg: rgba(195, 194, 183, 0.10);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--surface); color: var(--ink);
  font: 400 0.9375rem/1.6 ui-monospace, "SF Mono", "Cascadia Code", Menlo,
    Consolas, "Liberation Mono", monospace;
}
main { max-width: 66rem; margin: 0 auto; padding: 3.5rem 1.5rem 4rem; }
a { color: var(--accent); text-underline-offset: 3px; }
h1, h2 { line-height: 1.15; letter-spacing: -0.03em; }
h1 { font-size: clamp(2rem, 5vw, 3.1rem); margin: 0.4rem 0 1rem; font-weight: 700; }
h2 { font-size: 1.25rem; margin: 3rem 0 0.25rem; }
.eyebrow {
  color: var(--accent); font-size: 0.72rem; letter-spacing: 0.22em;
  text-transform: uppercase;
}
.lede { color: var(--ink-2); max-width: 46rem; margin: 0 0 1.5rem; }
.section-note { color: var(--ink-2); font-size: 0.82rem; margin: 0 0 1rem; }
.provenance {
  display: flex; flex-wrap: wrap; gap: 0.4rem 1.6rem; padding: 0.9rem 1.1rem;
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  font-size: 0.82rem;
}
.provenance b { font-weight: 400; color: var(--ink-2); }
.cards {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem; margin-top: 1.25rem;
}
.card {
  border: 1px solid var(--line); border-radius: 10px; padding: 1.1rem 1.2rem;
  background: var(--panel); display: flex; flex-direction: column; gap: 0.45rem;
}
.card h3 { margin: 0; font-size: 1.2rem; letter-spacing: -0.02em; }
.card .ref { color: var(--ink-2); font-size: 0.8rem; overflow-wrap: anywhere; }
.card .nums { font-size: 0.85rem; }
.pill {
  align-self: flex-start; border-radius: 999px; padding: 0.15rem 0.7rem;
  font-size: 0.78rem; border: 1px solid transparent;
}
.pill.good { background: var(--good-bg); color: var(--good); border-color: var(--good); }
.pill.bad { background: var(--bad-bg); color: var(--bad); border-color: var(--bad); }
.pill.none { background: var(--skip-bg); color: var(--ink-2); border-color: var(--line); }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; font-size: 0.85rem; margin: 0.75rem 0 0.5rem; }
th, td { border: 1px solid var(--line); padding: 0.45rem 0.7rem; text-align: left; }
th { background: var(--panel); font-weight: 400; color: var(--ink-2); }
th.peer, td.feature { color: var(--ink); white-space: nowrap; }
tbody tr:hover td { filter: brightness(0.96); }
@media (prefers-color-scheme: dark) { tbody tr:hover td { filter: brightness(1.18); } }
td.ok { background: var(--good-bg); }
td.fail { background: var(--bad-bg); }
td.warn { background: var(--warn-bg); }
td.skip, td.none { background: var(--skip-bg); color: var(--ink-2); }
td.blank { color: var(--ink-2); text-align: center; }
.legend { color: var(--ink-2); font-size: 0.78rem; display: flex; flex-wrap: wrap; gap: 1.2rem; }
.legend span::before { content: ""; }
footer {
  margin-top: 3.5rem; padding-top: 1.25rem; border-top: 1px solid var(--line);
  color: var(--ink-2); font-size: 0.82rem;
}
footer p { max-width: 46rem; }
.empty {
  border: 1px dashed var(--line); border-radius: 10px; padding: 2rem;
  color: var(--ink-2); margin-top: 1.5rem;
}
"""


def _verdict(counts: Counts) -> tuple[str, str, str]:
    """(css class, glyph, label) for an SDK scorecard."""
    if counts.run == 0:
        return "none", "—", "no results"
    if counts.failed:
        return "bad", "✕", "failing"
    return "good", "✓", "conformant"


def _render_cards(report: Report) -> str:
    # Scorecards are for the community SDKs under test; the go reference
    # peer appears in the matrices instead.
    sdks = sorted(
        (set(report.snapshots) | set(report.sdk_counts)) & set(COMMUNITY_SDKS)
    )
    cards = []
    for sdk in sdks:
        counts = report.sdk_counts.get(sdk, Counts())
        snap = report.snapshots.get(sdk, {})
        cls, glyph, label = _verdict(counts)
        ref = snap.get("sdk_ref", "")
        repo = SDK_REPOS.get(sdk)
        title = f'<a href="{_esc(repo)}">{_esc(sdk)}</a>' if repo else _esc(sdk)
        tier = _esc(snap["tier"]) if snap.get("tier") else ""
        cards.append(
            f'<div class="card">'
            f"<h3>{title}</h3>"
            f'<span class="pill {cls}">{glyph} {label}</span>'
            f'<span class="ref">{_esc(ref) if ref else "release not recorded"}</span>'
            f'<span class="nums">{counts.passed} passed · {counts.failed} failed'
            f" · {counts.skipped} skipped</span>"
            f'<span class="ref">{tier}</span>'
            f"</div>"
        )
    return "".join(cards)


def _pair_cell(counts: Counts | None) -> str:
    if counts is None:
        return '<td class="blank" title="pair not exercised">·</td>'
    if counts.run == 0:
        return f'<td class="skip" title="all skipped">— {counts.skipped} skipped</td>'
    if counts.failed:
        return (
            f'<td class="fail" title="{counts.failed} of {counts.run} failed">'
            f"✕ {counts.passed}/{counts.run}</td>"
        )
    return f'<td class="ok" title="all passed">✓ {counts.passed}/{counts.run}</td>'


def _render_matrix(report: Report) -> str:
    if not report.pair_counts:
        return ""
    encrypters = sorted({e for e, _ in report.pair_counts}, key=_sdk_sort_key)
    decrypters = sorted({d for _, d in report.pair_counts}, key=_sdk_sort_key)
    head = "".join(f'<th class="peer">{_esc(d)}</th>' for d in decrypters)
    body = []
    for enc in encrypters:
        cells = "".join(
            _pair_cell(report.pair_counts.get((enc, dec))) for dec in decrypters
        )
        body.append(f'<tr><th class="peer">{_esc(enc)}</th>{cells}</tr>')
    return f"""
  <h2 id="interop">Interop matrix</h2>
  <p class="section-note">Rows encrypt, columns decrypt. Each cell counts Base
  TDF round-trips against a live platform and KAS in the source run.</p>
  <div class="scroll"><table>
    <thead><tr><th>encrypt ↓ / decrypt →</th>{head}</tr></thead>
    <tbody>{"".join(body)}</tbody>
  </table></div>
  <p class="legend"><span>✓ all round-trips passed</span>
  <span>✕ at least one failure (passed/run)</span>
  <span>— skipped</span><span>· pair not exercised</span></p>
"""


_FEATURE_GLYPHS = {
    "supported": ("ok", "✓ yes"),
    "unsupported": ("none", "–"),
}


def _render_capabilities(report: Report) -> str:
    # Every SDK in the conformance runs gets a column, snapshot or not —
    # community SDKs always, plus any peer seen in junit results (e.g. go).
    sdks = sorted(
        set(report.snapshots) | set(COMMUNITY_SDKS) | set(report.sdk_counts),
        key=lambda s: (0 if s in COMMUNITY_SDKS else 1, s),
    )
    features: set[str] = set()
    for snap in report.snapshots.values():
        features.update((snap.get("supports") or {}).keys())
    if not features:
        return ""
    head = "".join(f'<th class="peer">{_esc(s)}</th>' for s in sdks)
    rows = []
    for feature in sorted(features):
        cells = []
        for sdk in sdks:
            snap = report.snapshots.get(sdk)
            value = ((snap or {}).get("supports") or {}).get(feature)
            if snap is None:
                cells.append('<td class="blank" title="no snapshot yet">·</td>')
            elif value is None:
                cells.append('<td class="blank" title="not probed">·</td>')
            else:
                cls, text = _FEATURE_GLYPHS.get(
                    str(value), ("warn", f"? {_esc(value)}")
                )
                cells.append(f'<td class="{cls}">{text}</td>')
        rows.append(
            f'<tr><td class="feature">{_esc(feature)}</td>{"".join(cells)}</tr>'
        )
    return f"""
  <h2 id="capabilities">Capability matrix</h2>
  <p class="section-note">What each SDK's CLI reports via <code>cli.sh
  supports &lt;feature&gt;</code>. “–” means the SDK does not implement the
  feature; “?” means the probe errored; “·” means no capability snapshot
  for that SDK yet.</p>
  <div class="scroll"><table>
    <thead><tr><th>feature</th>{head}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
"""


def _render_provenance(report: Report, generated: str) -> str:
    any_snap = next(iter(report.snapshots.values()), {})
    run_id = os.environ.get("SOURCE_RUN_ID") or any_snap.get("run_id")
    repo = os.environ.get("GITHUB_REPOSITORY") or any_snap.get("repo")
    run_url = os.environ.get("SOURCE_RUN_URL")
    if not run_url and run_id and repo:
        run_url = f"https://github.com/{repo}/actions/runs/{run_id}"
    items = []
    if run_url and run_id:
        items.append(
            f'<span><b>source run</b> <a href="{_esc(run_url)}">#{_esc(run_id)}</a></span>'
        )
    if any_snap.get("platform_ref"):
        items.append(f"<span><b>platform</b> {_esc(any_snap['platform_ref'])}</span>")
    if any_snap.get("go_channel"):
        items.append(f"<span><b>go peer</b> {_esc(any_snap['go_channel'])}</span>")
    items.append(f"<span><b>generated</b> {_esc(generated)}</span>")
    return f'<div class="provenance">{"".join(items)}</div>'


def _render_empty() -> str:
    return """
  <div class="empty">No conformance data yet. This page publishes
  automatically after the next <a
  href="https://github.com/arkavo-org/opentdf-tests/actions/workflows/community-xtest.yml">Community
  X-Test</a> run completes on <code>main</code>.</div>
"""


def render_html(report: Report, generated: str) -> str:
    sdk_total = len(
        (set(report.snapshots) | set(report.sdk_counts)) & set(COMMUNITY_SDKS)
    )
    if sdk_total:
        body = (
            f'<div class="cards">{_render_cards(report)}</div>'
            + _render_matrix(report)
            + _render_capabilities(report)
        )
    else:
        body = _render_empty()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="light dark"/>
  <title>OpenTDF Community SDK Conformance</title>
  <style>{_CSS}</style>
</head>
<body>
<main>
  <p class="eyebrow">OpenTDF · Community Conformance</p>
  <h1>SDK Conformance Report</h1>
  <p class="lede">Continuous interoperability results for community OpenTDF
  SDKs. Every run encrypts with one SDK, decrypts with another, and verifies
  the round-trip against a live platform and KAS — so a green cell means two
  independent implementations really exchanged a Base TDF.</p>
  {_render_provenance(report, generated)}
  {body}
  <footer>
    <p><strong>Add your SDK.</strong> Implement the <code>cli.sh</code>
    contract and open a PR against
    <a href="https://github.com/arkavo-org/opentdf-tests">arkavo-org/opentdf-tests</a>
    — see <a
    href="https://github.com/arkavo-org/opentdf-tests/blob/main/docs/community-conformance.md">docs/community-conformance.md</a>
    for the conformance contract and ownership.</p>
    <p>Community fork of <a href="https://github.com/opentdf/tests">opentdf/tests</a>;
    not an official OpenTDF certification. Machine-readable data:
    <a href="summary.json">summary.json</a>.</p>
  </footer>
</main>
</body>
</html>
"""


def generate(input_dir: Path, output_dir: Path) -> None:
    report = collect(input_dir)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(render_html(report, generated))

    summary = {
        "generated_at": generated,
        "source_run_id": os.environ.get("SOURCE_RUN_ID"),
        "junit_files": report.junit_files,
        "sdks": [
            {
                "sdk": sdk,
                "sdk_ref": report.snapshots.get(sdk, {}).get("sdk_ref"),
                "tier": report.snapshots.get(sdk, {}).get("tier"),
                "counts": report.sdk_counts.get(sdk, Counts()).as_dict(),
                "supports": report.snapshots.get(sdk, {}).get("supports"),
            }
            for sdk in sorted(set(report.snapshots) | set(report.sdk_counts))
        ],
        "pairs": [
            {"encrypt": enc, "decrypt": dec, **counts.as_dict()}
            for (enc, dec), counts in sorted(report.pair_counts.items())
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(
        f"Wrote {output_dir / 'index.html'} "
        f"({report.junit_files} junit files, {len(report.snapshots)} snapshots, "
        f"{len(report.pair_counts)} interop pairs)"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, default=Path("test-results"))
    p.add_argument("--output-dir", type=Path, default=Path("site"))
    args = p.parse_args()
    generate(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
