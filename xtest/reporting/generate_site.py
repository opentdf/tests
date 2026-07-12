"""Generate a static HTML capability/interop report for GitHub Pages.

Usage (from xtest/ cwd):
  uv run python -m reporting.generate_site \\
    --input-dir test-results \\
    --output-dir site

Expects directories matching report-<sdk>-<os>/ containing supports.json
and optional junit XML / meta.json.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def _load_supports(report_dir: Path) -> dict:
    path = report_dir / "supports.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _junit_counts(report_dir: Path) -> dict[str, int]:
    total = passed = failed = skipped = 0
    for junit in report_dir.glob("**/*.junit.xml"):
        try:
            root = ET.parse(junit).getroot()
        except ET.ParseError:
            continue
        # pytest may use testsuites or testsuite root
        suites = root.findall("testsuite")
        if root.tag == "testsuite":
            suites = [root]
        for suite in suites:
            total += int(suite.attrib.get("tests", 0))
            failed += int(suite.attrib.get("failures", 0)) + int(
                suite.attrib.get("errors", 0)
            )
            skipped += int(suite.attrib.get("skipped", 0))
    passed = max(0, total - failed - skipped)
    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped}


def generate(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for report_dir in sorted(input_dir.glob("report-*")):
        if not report_dir.is_dir():
            continue
        supports = _load_supports(report_dir)
        counts = _junit_counts(report_dir.parent)  # junit often sibling of report dir
        # also check inside report dir
        inner = _junit_counts(report_dir)
        if inner["total"] > counts["total"]:
            counts = inner
        rows.append(
            {
                "dir": report_dir.name,
                "supports": supports,
                "counts": counts,
            }
        )

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    feature_names: set[str] = set()
    for r in rows:
        feature_names.update((r["supports"].get("supports") or {}).keys())
    features = sorted(feature_names)

    # Capability matrix table
    matrix_rows = []
    for r in rows:
        sdk = r["supports"].get("sdk", r["dir"])
        sup = r["supports"].get("supports") or {}
        cells = "".join(
            f'<td class="{sup.get(f, "missing")}">{sup.get(f, "—")}</td>'
            for f in features
        )
        matrix_rows.append(f"<tr><th>{sdk}</th>{cells}</tr>")

    feature_header = "".join(f"<th>{f}</th>" for f in features)
    interop_rows = []
    for r in rows:
        sdk = r["supports"].get("sdk", r["dir"])
        c = r["counts"]
        interop_rows.append(
            f"<tr><td>{sdk}</td><td>{c['passed']}</td><td>{c['failed']}</td>"
            f"<td>{c['skipped']}</td><td>{c['total']}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>OpenTDF Community Conformance</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }}
    h1, h2 {{ color: #0b3d5c; }}
    table {{ border-collapse: collapse; margin: 1rem 0; font-size: 0.85rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.5rem; }}
    th {{ background: #eef3f7; }}
    td.supported {{ background: #d4edda; }}
    td.unsupported {{ background: #f8d7da; }}
    td.unknown, td.missing {{ background: #fff3cd; }}
    .meta {{ color: #555; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>OpenTDF Community SDK Conformance</h1>
  <p class="meta">Generated {generated}. Stage-1 = community ↔ go@main, Base TDF (<code>tdf</code>) only.</p>

  <h2>Interop summary (junit)</h2>
  <table>
    <tr><th>SDK</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Total</th></tr>
    {"".join(interop_rows) or "<tr><td colspan='5'>No junit data yet</td></tr>"}
  </table>

  <h2>Capability matrix (<code>cli.sh supports</code>)</h2>
  <table>
    <tr><th>SDK</th>{feature_header}</tr>
    {"".join(matrix_rows) or "<tr><td colspan='2'>No supports.json found under report-*</td></tr>"}
  </table>

  <h2>Bug metrics</h2>
  <p>Historical fingerprints roll up when Pages deploy (PR8) merges successive
  <code>history.json</code> artifacts. This snapshot only shows the current run.</p>

  <p class="meta">See docs/community-conformance.md in the tests fork for ownership and stages.</p>
</body>
</html>
"""
    (output_dir / "index.html").write_text(html)
    summary = {
        "generated_at": generated,
        "reports": [
            {
                "dir": r["dir"],
                "sdk": r["supports"].get("sdk"),
                "counts": r["counts"],
            }
            for r in rows
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Wrote {output_dir / 'index.html'} ({len(rows)} report dirs)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", type=Path, default=Path("test-results"))
    p.add_argument("--output-dir", type=Path, default=Path("site"))
    args = p.parse_args()
    generate(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
