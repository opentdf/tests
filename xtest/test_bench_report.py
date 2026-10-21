"""Unit tests for the benchmark report: its JSON shape and its rendering.

Offline: no SDKs, no services. Builds `PairedComparison` and `CellResult`
values directly.
"""

import json
import math
import random

import pytest

from perf import report, stats
from perf.report import BenchmarkRecorder, _p_cell
from perf.runner import BenchConfig, CellResult
from perf.stats import Verdict


def _comparison(
    ratio: float,
    *,
    p_value: float,
    p_value_faster: float,
    p_adjusted: float | None = None,
    p_adjusted_faster: float | None = None,
    verdict: Verdict = Verdict.INCONCLUSIVE,
) -> stats.PairedComparison:
    return stats.PairedComparison(
        n_rounds=20,
        baseline_median=1.0,
        candidate_median=ratio,
        ratio=ratio,
        ci_low=ratio * 0.9,
        ci_high=ratio * 1.1,
        p_value=p_value,
        p_value_faster=p_value_faster,
        p_adjusted=p_adjusted,
        p_adjusted_faster=p_adjusted_faster,
        verdict=verdict,
    )


class TestPCell:
    def test_an_improvement_shows_the_faster_tail(self):
        # The slower tail of a 2x speedup is ~1; printing it beside IMPROVED
        # contradicts the verdict on the same row.
        c = _comparison(
            0.5,
            p_value=1.0,
            p_value_faster=0.0004,
            p_adjusted=1.0,
            p_adjusted_faster=0.0011,
            verdict=Verdict.IMPROVED,
        )
        assert _p_cell(c) == "0.001"

    def test_a_slowdown_shows_the_slower_tail(self):
        c = _comparison(
            1.5,
            p_value=0.0004,
            p_value_faster=1.0,
            p_adjusted=0.002,
            p_adjusted_faster=1.0,
            verdict=Verdict.REGRESSION,
        )
        assert _p_cell(c) == "0.002"

    def test_no_change_shows_the_slower_tail(self):
        c = _comparison(1.0, p_value=0.5, p_value_faster=0.5, p_adjusted=0.6)
        assert _p_cell(c) == "0.600"

    @pytest.mark.parametrize(
        ("ratio", "expected"),
        [(0.8, "0.030"), (1.2, "0.020")],
        ids=["faster", "slower"],
    )
    def test_unadjusted_tail_is_used_when_not_corrected(self, ratio, expected):
        # Controls are reported unadjusted: they stay out of the BH families.
        c = _comparison(ratio, p_value=0.02, p_value_faster=0.03)
        assert _p_cell(c) == expected

    def test_tiny_p_is_floored(self):
        c = _comparison(0.5, p_value=1.0, p_value_faster=1e-6, p_adjusted_faster=1e-5)
        assert _p_cell(c) == "<0.001"

    def test_an_empty_comparison_shows_a_dash(self):
        c = _comparison(math.nan, p_value=math.nan, p_value_faster=math.nan)
        assert _p_cell(c) == "-"


def _cell(
    cell_id: str, costs: dict[str, float], *, control: bool = False, seed: int = 3
) -> CellResult:
    """A finished cell with lognormal samples, first arm = reference."""
    rng = random.Random(seed)
    n = 30
    samples = {
        arm: {
            "wall": [c * math.exp(rng.gauss(0, 0.02)) for _ in range(n)],
            "cpu": [0.8 * c * math.exp(rng.gauss(0, 0.02)) for _ in range(n)],
            "rss": [1e8 * c * math.exp(rng.gauss(0, 0.02)) for _ in range(n)],
        }
        for arm, c in costs.items()
    }
    ids = tuple(costs)
    return CellResult(
        cell_id=cell_id,
        arm_ids=ids,
        arm_labels={a: f"go@{a.split('#')[0]}" for a in ids},
        reference=ids[0],
        samples=samples,
        n_warmup=2,
        elapsed_s=12.0,
        stopped_because="precision",
        control=control,
        sdk="go",
    )


def _run(*cells: CellResult, metadata: dict[str, object] | None = None):
    cfg = BenchConfig(n_resamples=300)
    recorder = BenchmarkRecorder(results=list(cells), metadata=metadata or {})
    return recorder, cfg, recorder.gate(cfg)


class TestJsonSchema:
    def test_a_three_arm_cell_identifies_every_arm_and_keeps_every_sample(self):
        aa = _cell("go-aa", {"main#1": 1.0, "main#2": 1.0, "main#3": 1.0}, control=True)
        cell = _cell("go-encrypt", {"main": 1.0, "a": 1.0, "b": 1.3})
        doc = report.to_dict(*_run(aa, cell))

        assert doc["schema"] == report.SCHEMA_VERSION == 2
        out = doc["cells"][1]  # pyright: ignore[reportIndexIssue]
        assert out["reference"] == "main"
        assert [a["id"] for a in out["arms"]] == ["main", "a", "b"]
        assert out["samples"] == cell.samples
        assert [(c["a"], c["b"]) for c in out["contrasts"]] == [
            ("main", "a"),
            ("main", "b"),
        ]
        assert out["contrasts"][1]["metrics"]["wall"]["verdict"] == "REGRESSION"
        # "The candidate" would mean only the first of two here.
        assert "candidate" not in out and "baseline" not in out
        json.dumps(doc)  # serializable as-is

    def test_a_two_arm_cell_keeps_the_convenience_labels(self):
        aa = _cell("go-aa", {"main#1": 1.0, "main#2": 1.0}, control=True)
        cell = _cell("go-encrypt", {"v0.29.0": 1.0, "main": 1.0})
        out = report.to_dict(*_run(aa, cell))["cells"][1]  # pyright: ignore[reportIndexIssue]
        assert out["baseline"] == "go@v0.29.0"
        assert out["candidate"] == "go@main"


class TestMarkdown:
    def test_one_row_per_candidate_and_metric(self):
        aa = _cell("go-aa", {"main#1": 1.0, "main#2": 1.0, "main#3": 1.0}, control=True)
        cell = _cell("go-encrypt", {"main": 1.0, "a": 1.0, "b": 1.3})
        text = report.markdown(*_run(aa, cell))
        rows = [line for line in text.splitlines() if line.startswith("| go-encrypt ")]
        assert len(rows) == 2 * 3
        assert any("`go@b`" in r and "**REGRESSION**" in r for r in rows)
        assert "Reference: `go@main`." in text

    def test_a_neutral_preparation_says_so_instead_of_nothing_measured(self):
        recorder = BenchmarkRecorder(
            skipped={"go-encrypt-1KiB": "neutral preparation: same commit"},
            metadata={
                "preparation": "neutral",
                "installation": {"status_message": "All 2 resolved to abc12345"},
            },
        )
        cfg = BenchConfig(n_resamples=300)
        text = report.markdown(recorder, cfg, recorder.gate(cfg))
        assert "NEUTRAL" in text and "abc12345" in text
        assert "NOTHING MEASURED" not in text
