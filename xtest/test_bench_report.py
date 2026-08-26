"""Tests for what a benchmark run publishes: the JSON artifact and the summary.

The report is where a K-arm run stops being a pile of ratios and starts being
an answer, so the things worth pinning down are the ones a reader would act on
without checking: which arm won a bake-off, whether a tie is reported as a tie,
and whether a run that could not resolve anything says so instead of returning
a quiet page of INCONCLUSIVE.

Measurement is simulated exactly as in ``test_bench_runner``; nothing here
touches a platform or a subprocess.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from perf import report, stats
from perf.runner import BenchConfig
from test_bench_runner import REF, config, run


def recorder(
    costs: Mapping[str, float],
    *,
    cfg: BenchConfig | None = None,
    noise: float = 0.05,
    control: bool = True,
) -> report.BenchmarkRecorder:
    """A recorder holding one measured cell and, by default, its A/A control."""
    cfg = cfg or config(max_rounds=40)
    rec = report.BenchmarkRecorder()
    if control:
        aa, _ = run(
            dict.fromkeys(costs, 1.0),
            cfg=cfg,
            noise=noise,
            seed=11,
            cell_id="aa",
            control=True,
            sdk="go",
        )
        rec.record(aa)
    measured, _ = run(costs, cfg=cfg, noise=noise, seed=12, cell_id="encrypt", sdk="go")
    rec.record(measured)
    return rec


def bake_offs(
    costs: Mapping[str, float], *, cfg: BenchConfig | None = None, noise: float = 0.05
) -> tuple[list[report.BakeOff], BenchConfig]:
    cfg = cfg or config(max_rounds=40)
    rec = recorder(costs, cfg=cfg, noise=noise)
    return report.bake_offs(rec, cfg, rec.gate(cfg)), cfg


class TestBakeOff:
    def test_a_two_arm_run_has_nothing_to_rank(self):
        # One candidate is not a bake-off, and the gate has already said
        # everything there is to say about it.
        offs, _ = bake_offs({REF: 1.0, "cand": 1.3})
        assert offs == []

    def test_the_control_is_never_ranked(self):
        offs, _ = bake_offs({REF: 1.0, "a": 1.0, "b": 1.3})
        assert offs and all(b.cell_id == "encrypt" for b in offs)

    def test_the_faster_candidate_wins(self):
        offs, _ = bake_offs({REF: 1.0, "slow": 1.4, "quick": 1.0}, noise=0.02)
        wall = next(b for b in offs if b.metric == "wall")
        assert wall.winner == "quick"
        assert wall.order == ["quick", "slow"]
        assert "`quick` wins" in wall.detail

    def test_a_tie_refuses_to_name_a_winner(self):
        # Picking whichever point estimate landed lower would be reporting
        # noise as a decision, and a merge would be made on it.
        offs, _ = bake_offs({REF: 1.0, "a": 1.0, "b": 1.0}, noise=0.01)
        wall = next(b for b in offs if b.metric == "wall")
        assert wall.verdict is stats.Verdict.TIED
        assert wall.winner is None
        assert "no measurable difference" in wall.detail

    def test_an_unresolvable_pair_says_so_rather_than_guessing(self):
        offs, _ = bake_offs(
            {REF: 1.0, "a": 1.0, "b": 1.15},
            cfg=config(max_rounds=20),
            noise=0.35,
        )
        wall = next(b for b in offs if b.metric == "wall")
        assert wall.winner is None
        assert "cannot separate" in wall.detail

    def test_the_ranking_covers_every_gated_metric(self):
        offs, cfg = bake_offs({REF: 1.0, "a": 1.0, "b": 1.4}, noise=0.02)
        assert {b.metric for b in offs} == set(cfg.gated_metrics)


class TestUnderpoweredWarning:
    def test_a_precise_run_says_nothing(self):
        cfg = config(max_rounds=60)
        rec = recorder({REF: 1.0, "a": 1.0, "b": 1.0}, cfg=cfg, noise=0.005)
        assert report.underpowered_warning(rec, cfg, rec.gate(cfg)) is None

    def test_a_run_that_could_not_resolve_anything_asks_for_more_budget(self):
        # Otherwise three arms on a two-arm budget comes back as a wall of
        # INCONCLUSIVE after burning the whole runner, with nothing in the
        # output saying that time was the missing ingredient.
        cfg = config(max_rounds=20)
        rec = recorder({REF: 1.0, "a": 1.0, "b": 1.0}, cfg=cfg, noise=0.4)
        warning = report.underpowered_warning(rec, cfg, rec.gate(cfg))
        assert warning is not None
        assert "3-arm round costs 3 invocations" in warning
        assert "INCONCLUSIVE" in warning

    def test_the_warning_reaches_the_summary(self):
        cfg = config(max_rounds=20)
        rec = recorder({REF: 1.0, "a": 1.0, "b": 1.0}, cfg=cfg, noise=0.4)
        md = report.markdown(rec, cfg, rec.gate(cfg))
        assert "[!WARNING]" in md and "Underpowered" in md


class TestJsonArtifact:
    def artifact(self, tmp_path: Path, costs: Mapping[str, float]) -> dict:
        cfg = config(max_rounds=40)
        rec = recorder(costs, cfg=cfg, noise=0.02)
        path = report.write_json(tmp_path / "bench.json", rec, cfg, rec.gate(cfg))
        return json.loads(path.read_text())

    def test_arms_and_the_reference_are_recorded(self, tmp_path: Path):
        # Which arm the ratios are taken against is not recoverable from the
        # numbers, and every contrast in the file is meaningless without it.
        doc = self.artifact(tmp_path, {REF: 1.0, "a": 1.0, "b": 1.3})
        cell = next(c for c in doc["cells"] if c["id"] == "encrypt")
        assert cell["arms"] == [REF, "a", "b"]
        assert cell["reference"] == REF

    def test_every_pair_appears_once(self, tmp_path: Path):
        doc = self.artifact(tmp_path, {REF: 1.0, "a": 1.0, "b": 1.3})
        cell = next(c for c in doc["cells"] if c["id"] == "encrypt")
        assert set(cell["contrasts"]) == {f"a_vs_{REF}", f"b_vs_{REF}", "b_vs_a"}

    def test_two_arm_readers_still_find_a_baseline_and_candidate(self, tmp_path: Path):
        doc = self.artifact(tmp_path, {REF: 1.0, "cand": 1.3})
        cell = next(c for c in doc["cells"] if c["id"] == "encrypt")
        assert doc["schema"] == 2
        assert cell["baseline"] == f"sdk@{REF}"
        assert cell["candidate"] == "sdk@cand"

    def test_raw_samples_survive_for_every_arm(self, tmp_path: Path):
        # Re-analysing a surprising result offline is the difference between
        # understanding a red build and re-running the whole job to see the
        # same numbers again.
        doc = self.artifact(tmp_path, {REF: 1.0, "a": 1.0, "b": 1.3})
        cell = next(c for c in doc["cells"] if c["id"] == "encrypt")
        assert set(cell["samples"]) == {REF, "a", "b"}
        for arm in cell["samples"].values():
            assert len(arm["wall"]) == cell["n_rounds"]

    def test_the_bake_off_is_in_the_artifact(self, tmp_path: Path):
        doc = self.artifact(tmp_path, {REF: 1.0, "slow": 1.4, "quick": 1.0})
        wall = next(b for b in doc["bake_off"] if b["metric"] == "wall")
        assert wall["winner"] == "quick"

    def test_both_directional_p_values_are_recorded(self, tmp_path: Path):
        doc = self.artifact(tmp_path, {REF: 1.0, "cand": 0.7})
        cell = next(c for c in doc["cells"] if c["id"] == "encrypt")
        wall = cell["contrasts"][f"cand_vs_{REF}"]["wall"]
        assert wall["p_value"] is not None
        assert wall["p_adjusted"] is not None
        assert wall["p_value_faster"] is not None
        assert wall["p_adjusted_faster"] is not None

    def test_the_file_is_valid_json_despite_nan(self, tmp_path: Path):
        # A cell with no usable interval produces NaN, which `json.dumps`
        # would happily write as a bare `NaN` that no strict parser accepts.
        cfg = config(min_rounds=stats.MIN_USABLE_ROUNDS, max_rounds=40)
        rec = recorder({REF: 1.0, "a": 1.0, "b": 1.0}, cfg=cfg, control=False)
        path = report.write_json(tmp_path / "b.json", rec, cfg, rec.gate(cfg))
        json.loads(path.read_text())  # strict by default: no NaN accepted


class TestMarkdown:
    def test_the_header_names_the_arm_count(self):
        cfg = config(max_rounds=40)
        rec = recorder({REF: 1.0, "a": 1.0, "b": 1.0}, cfg=cfg, noise=0.02)
        md = report.markdown(rec, cfg, rec.gate(cfg))
        assert "3-arm" in md

    def test_the_table_names_both_sides_of_each_contrast(self):
        cfg = config(max_rounds=40)
        rec = recorder({REF: 1.0, "a": 1.0, "b": 1.3}, cfg=cfg, noise=0.02)
        md = report.markdown(rec, cfg, rec.gate(cfg))
        assert "| contrast |" in md
        assert "| `b` vs `a` |" in md, "the head-to-head is the point of a bake-off"
        assert "| `a` vs `base` |" in md

    def test_a_bake_off_section_appears_only_with_candidates_to_rank(self):
        cfg = config(max_rounds=40)
        two = recorder({REF: 1.0, "cand": 1.3}, cfg=cfg, noise=0.02)
        assert "### Bake-off" not in report.markdown(two, cfg, two.gate(cfg))
        three = recorder({REF: 1.0, "a": 1.0, "b": 1.3}, cfg=cfg, noise=0.02)
        assert "### Bake-off" in report.markdown(three, cfg, three.gate(cfg))

    def test_the_bottom_line_precedes_supporting_detail(self):
        cfg = config(max_rounds=40)
        rec = recorder({REF: 1.0, "cand": 1.35}, cfg=cfg, noise=0.01)
        md = report.markdown(rec, cfg, rec.gate(cfg))

        assert md.index("### TL;DR") < md.index("### Compared builds")
        assert md.index("### Compared builds") < md.index("### What changed")
        assert md.index("### What changed") < md.index("All measurements")
        assert md.index("All measurements") < md.index("### Run facts")

    def test_provenance_links_releases_prs_commits_and_the_diff(self):
        cfg = config(max_rounds=40)
        rec = recorder({REF: 1.0, "cand": 1.35}, cfg=cfg, noise=0.01)
        repo = "https://github.com/opentdf/platform"
        rec.metadata = {
            "github_run_url": "https://github.com/opentdf/tests/actions/runs/42",
            "arm_sources": [
                {
                    "tag": REF,
                    "alias": "latest",
                    "release": "otdfctl/v0.40.0",
                    "sha": "a" * 40,
                    "repo_url": repo,
                },
                {
                    "tag": "cand",
                    "alias": "feature",
                    "pr": 123,
                    "head": True,
                    "sha": "b" * 40,
                    "repo_url": repo,
                },
            ],
        }
        md = report.markdown(
            rec,
            cfg,
            rec.gate(cfg),
            artifact_url="https://github.com/opentdf/tests/actions/runs/42/artifacts/7",
        )

        assert f"{repo}/releases/tag/otdfctl%2Fv0.40.0" in md
        assert f"{repo}/pull/123" in md
        assert f"{repo}/commit/{'b' * 40}" in md
        assert f"{repo}/compare/{'a' * 40}...{'b' * 40}" in md
        assert "actions/runs/42/artifacts/7" in md
        assert "actions/runs/42" in md
        assert "candidate A" in md

    def test_the_primary_table_omits_clean_rows_but_the_full_table_keeps_them(self):
        cfg = config(min_rounds=10, max_rounds=60)
        rec = recorder({REF: 1.0, "clean": 1.0, "slow": 1.4}, cfg=cfg, noise=0.005)
        md = report.markdown(rec, cfg, rec.gate(cfg))
        primary = md.split("### What changed", 1)[1].split("### Bake-off", 1)[0]

        assert "`slow` vs `base`" in primary
        assert "`clean` vs `base`" not in primary
        assert "`clean` vs `base`" in md

    def test_attention_rows_get_shared_scale_unicode_views(self):
        cfg = config(max_rounds=40)
        rec = recorder({REF: 1.0, "cand": 1.35}, cfg=cfg, noise=0.01)
        md = report.markdown(rec, cfg, rec.gate(cfg))

        assert "#### Effect at a glance" in md
        assert "┆" in md and "│" in md and "●" in md
        assert "Round stability for attention rows" in md
        assert any("\u2800" <= char <= "\u28ff" for char in md)

    def test_extreme_effects_fit_and_name_their_candidate(self):
        cfg = config(min_rounds=12, max_rounds=40)
        rec = recorder({REF: 1.0, "epic": 0.02, "fast": 0.5}, cfg=cfg, noise=0.005)
        md = report.markdown(rec, cfg, rec.gate(cfg))
        effect = md.split("#### Effect at a glance", 1)[1].split("### Bake-off", 1)[0]

        assert "candidate A" in effect and "candidate B" in effect
        assert "-98.0%" in effect and "-49.7%" in effect
        assert "◀" not in effect
        assert "◆" in effect

    def test_run_facts_end_the_summary_with_reproducibility_context(self):
        cfg = config(max_rounds=40, seed=91)
        rec = recorder({REF: 1.0, "cand": 1.0}, cfg=cfg, noise=0.01)
        rec.metadata = {
            "platform_version": "v0.4.50",
            "runner_os": "Linux",
        }
        md = report.markdown(rec, cfg, rec.gate(cfg))

        assert "### Run facts" in md
        assert "v0.4.50" in md and "Linux" in md
        assert "seed 91" in md
        assert md.rstrip().endswith("cells skipped.</sub>")

    def test_braille_trace_is_compact_and_deterministic(self):
        values = [0.9, 1.0, 1.1, 1.2] * 20
        trace = report._braille_sparkline(values, 1.15)

        assert trace == report._braille_sparkline(values, 1.15)
        assert len(trace) == 24
        assert all("\u2800" <= char <= "\u28ff" for char in trace)


class TestMarkdownTemplate:
    def test_it_can_be_published_after_the_artifact_url_is_known(self, tmp_path: Path):
        path = report.write_markdown(
            tmp_path / "go.summary.md",
            f"[evidence]({report.ARTIFACT_URL_PLACEHOLDER})\n",
        )

        assert report.ARTIFACT_URL_PLACEHOLDER in path.read_text()
