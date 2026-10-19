"""Unit tests for the decision-first benchmark summary.

Presentation only: these check that every outcome reads distinctly and
legibly, that provenance and links come out right with and without CI, and
that rendering never changes a decision.
"""

from __future__ import annotations

import copy
import math
import random

import pytest

from perf import presentation, stats
from perf.report import BenchmarkRecorder
from perf.runner import BenchConfig, CellResult

CFG = BenchConfig(n_resamples=300)


def cell(
    cell_id: str,
    costs: dict[str, float],
    *,
    control: bool = False,
    seed: int = 3,
    noise: float = 0.02,
) -> CellResult:
    rng = random.Random(seed)
    ids = tuple(costs)
    return CellResult(
        cell_id=cell_id,
        arm_ids=ids,
        arm_labels={a: f"go@{a.split('#')[0]}" for a in ids},
        reference=ids[0],
        samples={
            a: {
                m: [c * math.exp(rng.gauss(0, noise)) for _ in range(30)]
                for m in ("wall", "cpu", "rss")
            }
            for a, c in costs.items()
        },
        n_warmup=2,
        elapsed_s=10.0,
        stopped_because="precision",
        control=control,
        sdk="go",
    )


def control(n: int = 2, *, noise: float = 0.02) -> CellResult:
    return cell(
        "go-encrypt-1MiB-control",
        {f"main#{i + 1}": 1.0 for i in range(n)},
        control=True,
        noise=noise,
    )


INSTALLATION = {
    "sdk": "go",
    "status": "success",
    "status_message": "",
    "arms": [
        {
            "requested_alias": "latest",
            "repository": "https://github.com/opentdf/platform.git",
            "commit_sha": "a" * 40,
            "installed_tag": "v0.29.0",
            "installation_method": "release",
        },
        {
            "requested_alias": "main",
            "repository": "https://github.com/opentdf/platform.git",
            "commit_sha": "b" * 40,
            "installed_tag": "main",
            "installation_method": "source",
        },
    ],
}


def render(
    *cells: CellResult, skipped=None, metadata=None
) -> tuple[str, stats.GateResult]:
    recorder = BenchmarkRecorder(
        results=list(cells), skipped=skipped or {}, metadata=metadata or {}
    )
    gate = recorder.gate(CFG)
    return presentation.render(recorder, CFG, gate), gate


def title(text: str) -> str:
    return text.splitlines()[0]


class TestOutcomesReadDistinctly:
    def test_pass(self):
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0})
        )
        assert title(text).endswith("PASS")

    def test_regression(self):
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.4})
        )
        assert title(text).endswith("REGRESSION")
        assert "**REGRESSION**" in text and "Effect at a glance" in text

    def test_nothing_measured(self):
        text, _ = render(skipped={"go-encrypt-1KiB": "no final go release"})
        assert title(text).endswith("NOTHING MEASURED")
        assert "not a passing result" in text

    def test_neutral(self):
        text, _ = render(
            skipped={"go-encrypt-1KiB": "neutral preparation: same commit"},
            metadata={"preparation": "neutral", "installation": INSTALLATION},
        )
        assert title(text).endswith("NEUTRAL")
        assert "Cells not run (same commit)" in text

    def test_untrustworthy_control(self):
        biased = cell(
            "go-encrypt-1MiB-control", {"main#1": 1.0, "main#2": 1.4}, control=True
        )
        text, _ = render(biased, cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.4}))
        assert title(text).endswith("UNTRUSTWORTHY")

    def test_partial_coverage_lists_what_was_skipped(self):
        text, _ = render(
            control(),
            cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0}),
            skipped={"go-decrypt-32MiB": "budget ran out"},
        )
        assert title(text).endswith("PARTIAL")
        assert "coverage is incomplete" in text
        assert "`go-decrypt-32MiB`: budget ran out" in text

    def test_inconclusive(self):
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.1}, noise=0.4)
        )
        assert title(text).endswith("INCONCLUSIVE")


class TestCandidates:
    def test_a_winner_reads_as_the_conclusion_says(self):
        recorder = BenchmarkRecorder(
            results=[
                control(3),
                cell("go-encrypt-1KiB", {"main": 1.0, "a": 1.0, "b": 0.6}),
            ]
        )
        gate = recorder.gate(CFG)
        text = presentation.render(recorder, CFG, gate)
        wall = next(c for c in recorder.conclusions(CFG, gate) if c.metric == "wall")
        assert wall.winner == "b"
        assert "`go@b` wins" in text

    def test_a_tie_and_an_unresolved_pair_say_so(self):
        text, _ = render(
            control(3, noise=0.005),
            cell("go-encrypt-1KiB", {"main": 1.0, "a": 1.0, "b": 1.0}, noise=0.005),
        )
        assert "no winner" in text and "tied" in text


class TestProvenance:
    def test_requested_refs_and_commits_are_linked(self):
        text, _ = render(
            control(),
            cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0}),
            metadata={"installation": INSTALLATION},
        )
        repo = "https://github.com/opentdf/platform"
        assert f"[`{'b' * 8}`]({repo}/commit/{'b' * 40})" in text
        assert f"{repo}/compare/{'a' * 40}...{'b' * 40}" in text
        assert "| latest |" in text and "| main |" in text

    def test_missing_provenance_is_said_not_invented(self):
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0})
        )
        assert "provenance unavailable" in text


class TestLegibility:
    def test_a_huge_effect_stays_on_its_line(self):
        c = stats.PairedComparison(
            n_rounds=30,
            baseline_median=1.0,
            candidate_median=40.0,
            ratio=40.0,
            ci_low=35.0,
            ci_high=45.0,
            p_value=0.001,
            p_value_faster=1.0,
        )
        strip = presentation.effect_strip(c, 1.15, width=57, span=math.log(45) * 1.05)
        assert len(strip) == 57
        # Past the slower threshold marker, and not clipped onto the edge.
        marker = max(strip.find("●"), strip.find("◆"))
        assert strip.rfind("┆") < marker < 56

    def test_an_unavailable_interval_does_not_break_the_strip(self):
        c = stats.PairedComparison(
            n_rounds=3,
            baseline_median=1.0,
            candidate_median=1.0,
            ratio=math.nan,
            ci_low=math.nan,
            ci_high=math.nan,
            p_value=math.nan,
            p_value_faster=math.nan,
        )
        assert len(presentation.effect_strip(c, 1.15)) == 57

    def test_markdown_sensitive_text_cannot_break_a_table(self):
        text, _ = render(
            skipped={"go-encrypt-1KiB": "reason with | pipe and `tick` and [link](x)"}
        )
        line = next(line for line in text.splitlines() if "go-encrypt-1KiB" in line)
        assert "\\|" in line and "`tick`" not in line and "\\[link\\]" in line

    def test_long_arm_names_render(self):
        name = "fix--otdfctl-streaming-encrypt-writer-with-a-very-long-branch-name"
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, name: 1.4})
        )
        assert f"`go@{name}`" in text

    def test_trace_is_two_rounds_per_glyph(self):
        assert len(presentation.braille_trace([1.0, 1.1, 0.9, 1.2], 1.15)) == 2


class TestPublishing:
    def test_works_without_github_and_leaves_no_placeholder(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        for var in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
            monkeypatch.delenv(var, raising=False)
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0})
        )
        local = presentation.publish(text)
        assert presentation.ARTIFACT_URL not in local
        assert "local output" in local

    def test_the_artifact_url_is_filled_in(self):
        text, _ = render(
            control(), cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0})
        )
        url = "https://github.com/opentdf/tests/actions/runs/1/artifacts/2"
        published = presentation.publish(text, url)
        assert presentation.ARTIFACT_URL not in published
        assert published.count(url) == 2

    def test_a_workflow_link_survives_without_an_artifact_url(self):
        text, _ = render(
            control(),
            cell("go-encrypt-1KiB", {"v0.29.0": 1.0, "main": 1.0}),
            metadata={"github_run_url": "https://example.test/run/1"},
        )
        assert "[Workflow run](https://example.test/run/1)" in presentation.publish(
            text
        )


def test_rendering_does_not_change_any_decision():
    recorder = BenchmarkRecorder(
        results=[control(3), cell("go-encrypt-1KiB", {"main": 1.0, "a": 1.3, "b": 0.6})]
    )
    gate = recorder.gate(CFG)
    before = copy.deepcopy((gate.comparisons, gate.regressions, gate.trustworthy))
    winners = [c.winner for c in recorder.conclusions(CFG, gate)]
    presentation.render(recorder, CFG, gate)
    assert (gate.comparisons, gate.regressions, gate.trustworthy) == before
    assert [c.winner for c in recorder.conclusions(CFG, gate)] == winners
