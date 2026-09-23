"""Unit tests for benchmark arm selection and payload generation.

Both decide *what* gets measured, before any measuring happens, and both fail
quietly when they get it wrong: a baseline that is silently a release
candidate, or a payload whose bytes changed between two runs that claim to be
comparable. Neither shows up as an error -- only as numbers that mean
something other than what the report says they mean.

No platform and no real SDK; the builds are stub ``cli.sh`` trees in
``tmp_path``.
"""

import json
from pathlib import Path
from typing import cast

import pytest

import tdfs
from fixtures import bench
from perf.cells import cells_for
from perf.runner import BenchConfig


def install(root: Path, sdk: str, *versions: str) -> None:
    """Lay down a stub build tree, as ``otdf-sdk-mgr install`` would."""
    for version in versions:
        cli = root / "sdk" / sdk / "dist" / version / "cli.sh"
        cli.parent.mkdir(parents=True)
        cli.write_text("#!/bin/sh\nexit 0\n")


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`SDK.__init__` resolves `cli.sh` relative to the cwd, so move there."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class FakeConfig:
    """A ``pytest.Config`` stub answering the ``--bench-*`` options named."""

    def __init__(self, **opts: str | None) -> None:
        self._opts = {name.replace("_", "-"): value for name, value in opts.items()}

    def getoption(self, name: str) -> str | None:
        return self._opts.get(name.removeprefix("--"))


def options(**opts: str | None) -> pytest.Config:
    return cast(pytest.Config, FakeConfig(**opts))


class TestFinalRelease:
    @pytest.mark.parametrize("version", ["v0.29.0", "0.29.0"])
    def test_accepts_a_plain_tag(self, cwd: Path, version: str):
        install(cwd, "go", version)
        assert tdfs.SDK("go", version).is_final_release()

    @pytest.mark.parametrize(
        "version", ["v0.29.0-rc.1", "v0.29.0+build.5", "main", "DSPX-1234"]
    )
    def test_rejects_anything_else(self, cwd: Path, version: str):
        install(cwd, "go", version)
        assert not tdfs.SDK("go", version).is_final_release()


class TestBaselineSelection:
    def test_picks_the_newest_final_release(self, cwd: Path):
        install(cwd, "go", "main", "v0.28.0", "v0.29.0")
        baseline, candidate = bench.select_arms("go")
        assert baseline.version == "v0.29.0"
        assert candidate.version == "main"

    def test_a_release_candidate_never_becomes_the_baseline(self, cwd: Path):
        # An rc parses to the same semver as its final release, so ordering by
        # semver alone leaves the two tied and the directory listing breaks
        # the tie -- a baseline nobody chose, differing run to run.
        install(cwd, "go", "main", "v0.29.0", "v0.29.0-rc.1", "v0.30.0-rc.1")
        baseline, _ = bench.select_arms("go")
        assert baseline.version == "v0.29.0"

    def test_no_final_release_is_a_clear_refusal(self, cwd: Path):
        install(cwd, "go", "main", "v0.30.0-rc.1")
        with pytest.raises(bench.ArmSelectionError, match="no final go release"):
            bench.select_arms("go")

    def test_no_branch_build_is_a_clear_refusal(self, cwd: Path):
        install(cwd, "go", "v0.29.0")
        with pytest.raises(bench.ArmSelectionError, match="no unreleased go build"):
            bench.select_arms("go")

    def test_explicit_specs_win(self, cwd: Path):
        install(cwd, "go", "main", "v0.28.0", "v0.29.0")
        baseline, candidate = bench.select_arms("go", ["go@v0.28.0", "go@v0.29.0"])
        assert (baseline.version, candidate.version) == ("v0.28.0", "v0.29.0")

    def test_refuses_to_compare_a_build_against_itself(self, cwd: Path):
        install(cwd, "go", "main", "v0.29.0")
        with pytest.raises(bench.ArmSelectionError, match="same build"):
            bench.select_arms("go", ["go@main", "go@main"])

    def test_two_branch_builds_need_explicit_specs(self, cwd: Path):
        # What a branch-vs-branch dispatch installs: two heads and no release
        # at all. Named explicitly it is a fine comparison; left to the default
        # there is no baseline, and "newest final release" cannot invent one.
        install(cwd, "go", "main", "feat--DSPX-2604-createtdf-chunked")
        baseline, candidate = bench.select_arms(
            "go", ["go@main", "go@feat--DSPX-2604-createtdf-chunked"]
        )
        assert baseline.version == "main"
        assert candidate.version == "feat--DSPX-2604-createtdf-chunked"
        with pytest.raises(bench.ArmSelectionError, match="no final go release"):
            bench.select_arms("go")

    def test_the_first_spec_is_the_reference(self, cwd: Path):
        # Order is the whole interface: every gated contrast is taken against
        # arms[0], so reversing the list reverses which build is on trial.
        install(cwd, "go", "main", "a--impl", "b--impl")
        arms = bench.select_arms("go", ["go@main", "go@a--impl", "go@b--impl"])
        assert [a.version for a in arms] == ["main", "a--impl", "b--impl"]
        assert bench.BenchArms(arms).reference.version == "main"
        assert [a.version for a in bench.BenchArms(arms).candidates] == [
            "a--impl",
            "b--impl",
        ]

    def test_a_missing_arm_names_which_one(self, cwd: Path):
        install(cwd, "go", "main", "a--impl")
        with pytest.raises(bench.ArmSelectionError, match="arm 3"):
            bench.select_arms("go", ["go@main", "go@a--impl", "go@nope"])


class TestRefSpecParsing:
    def test_commas_or_whitespace_both_work(self):
        assert bench.parse_refs("go@main,go@a") == ("go@main", "go@a")
        assert bench.parse_refs("go@main go@a") == ("go@main", "go@a")

    def test_a_single_ref_is_refused(self):
        # One arm is not a comparison, and the harness reports only ratios.
        with pytest.raises(ValueError, match="need 2 to 4 refs"):
            bench.parse_refs("go@main")

    def test_more_than_four_is_refused(self):
        # setup-cli-tool installs four builds side by side; a fifth would be
        # silently absent at measurement time.
        with pytest.raises(ValueError, match="need 2 to 4 refs"):
            bench.parse_refs("go@a,go@b,go@c,go@d,go@e")

    def test_a_repeated_ref_is_refused(self):
        with pytest.raises(ValueError, match="duplicate"):
            bench.parse_refs("go@main,go@main")


class TestSpecsForSdk:
    def test_specs_naming_another_sdk_fall_back_to_the_default(self):
        # A run measuring go and java with refs for go only: java still gets
        # its own default pair rather than an error or go's builds.
        assert bench._specs_for(("go@main", "go@a"), "java") is None

    def test_a_mixed_sdk_list_is_an_error(self):
        with pytest.raises(bench.ArmSelectionError, match="more than one SDK"):
            bench._specs_for(("go@main", "java@main"), "go")


class TestArmOptions:
    def test_no_options_means_the_default_pair(self):
        # The nightly passes nothing at all, and must keep getting the
        # (newest release, branch head) comparison it has always run.
        assert bench.arm_specs_from_options(options()) is None
        assert bench.arm_count(options()) == 2

    def test_the_two_arm_shorthand_still_works(self):
        cfg = options(bench_baseline="go@v0.29.0", bench_candidate="go@main")
        assert bench.arm_specs_from_options(cfg) == ("go@v0.29.0", "go@main")

    def test_half_a_pair_is_a_usage_error(self):
        with pytest.raises(pytest.UsageError, match="together"):
            bench.arm_specs_from_options(options(bench_baseline="go@main"))

    def test_mixing_the_two_forms_is_a_usage_error(self):
        # There is no reading of "--bench-refs a,b --bench-candidate c" that
        # is not a mistake, and silently picking one would measure something
        # nobody asked for.
        cfg = options(bench_refs="go@a,go@b", bench_candidate="go@c")
        with pytest.raises(pytest.UsageError, match="cannot be combined"):
            bench.arm_specs_from_options(cfg)

    def test_a_malformed_refs_list_is_a_usage_error(self):
        with pytest.raises(pytest.UsageError, match="invalid --bench-refs"):
            bench.arm_specs_from_options(options(bench_refs="go@main"))

    def test_the_arm_count_follows_the_refs(self):
        assert bench.arm_count(options(bench_refs="go@a,go@b,go@c")) == 3


class TestRunnerMetadata:
    def test_resolver_provenance_is_preserved_and_enriched(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv(
            "BENCH_VERSION_INFO",
            json.dumps(
                [
                    {
                        "sdk": "go",
                        "tag": "v0.30.0",
                        "release": "v0.30.0",
                        "sha": "a" * 40,
                    },
                    {
                        "sdk": "go",
                        "tag": "feature",
                        "pr": 42,
                        "head": True,
                        "sha": "b" * 40,
                    },
                ]
            ),
        )

        sources, warning = bench._arm_sources()

        assert warning == ""
        assert sources[0]["repo_url"] == "https://github.com/opentdf/otdfctl"
        assert sources[1]["repo_url"] == "https://github.com/opentdf/platform"

    def test_bad_resolver_metadata_degrades_to_an_explanation(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("BENCH_VERSION_INFO", "not-json")

        sources, warning = bench._arm_sources()

        assert sources == []
        assert "not valid JSON" in warning

    def test_workflow_url_needs_all_three_parts(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_REPOSITORY", "opentdf/tests")
        monkeypatch.setenv("GITHUB_RUN_ID", "123")
        assert bench._github_run_url() == (
            "https://github.com/opentdf/tests/actions/runs/123"
        )

        monkeypatch.delenv("GITHUB_RUN_ID")
        assert bench._github_run_url() == ""

    def test_requested_names_survive_resolver_deduplication(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("BENCH_REQUESTED_REFS", "main latest")

        assert bench._requested_refs() == ["main", "latest"]

    def test_one_resolved_sha_from_two_names_is_marked_same_commit(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("BENCH_REQUESTED_REFS", "main latest")
        monkeypatch.setattr(
            bench,
            "_arm_sources",
            lambda: ([{"tag": "main", "sha": "a" * 40}], ""),
        )
        monkeypatch.setattr(bench, "_platform_version", lambda: "test")

        metadata = bench.runner_metadata(options(bench_seed="0"))

        assert metadata["comparison_status"] == "same_commit"
        assert "main, latest" in str(metadata["comparison_note"])


class TestDefaultBudget:
    def test_two_arms_keep_the_number_the_default_was_chosen_for(self):
        assert bench.default_budget_seconds(2) == BenchConfig().budget_seconds

    def test_the_budget_scales_with_the_arm_count(self):
        # A round costs one invocation per arm, so at a fixed budget the round
        # count falls as 2/K and every interval widens as sqrt(K/2). Scaling
        # the default by K/2 buys back the precision instead of quietly
        # trading it for arms and reporting the loss as INCONCLUSIVE.
        base = BenchConfig().budget_seconds
        assert bench.default_budget_seconds(3) == base * 1.5
        assert bench.default_budget_seconds(4) == base * 2

    def test_an_explicit_budget_is_taken_as_given(self):
        cfg = FakeConfig(
            bench_refs="go@a,go@b,go@c",
            bench_budget_seconds="900",
            bench_min_rounds="20",
            bench_max_rounds="60",
            bench_warmup="5",
            bench_seed="1",
            bench_threshold="1.15",
        )
        built = bench.config_from_options(cast(pytest.Config, cfg))
        assert built.budget_seconds == 900.0, "a named number is not scaled"


class TestDistTagShape:
    def test_a_slashed_tag_breaks_discovery(self, cwd: Path):
        # Why otdf-sdk-mgr flattens '/' to '--' in a resolved ref. A branch
        # installed as dist/feat/x/ is listed as a build named "feat", which
        # has no cli.sh -- and this raises during collection, before any cell
        # has a chance to report why.
        install(cwd, "go", "feat/DSPX-2604-createtdf-chunked")
        with pytest.raises(FileNotFoundError):
            tdfs.all_versions_of("go")

    def test_a_flattened_tag_is_discovered(self, cwd: Path):
        install(cwd, "go", "feat--DSPX-2604-createtdf-chunked")
        assert [s.version for s in tdfs.all_versions_of("go")] == [
            "feat--DSPX-2604-createtdf-chunked"
        ]


def stub_sdk(cwd: Path, version: str, **features: bool) -> tdfs.SDK:
    """An installed stub build whose feature support is stated, not inferred.

    Real support is derived from the version string, which would make these
    tests assertions about the version table rather than about arm selection.
    """
    install(cwd, "go", version)
    sdk = tdfs.SDK("go", version)
    sdk._supports.update(cast(dict[tdfs.feature_type, bool], features))
    return sdk


#: Every comparability feature present, which is the uninteresting case.
COMPARABLE = {"hexless": True, "hexaflexible": True, "autoconfigure": True}


class TestComparability:
    def test_matching_arms_are_comparable(self, cwd: Path):
        arms = bench.BenchArms(
            (
                stub_sdk(cwd, "main", **COMPARABLE),
                stub_sdk(cwd, "a--impl", **COMPARABLE),
                stub_sdk(cwd, "b--impl", **COMPARABLE),
            )
        )
        assert bench.comparability_problem(arms) is None

    def test_every_candidate_is_checked_against_the_reference(self, cwd: Path):
        # Checking only adjacent pairs would clear a third arm that disagrees
        # with the reference, and its gated contrast is taken against exactly
        # that reference -- so it would be timing different work.
        odd_one_out = bench.BenchArms(
            (
                stub_sdk(cwd, "main", **COMPARABLE),
                stub_sdk(cwd, "a--impl", **COMPARABLE),
                stub_sdk(cwd, "b--impl", **(COMPARABLE | {"autoconfigure": False})),
            )
        )
        problem = bench.comparability_problem(odd_one_out)
        assert problem is not None
        assert "b--impl" in problem and "autoconfigure" in problem

    def test_the_target_mode_is_pinned_only_when_every_arm_can_be_told(self, cwd: Path):
        # Letting one arm choose its own container version would compare
        # output formats rather than speed.
        all_new = (
            stub_sdk(cwd, "main", **COMPARABLE),
            stub_sdk(cwd, "a--impl", **COMPARABLE),
        )
        assert bench.pinned_target_mode(bench.BenchArms(all_new)) == "4.3.0"
        one_old = all_new + (
            stub_sdk(cwd, "b--impl", **(COMPARABLE | {"hexaflexible": False})),
        )
        assert bench.pinned_target_mode(bench.BenchArms(one_old)) is None


class TestBuildArms:
    def cell_arms(self, cwd: Path, control: bool, n: int):
        arms = bench.BenchArms(
            tuple(
                stub_sdk(cwd, v, **COMPARABLE)
                for v in ("main", "a--impl", "b--impl", "c--impl")[:n]
            )
        )
        cells = cells_for(["go"])
        cell = next(
            c for c in cells if c.control is control and c.operation == "encrypt"
        )
        pt = cwd / "plain.bin"
        pt.write_bytes(b"x" * 1024)
        return bench.build_arms(
            cell,
            arms,
            pt_file=pt,
            ct_file=None,
            tmp_dir=cwd,
            attr_values=[],
        )

    def test_one_arm_per_build(self, cwd: Path):
        built = self.cell_arms(cwd, control=False, n=3)
        assert [a.name for a in built] == ["main", "a--impl", "b--impl"]

    def test_every_arm_writes_its_own_output(self, cwd: Path):
        # Sharing an output path would have the arms overwrite each other
        # mid-round, and the second one would be measured deleting the first.
        built = self.cell_arms(cwd, control=False, n=3)
        assert len({a.invocation.output for a in built}) == 3

    def test_the_control_is_k_copies_of_the_reference(self, cwd: Path):
        # Not a cheap pair: in a K-arm round the last arm runs K-1 invocations
        # after the first, so a two-arm control would measure less drift than
        # the contrasts it is the noise floor for.
        built = self.cell_arms(cwd, control=True, n=3)
        assert len(built) == 3
        assert {a.label for a in built} == {"go@main"}
        assert len({a.name for a in built}) == 3, "ids key the sample vectors"
        assert len({a.invocation.output for a in built}) == 3
