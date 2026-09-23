"""Tests for the final workflow-level benchmark summary."""

from __future__ import annotations

import json
from pathlib import Path

from perf import aggregate


def document(
    sdk: str,
    verdict: str,
    *,
    elapsed: float = 30,
    skipped: int = 0,
) -> dict[str, object]:
    ratio = {
        "REGRESSION": 1.3,
        "IMPROVED": 0.7,
        "INCONCLUSIVE": 1.1,
        "PASS": 1.0,
    }[verdict]
    return {
        "schema": 2,
        "metadata": {
            "sdk": sdk,
            "platform_version": "v0.4.50",
            "arm_sources": [{"tag": "v1"}, {"tag": "main"}],
        },
        "config": {"gated_metrics": ["wall", "rss"]},
        "noise_floor": {"assessed": True, "width_ratio": 1.04},
        "trustworthy": True,
        "skipped": {f"skipped-{i}": "unsupported" for i in range(skipped)},
        "cells": [
            {
                "id": f"{sdk}-encrypt-1MiB",
                "control": False,
                "reference": "v1",
                "arms": ["v1", "main"],
                "elapsed_s": elapsed,
                "contrasts": {
                    "main_vs_v1": {
                        "wall": {
                            "verdict": verdict,
                            "ratio": ratio,
                            "ci_low": ratio - 0.02,
                            "ci_high": ratio + 0.02,
                        }
                    }
                },
            }
        ],
    }


def test_load_runs_ignores_unrelated_json_and_uses_stable_sdk_order(tmp_path: Path):
    (tmp_path / "java.json").write_text(json.dumps(document("java", "PASS")))
    (tmp_path / "go.json").write_text(json.dumps(document("go", "PASS")))
    (tmp_path / "unrelated.json").write_text('{"hello": "world"}')

    assert [run.sdk for run in aggregate.load_runs(tmp_path)] == ["go", "java"]


def test_rollup_puts_the_cross_sdk_bottom_line_first_and_combines_run_facts():
    runs = [
        aggregate.Run("go", document("go", "REGRESSION", elapsed=20)),
        aggregate.Run("java", document("java", "PASS", elapsed=30, skipped=1)),
        aggregate.Run("js", document("js", "INCONCLUSIVE", elapsed=40)),
    ]
    md = aggregate.markdown(
        runs,
        artifact_urls={
            "go": "https://example.test/go",
            "java": "https://example.test/java",
        },
        run_url="https://example.test/run",
        expected_sdks=["go", "java", "js"],
    )

    assert md.startswith("# SDK performance benchmark roll-up — REGRESSION\n")
    assert "go: REGRESSION, java: PASS, js: INCONCLUSIVE" in md
    assert md.index("### TL;DR") < md.index("| SDK | outcome")
    assert md.index("| SDK | outcome") < md.index("### Confirmed regressions")
    assert "| go | `go-encrypt-1MiB` | wall | +30.0% [+28.0%, +32.0%] |" in md
    assert "| 3/3 | 3 | 1 | 90s | v0.4.50 |" in md
    assert "[artifact](https://example.test/go)" in md
    assert "[Workflow run](https://example.test/run)" in md
    assert "Absolute timings are not compared across SDKs" in md


def test_rollup_explains_when_no_matrix_artifact_survived():
    md = aggregate.markdown([], run_url="https://example.test/run")

    assert "NO RESULTS" in md
    assert "No benchmark JSON artifacts were available" in md


def test_rollup_makes_a_missing_matrix_result_visible():
    md = aggregate.markdown(
        [aggregate.Run("go", document("go", "PASS"))],
        expected_sdks=["go", "java"],
    )

    assert "roll-up — INCOMPLETE" in md
    assert "Missing result(s): java" in md
    assert "| **java** | **MISSING** |" in md


def test_a_control_without_a_result_cell_is_nothing_measured():
    doc = document("go", "PASS")
    doc["cells"] = [{"id": "go-control", "control": True, "contrasts": {}}]

    assert aggregate.Run("go", doc).status == "NOTHING MEASURED"


def test_same_commit_is_neutral_and_names_both_requested_refs():
    doc = document("java", "PASS")
    doc["nothing_measured"] = True
    doc["cells"] = []
    metadata = doc["metadata"]
    assert isinstance(metadata, dict)
    metadata.update(
        {
            "comparison_status": "same_commit",
            "requested_refs": ["main", "latest"],
            "arm_sources": [
                {
                    "tag": "main",
                    "sha": "a" * 40,
                    "repo_url": "https://github.com/opentdf/java-sdk",
                }
            ],
        }
    )
    run = aggregate.Run("java", doc)
    md = aggregate.markdown([run], expected_sdks=["java"])

    assert run.status == "SAME COMMIT"
    assert "roll-up — SAME COMMIT" in md
    assert "`main`" in md and "`latest`" in md and "same commit" in md


def test_rollup_uses_measured_reference_order_and_links_sources():
    doc = document("go", "PASS")
    metadata = doc["metadata"]
    assert isinstance(metadata, dict)
    metadata["arm_sources"] = [
        {
            "tag": "main",
            "sha": "b" * 40,
            "repo_url": "https://github.com/opentdf/platform",
        },
        {
            "tag": "v1",
            "release": "otdfctl/v1.0.0",
            "sha": "a" * 40,
            "repo_url": "https://github.com/opentdf/platform",
        },
    ]
    md = aggregate.markdown([aggregate.Run("go", doc)])

    assert "releases/tag/otdfctl%2Fv1.0.0" in md
    assert md.index("`v1`") < md.index("`main`")
