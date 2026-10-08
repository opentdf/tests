"""Unit tests for the benchmark report's rendering helpers.

Offline: no SDKs, no services. Builds `PairedComparison` values directly.
"""

import math

import pytest

from perf import stats
from perf.report import _p_cell
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
