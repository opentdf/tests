"""Report formatters for coverage matrix."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .models import CoverageMatrix, TestSuite


class BaseFormatter:
    """Base class for report formatters."""
    
    def format(self, matrix: CoverageMatrix) -> str:
        """Format the coverage matrix into a string."""
        raise NotImplementedError
    
    def save(self, matrix: CoverageMatrix, output_path: Path) -> None:
        """Save the formatted report to a file."""
        output = self.format(matrix)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(output)


class JSONFormatter(BaseFormatter):
    """Format coverage matrix as JSON."""
    
    def format(self, matrix: CoverageMatrix) -> str:
        """Format as JSON."""
        data = matrix.to_json_dict()
        return json.dumps(data, indent=2, default=str)


class MarkdownFormatter(BaseFormatter):
    """Format coverage matrix as Markdown."""
    
    def format(self, matrix: CoverageMatrix) -> str:
        """Format as Markdown."""
        lines = []
        
        # Header
        lines.append("# Test Coverage Report")
        lines.append(f"\nGenerated: {matrix.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if matrix.profile_id:
            lines.append(f"Profile: `{matrix.profile_id}`")
        lines.append("")
        
        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(f"- **Total Tests**: {matrix.total_tests}")
        lines.append(f"- **Test Suites**: {len(matrix.test_suites)}")
        lines.append(f"- **Requirements Covered**: {len(matrix.requirements)}")
        lines.append(f"- **Coverage Gaps**: {len(matrix.gaps)} ({len([g for g in matrix.gaps if g.severity == 'high'])} high severity)")
        lines.append("")
        
        # Test Suite Summary
        lines.append("## Test Suite Summary")
        lines.append("")
        lines.append("| Suite | Total Tests | Passed | Failed | Skipped | Pass Rate |")
        lines.append("|-------|-------------|--------|--------|---------|-----------|")
        
        for suite, coverage in matrix.test_suites.items():
            pass_rate = f"{coverage.pass_rate:.1f}%" if coverage.total_tests > 0 else "N/A"
            lines.append(
                f"| {suite.value} | {coverage.total_tests} | "
                f"{coverage.passed} | {coverage.failed} | "
                f"{coverage.skipped} | {pass_rate} |"
            )
        lines.append("")
        
        # Requirements Coverage
        lines.append("## Requirements Coverage")
        lines.append("")
        lines.append("| Requirement | Tests | Coverage | Pass Rate | Test Suites |")
        lines.append("|-------------|-------|----------|-----------|-------------|")
        
        for req_id in sorted(matrix.requirements.keys()):
            req = matrix.requirements[req_id]
            coverage_pct = f"{req.coverage_percent:.1f}%"
            pass_rate = f"{req.pass_rate:.1f}%" if req.total_tests > 0 else "N/A"
            suites = ", ".join(suite.value for suite in req.test_suites.keys())
            
            # Add visual indicator
            if req.coverage_percent >= 80:
                status = "✅"
            elif req.coverage_percent >= 50:
                status = "⚠️"
            else:
                status = "❌"
            
            lines.append(
                f"| {req_id} | {req.total_tests} | "
                f"{coverage_pct} {status} | {pass_rate} | {suites} |"
            )
        lines.append("")
        
        # SDK Compatibility Matrix (if available)
        if matrix.sdk_matrix and matrix.sdk_matrix.combinations:
            lines.append("## SDK Compatibility Matrix")
            lines.append("")
            lines.append("Cross-SDK test coverage (encryption → decryption):")
            lines.append("")
            
            # Get all SDKs
            all_sdks = sorted(set(
                list(matrix.sdk_matrix.combinations.keys()) +
                [sdk for combos in matrix.sdk_matrix.combinations.values() for sdk in combos.keys()]
            ))
            
            # Create matrix table
            lines.append("| From \\ To | " + " | ".join(all_sdks) + " |")
            lines.append("|" + "-" * 11 + "|" + "|".join(["-" * (len(sdk) + 2) for sdk in all_sdks]) + "|")
            
            for from_sdk in all_sdks:
                row = [from_sdk]
                for to_sdk in all_sdks:
                    if from_sdk == to_sdk:
                        row.append("—")
                    else:
                        count = matrix.sdk_matrix.get_coverage(from_sdk, to_sdk) or 0
                        if count > 0:
                            results = matrix.sdk_matrix.results.get(from_sdk, {}).get(to_sdk, {})
                            passed = results.get("passed", 0)
                            failed = results.get("failed", 0)
                            if failed > 0:
                                row.append(f"⚠️ {passed}/{count}")
                            else:
                                row.append(f"✅ {count}")
                        else:
                            row.append("❌ 0")
                
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
        
        # Capability Coverage
        lines.append("## Capability Coverage")
        lines.append("")
        
        for cap_key in sorted(matrix.capabilities.keys()):
            lines.append(f"### {cap_key.title()}")
            lines.append("")
            lines.append("| Value | Tests | Passed | Failed | Suites |")
            lines.append("|-------|-------|--------|--------|--------|")
            
            for cap_value in sorted(matrix.capabilities[cap_key].keys()):
                cap = matrix.capabilities[cap_key][cap_value]
                suites = ", ".join(suite.value for suite in cap.test_suites.keys())
                lines.append(
                    f"| {cap_value} | {cap.total_tests} | "
                    f"{cap.passed} | {cap.failed} | {suites} |"
                )
            lines.append("")
        
        # Coverage Gaps
        if matrix.gaps:
            lines.append("## Coverage Gaps")
            lines.append("")
            
            # Group gaps by severity
            high_gaps = [g for g in matrix.gaps if g.severity == "high"]
            medium_gaps = [g for g in matrix.gaps if g.severity == "medium"]
            low_gaps = [g for g in matrix.gaps if g.severity == "low"]
            
            if high_gaps:
                lines.append("### 🔴 High Severity")
                lines.append("")
                for gap in high_gaps:
                    lines.append(f"- **{gap.gap_type}**: {gap.description}")
                lines.append("")
            
            if medium_gaps:
                lines.append("### 🟡 Medium Severity")
                lines.append("")
                for gap in medium_gaps:
                    lines.append(f"- **{gap.gap_type}**: {gap.description}")
                lines.append("")
            
            if low_gaps:
                lines.append("### 🟢 Low Severity")
                lines.append("")
                for gap in low_gaps:
                    lines.append(f"- **{gap.gap_type}**: {gap.description}")
                lines.append("")
        
        # Footer
        lines.append("---")
        lines.append(f"*Report generated by OpenTDF Test Framework*")
        
        return "\n".join(lines)


class HTMLFormatter(BaseFormatter):
    """Format coverage matrix as HTML."""
    
    def format(self, matrix: CoverageMatrix) -> str:
        """Format as HTML."""
        html = []
        
        # HTML header with inline CSS
        html.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Coverage Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .metric {
            display: inline-block;
            margin: 10px 20px 10px 0;
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
        }
        .metric-label {
            color: #7f8c8d;
            font-size: 0.9em;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #34495e;
            color: white;
            font-weight: 500;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #ecf0f1;
            border-radius: 10px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #3498db, #2ecc71);
            transition: width 0.3s;
        }
        .status-passed { color: #27ae60; font-weight: bold; }
        .status-failed { color: #e74c3c; font-weight: bold; }
        .status-skipped { color: #95a5a6; }
        .gap-high { color: #e74c3c; font-weight: bold; }
        .gap-medium { color: #f39c12; }
        .gap-low { color: #95a5a6; }
        .matrix-cell {
            text-align: center;
            font-weight: bold;
        }
        .matrix-pass { background: #d4edda; color: #155724; }
        .matrix-fail { background: #f8d7da; color: #721c24; }
        .matrix-none { background: #f8f9fa; color: #6c757d; }
        .matrix-self { background: #e7e7e7; color: #999; }
    </style>
</head>
<body>
""")
        
        # Header
        html.append(f"""
    <h1>Test Coverage Report</h1>
    <p>Generated: {matrix.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
""")
        if matrix.profile_id:
            html.append(f"    <p>Profile: <code>{matrix.profile_id}</code></p>")
        
        # Executive Summary
        html.append("""
    <div class="card">
        <h2>Executive Summary</h2>
        <div class="metrics">
""")
        
        html.append(f"""
            <div class="metric">
                <div class="metric-value">{matrix.total_tests}</div>
                <div class="metric-label">Total Tests</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(matrix.test_suites)}</div>
                <div class="metric-label">Test Suites</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(matrix.requirements)}</div>
                <div class="metric-label">Requirements</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(matrix.gaps)}</div>
                <div class="metric-label">Coverage Gaps</div>
            </div>
""")
        
        html.append("""
        </div>
    </div>
""")
        
        # Test Suite Summary
        html.append("""
    <div class="card">
        <h2>Test Suite Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Suite</th>
                    <th>Total</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Skipped</th>
                    <th>Pass Rate</th>
                </tr>
            </thead>
            <tbody>
""")
        
        for suite, coverage in matrix.test_suites.items():
            pass_rate = coverage.pass_rate
            html.append(f"""
                <tr>
                    <td><strong>{suite.value.upper()}</strong></td>
                    <td>{coverage.total_tests}</td>
                    <td class="status-passed">{coverage.passed}</td>
                    <td class="status-failed">{coverage.failed}</td>
                    <td class="status-skipped">{coverage.skipped}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {pass_rate}%"></div>
                        </div>
                        {pass_rate:.1f}%
                    </td>
                </tr>
""")
        
        html.append("""
            </tbody>
        </table>
    </div>
""")
        
        # Requirements Coverage
        html.append("""
    <div class="card">
        <h2>Requirements Coverage</h2>
        <table>
            <thead>
                <tr>
                    <th>Requirement</th>
                    <th>Tests</th>
                    <th>Coverage</th>
                    <th>Pass Rate</th>
                    <th>Suites</th>
                </tr>
            </thead>
            <tbody>
""")
        
        for req_id in sorted(matrix.requirements.keys()):
            req = matrix.requirements[req_id]
            suites = ", ".join(suite.value for suite in req.test_suites.keys())
            html.append(f"""
                <tr>
                    <td><strong>{req_id}</strong></td>
                    <td>{req.total_tests}</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {req.coverage_percent}%"></div>
                        </div>
                        {req.coverage_percent:.1f}%
                    </td>
                    <td>{req.pass_rate:.1f}%</td>
                    <td>{suites}</td>
                </tr>
""")
        
        html.append("""
            </tbody>
        </table>
    </div>
""")
        
        # SDK Matrix (if available)
        if matrix.sdk_matrix and matrix.sdk_matrix.combinations:
            all_sdks = sorted(set(
                list(matrix.sdk_matrix.combinations.keys()) +
                [sdk for combos in matrix.sdk_matrix.combinations.values() for sdk in combos.keys()]
            ))
            
            html.append("""
    <div class="card">
        <h2>SDK Compatibility Matrix</h2>
        <p>Cross-SDK test coverage (rows: encryption, columns: decryption)</p>
        <table>
            <thead>
                <tr>
                    <th>From \\ To</th>
""")
            for sdk in all_sdks:
                html.append(f"                    <th>{sdk}</th>\n")
            html.append("""                </tr>
            </thead>
            <tbody>
""")
            
            for from_sdk in all_sdks:
                html.append(f"                <tr>\n                    <th>{from_sdk}</th>\n")
                for to_sdk in all_sdks:
                    if from_sdk == to_sdk:
                        html.append('                    <td class="matrix-cell matrix-self">—</td>\n')
                    else:
                        count = matrix.sdk_matrix.get_coverage(from_sdk, to_sdk) or 0
                        if count > 0:
                            results = matrix.sdk_matrix.results.get(from_sdk, {}).get(to_sdk, {})
                            passed = results.get("passed", 0)
                            failed = results.get("failed", 0)
                            if failed > 0:
                                css_class = "matrix-fail"
                                text = f"{passed}/{count}"
                            else:
                                css_class = "matrix-pass"
                                text = str(count)
                        else:
                            css_class = "matrix-none"
                            text = "0"
                        html.append(f'                    <td class="matrix-cell {css_class}">{text}</td>\n')
                html.append("                </tr>\n")
            
            html.append("""
            </tbody>
        </table>
    </div>
""")
        
        # Coverage Gaps
        if matrix.gaps:
            html.append("""
    <div class="card">
        <h2>Coverage Gaps</h2>
        <ul>
""")
            for gap in sorted(matrix.gaps, key=lambda g: (g.severity != "high", g.severity != "medium", g.description)):
                severity_class = f"gap-{gap.severity}"
                html.append(f'            <li class="{severity_class}">{gap.description}</li>\n')
            
            html.append("""
        </ul>
    </div>
""")
        
        # Footer
        html.append("""
</body>
</html>
""")
        
        return "".join(html)