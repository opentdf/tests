"""Unit tests for the benchmark report: its JSON shape and its rendering.

Offline: no SDKs, no services. Builds `PairedComparison` and `CellResult`
values directly.
"""

import json
import math
import random
import statistics

import pytest

from perf import report, stats
from perf.measure import format_metric
from perf.report import BenchmarkRecorder, _p_cell
from perf.runner import BenchConfig, CellResult, contrast_key
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
        a_median=1.0,
        b_median=ratio,
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
    """A finished cell with lognormal samples, first arm = reference.

    Each metric is in its measured unit -- wall clock in nanoseconds, as a
    :class:`perf.measure.Sample` reports it -- so medians render as real
    numbers rather than ``0.0 ms``.
    """
    rng = random.Random(seed)
    n = 30
    samples = {
        arm: {
            "wall": [4.12e8 * c * math.exp(rng.gauss(0, 0.02)) for _ in range(n)],
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
        # Through JSON and back, as a consumer reads it.
        doc = json.loads(json.dumps(report.to_dict(*_run(aa, cell))))

        assert doc["schema"] == report.SCHEMA_VERSION == 2
        assert doc["nothing_measured"] is False
        assert doc["regressions"] == [
            contrast_key("go-encrypt", "main", "b", "wall"),
            contrast_key("go-encrypt", "main", "b", "rss"),
        ]
        out = doc["cells"][1]
        assert out["reference"] == "main"
        assert out["arms"] == [
            {"id": "main", "label": "go@main"},
            {"id": "a", "label": "go@a"},
            {"id": "b", "label": "go@b"},
        ]
        assert out["samples"] == cell.samples, "every raw sample survives"
        assert [(c["a"], c["b"]) for c in out["contrasts"]] == [
            ("main", "a"),
            ("main", "b"),
        ]
        slowed = out["contrasts"][1]["metrics"]["wall"]
        assert slowed["verdict"] == "REGRESSION"
        # `a` is the reference and `b` the slowed candidate, never the reverse.
        assert slowed["b_median"] > slowed["a_median"]
        # "The candidate" would mean only the first of two here.
        assert "candidate" not in out and "baseline" not in out

    def test_a_control_only_run_reports_nothing_measured(self):
        aa = _cell("go-aa", {"main#1": 1.0, "main#2": 1.0}, control=True)
        doc = report.to_dict(*_run(aa))
        assert doc["nothing_measured"] is True
        assert doc["regressions"] == []

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

    def test_a_two_arm_run_renders_the_documented_table(self):
        # The nightly shape: one control and one cell that regressed by 30%.
        aa = _cell(
            "go-encrypt-1MiB-control",
            {"v0.29.0#1": 1.0, "v0.29.0#2": 1.0},
            control=True,
        )
        cell = _cell("go-encrypt-1MiB", {"v0.29.0": 1.0, "main": 1.3})
        lines = report.markdown(*_run(aa, cell)).splitlines()

        # The headline names contrast keys, which are the JSON's keys too.
        assert (
            "**2 confirmed regression(s) past the 15% threshold: "
            "go-encrypt-1MiB/main_vs_v0.29.0/wall, "
            "go-encrypt-1MiB/main_vs_v0.29.0/rss**"
        ) in lines
        assert (
            "| cell | candidate | metric | reference median | candidate median "
            "| ratio (95% CI) | p (BH) | n | verdict |"
        ) in lines
        # A control's copies share a label, so its rows name the copy.
        control_rows = [r for r in lines if r.startswith("| go-encrypt-1MiB-control ")]
        assert len(control_rows) == 3
        assert control_rows[0].startswith(
            "| go-encrypt-1MiB-control | A/A v0.29.0#2 | wall clock (ungated) | "
        )

        def median_ms(arm: str) -> str:
            return format_metric("wall", statistics.median(cell.samples[arm]["wall"]))

        wall = next(r for r in lines if r.startswith("| go-encrypt-1MiB | "))
        assert wall.startswith(
            f"| go-encrypt-1MiB | `go@main` | wall clock "
            f"| {median_ms('v0.29.0')} | {median_ms('main')} | "
        )
        assert wall.endswith("| 30 | **REGRESSION** |")
        assert not any("| 0.0 ms |" in r for r in lines)
        assert "Reference: `go@v0.29.0`." in lines

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
