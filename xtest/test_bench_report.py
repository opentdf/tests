"""Unit tests for the benchmark report: its JSON shape and its rendering.

Offline: no SDKs, no services. Builds `PairedComparison` and `CellResult`
values directly.
"""

import json
import math
import random
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import conftest
from fixtures import bench
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


def _measured(cell_id: str, *, seed: int = 3) -> CellResult:
    """A finished two-arm cell, as `run_cell` records it."""
    rng = random.Random(seed)
    samples = {
        arm: {
            m: [rng.lognormvariate(0, 0.02) for _ in range(20)]
            for m in ("wall", "cpu", "rss")
        }
        for arm in ("baseline", "candidate")
    }
    return CellResult(
        cell_id=cell_id,
        baseline_label="go@v0.29.0",
        candidate_label="go@main",
        samples=samples,
        n_warmup=2,
        elapsed_s=12.0,
        stopped_because="precision",
        sdk="go",
    )


@pytest.fixture
def cfg(monkeypatch: pytest.MonkeyPatch) -> BenchConfig:
    """The config the hook sees, without the platform probe in its metadata."""
    cfg = BenchConfig(n_resamples=300)
    monkeypatch.setattr(bench, "config_from_options", lambda config: cfg)
    monkeypatch.setattr(bench, "runner_metadata", lambda config: {"seed": cfg.seed})
    return cfg


def _finish(out_dir: Path, recorder: BenchmarkRecorder) -> None:
    """Run the session-finish hook as pytest does after a ``--bench`` run."""
    options: dict[str, object] = {"--bench": True, "--bench-out": out_dir}
    config = SimpleNamespace(
        getoption=lambda name, default=None: options.get(name, default),
        stash=pytest.Stash(),
        pluginmanager=SimpleNamespace(get_plugin=lambda name: None),
    )
    config.stash[report.RECORDER_KEY] = recorder
    session = SimpleNamespace(config=config, exitstatus=pytest.ExitCode.OK)
    conftest.pytest_sessionfinish(cast(pytest.Session, session), 0)


class TestSessionFinish:
    @pytest.mark.parametrize("broken", ["analyze", "to_dict"])
    def test_a_failed_analysis_still_writes_the_raw_samples(
        self,
        broken: str,
        cfg: BenchConfig,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # The run whose analysis broke is the one someone most needs the
        # samples from, and the error must still end the session loudly.
        error = KeyError("go-encrypt-1MiB/wall")

        def fail(*args: object) -> None:
            raise error

        monkeypatch.setattr(report, broken, fail)
        recorder = BenchmarkRecorder(
            results=[_measured("go-encrypt-1MiB")],
            skipped={"go-decrypt-1MiB": "no final release to compare against"},
        )
        out = tmp_path / "out"
        with pytest.raises(KeyError) as raised:
            _finish(out, recorder)

        raw = out / "benchmarks.raw.json"
        assert raw.is_file()
        assert list(out.iterdir()) == [raw], "no normal artifact without a gate"
        assert raised.value is error
        assert raised.value.__notes__ == [f"raw samples, without statistics: {raw}"]
        doc = json.loads(raw.read_text())
        assert "schema" not in doc, "a reader of the normal artifact must trip"
        assert doc["analysis_error"] == {"type": "KeyError", "message": str(error)}
        assert doc["metadata"] == {"seed": 0}
        assert doc["config"]["n_resamples"] == 300
        assert doc["skipped"] == recorder.skipped
        # Enough to re-analyse offline: every cell, samples included, rebuilds.
        assert [CellResult(**c) for c in doc["cells"]] == recorder.results

    def test_a_clean_analysis_writes_what_it_always_did(
        self, cfg: BenchConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        recorder = BenchmarkRecorder(results=[_measured("go-encrypt-1MiB")])
        out = tmp_path / "out"
        _finish(out, recorder)

        gate = recorder.gate(cfg)
        assert list(out.iterdir()) == [out / "benchmarks.json"]
        assert (out / "benchmarks.json").read_text() == json.dumps(
            report.to_dict(recorder, cfg, gate), indent=2
        )
        assert summary.read_text() == report.markdown(recorder, cfg, gate)
