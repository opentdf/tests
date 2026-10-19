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
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

import tdfs
from fixtures import bench
from perf.cells import PAYLOADS, cells_for
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
        baseline, candidate = bench.select_arms(
            "go", baseline_spec="go@v0.28.0", candidate_spec="go@v0.29.0"
        )
        assert (baseline.version, candidate.version) == ("v0.28.0", "v0.29.0")

    def test_refuses_to_compare_a_build_against_itself(self, cwd: Path):
        install(cwd, "go", "main", "v0.29.0")
        with pytest.raises(bench.ArmSelectionError, match="nothing to compare"):
            bench.select_arms("go", baseline_spec="go@main", candidate_spec="go@main")


#: The fixture body, called directly: these tests are about the bytes it
#: writes, not about pytest's fixture wiring.
make_payloads = bench.bench_payloads.__wrapped__  # pyright: ignore[reportAttributeAccessIssue]


class TestPayloads:
    def test_every_size_is_generated(self, tmp_path: Path):
        out = make_payloads(tmp_path, BenchConfig(seed=1))
        for payload in PAYLOADS:
            assert out[payload.label].stat().st_size == payload.n_bytes

    def test_a_seed_reproduces_the_bytes(self, tmp_path: Path):
        a = read_all(make_payloads(subdir(tmp_path, "a"), BenchConfig(seed=1)))
        b = read_all(make_payloads(subdir(tmp_path, "b"), BenchConfig(seed=1)))
        assert a == b

    def test_a_different_seed_changes_them(self, tmp_path: Path):
        a = read_all(make_payloads(subdir(tmp_path, "a"), BenchConfig(seed=1)))
        b = read_all(make_payloads(subdir(tmp_path, "b"), BenchConfig(seed=2)))
        assert a != b

    def test_a_partial_cache_still_reproduces_the_bytes(self, tmp_path: Path):
        # tmp_dir persists between runs. With one RNG stream shared across the
        # payloads, skipping a cached file shifts every payload after it, so a
        # rerun measures different input than the run it is compared against.
        first = read_all(make_payloads(tmp_path, BenchConfig(seed=1)))
        (tmp_path / f"bench-plain-{PAYLOADS[0].label}.bin").unlink()
        second = read_all(make_payloads(tmp_path, BenchConfig(seed=1)))
        assert first == second

    def test_a_truncated_cache_entry_is_regenerated(self, tmp_path: Path):
        first = read_all(make_payloads(tmp_path, BenchConfig(seed=1)))
        path = tmp_path / f"bench-plain-{PAYLOADS[1].label}.bin"
        path.write_bytes(b"truncated")
        second = read_all(make_payloads(tmp_path, BenchConfig(seed=1)))
        assert first == second


def read_all(paths: dict[str, Path]) -> dict[str, bytes]:
    return {label: p.read_bytes() for label, p in paths.items()}


def subdir(root: Path, name: str) -> Path:
    out = root / name
    out.mkdir()
    return out


class FakeConfig:
    """Just enough of ``pytest.Config`` for the option-reading helpers."""

    def __init__(self, **opts: object) -> None:
        self._opts: dict[str, object] = {
            "--bench-refs": None,
            "--bench-baseline": None,
            "--bench-candidate": None,
            "--bench-min-rounds": 20,
            "--bench-max-rounds": 60,
            "--bench-warmup": 5,
            "--bench-budget-seconds": None,
            "--bench-seed": 0,
            "--bench-threshold": 1.15,
        } | opts
        self.stash = pytest.Stash()

    def getoption(self, name: str, default: object = None) -> object:
        return self._opts.get(name, default)


def options(**opts: object) -> pytest.Config:
    return cast(pytest.Config, FakeConfig(**opts))


def prepared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tags: Sequence[str],
    *,
    sdk: str = "go",
    status: str = "success",
    message: str = "",
) -> None:
    """Point the run at a manifest recording ``tags`` as its arms, in order."""
    doc = {
        "schema_version": "v1alpha1",
        "sdk_arms": [
            {
                "requested_alias": t,
                "repository": "https://github.com/opentdf/platform.git",
                "commit_sha": f"{i:040d}",
                "installed_tag": t,
                "installed_path": "",
                "installation_method": "source",
            }
            for i, t in enumerate(tags)
        ],
        "status": status,
        "status_message": message,
        "metadata": {"sdk": sdk},
    }
    path = tmp_path / "benchmark.installed.json"
    path.write_text(json.dumps(doc))
    monkeypatch.setenv("BENCH_INSTALLATION_MANIFEST", str(path))


@pytest.fixture(autouse=True)
def _no_ambient_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    # `otdf-local env` exports this; a developer's shell must not change what
    # these tests see.
    monkeypatch.delenv("BENCH_INSTALLATION_MANIFEST", raising=False)


class TestMultiArmSelection:
    def test_named_arms_resolve_in_order(self, cwd: Path):
        install(cwd, "go", "main", "v0.29.0", "my-branch")
        arms = bench.select_arms("go", ["go@v0.29.0", "go@main", "go@my-branch"])
        assert [a.version for a in arms] == ["v0.29.0", "main", "my-branch"]

    def test_a_missing_arm_is_named(self, cwd: Path):
        install(cwd, "go", "main", "v0.29.0")
        with pytest.raises(bench.ArmSelectionError, match="arm 3"):
            bench.select_arms("go", ["go@v0.29.0", "go@main", "go@nope"])


class TestPreparedArms:
    def test_the_manifest_supplies_the_arms_in_request_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        prepared(tmp_path, monkeypatch, ["v0.29.0", "main", "my--branch"])
        config = options()
        assert bench.arm_specs_from_options(config) == (
            "go@v0.29.0",
            "go@main",
            "go@my--branch",
        )
        assert bench.arm_count(config) == 3
        # The default budget follows the prepared arm count.
        assert bench.config_from_options(config).budget_seconds == 2250.0

    def test_explicit_refs_win_over_the_manifest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        prepared(tmp_path, monkeypatch, ["v0.29.0", "main"])
        config = options(**{"--bench-refs": "go@v0.28.0,go@main"})
        assert bench.arm_specs_from_options(config) == ("go@v0.28.0", "go@main")
        assert bench.preparation_problem(config, "go") is None

    def test_a_neutral_preparation_skips_with_its_reason_and_is_neutral(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        prepared(
            tmp_path,
            monkeypatch,
            ["latest", "main"],
            status="neutral",
            message="All 2 requested aliases resolved to the same commit: abc12345",
        )
        config = options()
        assert bench.arm_specs_from_options(config) is None
        problem = bench.preparation_problem(config, "go")
        assert problem is not None and "neutral" in problem and "abc12345" in problem
        assert bench.preparation_is_neutral(config)
        assert bench.runner_metadata(config)["preparation"] == "neutral"

    def test_a_failed_preparation_is_a_problem_but_not_neutral(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        prepared(tmp_path, monkeypatch, [], status="failed", message="no such ref")
        config = options()
        problem = bench.preparation_problem(config, "go")
        assert problem is not None and "no such ref" in problem
        assert not bench.preparation_is_neutral(config)

    def test_another_sdks_manifest_does_not_affect_this_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        prepared(
            tmp_path, monkeypatch, ["latest", "main"], sdk="java", status="neutral"
        )
        assert bench.preparation_problem(options(), "go") is None

    def test_a_resolver_with_a_problem_skips_that_sdk(self):
        resolver = bench.ArmResolver(None, problem={"go": "neutral preparation: x"})
        with pytest.raises(bench.ArmSelectionError, match="neutral"):
            resolver("go")


class TestBuildArms:
    def arms(self, cwd: Path, n: int) -> bench.BenchArms:
        versions = ("main", "a--impl", "b--impl", "c--impl")[:n]
        install(cwd, "go", *versions)
        for v in versions:
            # `supports` runs the stub, which then answers yes to everything.
            (cwd / "sdk" / "go" / "dist" / v / "cli.sh").chmod(0o755)
        return bench.BenchArms(tuple(tdfs.SDK("go", v) for v in versions))

    @pytest.mark.parametrize("n", [2, 3, 4])
    def test_a_cell_runs_each_build_once(self, cwd: Path, n: int):
        arms = self.arms(cwd, n)
        cell = next(c for c in cells_for(["go"]) if not c.control)
        built = bench.build_arms(
            cell, arms, pt_file=cwd / "pt", ct_file=None, tmp_dir=cwd, attr_values=[]
        )
        assert [a.name for a in built] == [s.version for s in arms.arms]
        assert len({a.invocation.output for a in built}) == n

    @pytest.mark.parametrize("n", [2, 3, 4])
    def test_the_control_is_k_copies_of_the_reference(self, cwd: Path, n: int):
        # As many arms as the real cells: the last of K drifts further from
        # the first than an adjacent pair does, and a two-arm control would
        # understate the noise of the contrasts being judged.
        arms = self.arms(cwd, n)
        control = next(c for c in cells_for(["go"]) if c.control)
        built = bench.build_arms(
            control, arms, pt_file=cwd / "pt", ct_file=None, tmp_dir=cwd, attr_values=[]
        )
        assert len(built) == n
        assert {a.label for a in built} == {"go@main"}
        assert len({a.name for a in built}) == n, "ids key the sample vectors"
        assert len({a.invocation.output for a in built}) == n
