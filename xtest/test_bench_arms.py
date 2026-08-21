"""Unit tests for benchmark arm selection and payload generation.

Both decide *what* gets measured, before any measuring happens, and both fail
quietly when they get it wrong: a baseline that is silently a release
candidate, or a payload whose bytes changed between two runs that claim to be
comparable. Neither shows up as an error -- only as numbers that mean
something other than what the report says they mean.

No platform and no real SDK; the builds are stub ``cli.sh`` trees in
``tmp_path``.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

import tdfs
from fixtures import bench
from perf.cells import (
    CONTROL_PAYLOAD,
    DEFAULT_PAYLOAD_SPEC,
    PAYLOADS,
    Payload,
    cells_for,
    parse_payload,
    parse_payloads,
)
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

    def test_two_branch_builds_need_explicit_specs(self, cwd: Path):
        # What a branch-vs-branch dispatch installs: two heads and no release
        # at all. Named explicitly it is a fine comparison; left to the default
        # there is no baseline, and "newest final release" cannot invent one.
        install(cwd, "go", "main", "feat--DSPX-2604-createtdf-chunked")
        baseline, candidate = bench.select_arms(
            "go",
            baseline_spec="go@main",
            candidate_spec="go@feat--DSPX-2604-createtdf-chunked",
        )
        assert baseline.version == "main"
        assert candidate.version == "feat--DSPX-2604-createtdf-chunked"
        with pytest.raises(bench.ArmSelectionError, match="no final go release"):
            bench.select_arms("go")


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


class TestPayloadSpec:
    @pytest.mark.parametrize(
        ("spec", "n_bytes"),
        [
            ("512B", 512),
            ("1KiB", 1024),
            ("32MiB", 32 * 2**20),
            ("1GiB", 2**30),
            ("4GiB", 4 * 2**30),
        ],
    )
    def test_sizes_parse(self, spec: str, n_bytes: int):
        assert parse_payload(spec).n_bytes == n_bytes

    def test_the_label_is_canonical_regardless_of_case(self):
        # The label is a filename and a cell id. '1gib' and '1GiB' naming two
        # cells would measure one size twice and report it as two results.
        assert parse_payload("1gib").label == "1GiB"
        assert parse_payload(" 1 GIB ").label == "1GiB"

    @pytest.mark.parametrize(
        "spec", ["", "1", "MiB", "1MB", "1.5GiB", "-1GiB", "0GiB", "1GiB extra"]
    )
    def test_junk_is_refused(self, spec: str):
        with pytest.raises(ValueError):
            parse_payload(spec)

    def test_a_list_is_sorted_ascending(self):
        labels = [p.label for p in parse_payloads("1GiB,1KiB,32MiB")]
        assert labels == ["1KiB", "32MiB", "1GiB"]

    def test_one_size_written_two_ways_is_one_payload(self):
        # Otherwise the run pays for two identical cells and reports them as
        # independent results, which the multiplicity correction then treats
        # as two tests.
        assert [p.label for p in parse_payloads("1KiB,1024B")] == ["1KiB"]

    def test_an_empty_list_is_refused(self):
        with pytest.raises(ValueError, match="no payload sizes"):
            parse_payloads(" , ")


class TestCellMatrix:
    def test_the_default_matrix_is_unchanged(self):
        ids = [c.id for c in cells_for(["go"], parse_payloads(DEFAULT_PAYLOAD_SPEC))]
        assert ids == [
            "go-encrypt-1MiB-control",
            "go-encrypt-1KiB",
            "go-decrypt-1KiB",
            "go-encrypt-1MiB",
            "go-decrypt-1MiB",
            "go-encrypt-32MiB",
            "go-decrypt-32MiB",
        ]

    def test_the_control_comes_first_and_the_biggest_pair_last(self):
        # The budget is spent in cell order, so whatever is last is what a
        # short run loses. Losing the control invalidates every other cell;
        # losing the largest pair costs the most expensive measurement but
        # leaves the rest readable.
        cells = cells_for(["go"], parse_payloads("1KiB,1GiB"))
        assert cells[0].control
        assert [c.id for c in cells[-2:]] == ["go-encrypt-1GiB", "go-decrypt-1GiB"]

    def test_the_control_size_does_not_follow_the_selection(self):
        # The control's CI width is the run's noise floor and every cell is
        # judged against it. If it moved with --bench-payloads, two runs of
        # the same comparison could disagree on which cells are trustworthy.
        for spec in ("1KiB", "1GiB", DEFAULT_PAYLOAD_SPEC):
            control = next(c for c in cells_for(["go"], parse_payloads(spec)))
            assert control.payload == CONTROL_PAYLOAD


#: The fixture body, called directly: these tests are about the bytes it
#: writes, not about pytest's fixture wiring.
_make_payloads = bench.bench_payloads.__wrapped__  # pyright: ignore[reportAttributeAccessIssue]


def make_payloads(
    tmp_path: Path, config: BenchConfig, payloads: Sequence[Payload] = PAYLOADS
) -> dict[str, Path]:
    return _make_payloads(tmp_path, config, tuple(payloads))


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

    def test_the_controls_payload_is_generated_even_when_not_selected(
        self, tmp_path: Path
    ):
        # --bench-payloads 1GiB is a legitimate ask, and the A/A control still
        # needs its own file. Without it the control cell dies on a KeyError
        # in arm construction -- and a run with no control can pass nothing.
        out = make_payloads(tmp_path, BenchConfig(seed=1), [Payload("4KiB", 4096)])
        assert out[CONTROL_PAYLOAD.label].stat().st_size == CONTROL_PAYLOAD.n_bytes

    def test_chunking_does_not_change_the_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # A 1 GiB payload is written in chunks rather than built in RAM. The
        # chunk size must not be part of the seed contract: a run compared
        # against an earlier one has to measure the same bytes, and the check
        # is cheap next to the cost of discovering otherwise.
        payload = Payload("40KiB", 40 * 1024)
        whole = subdir(tmp_path, "whole")
        bench.write_payload(whole / "p.bin", payload, seed=7)
        monkeypatch.setattr(bench, "_CHUNK_BYTES", 4096)
        chunked = subdir(tmp_path, "chunked")
        bench.write_payload(chunked / "p.bin", payload, seed=7)
        assert (whole / "p.bin").read_bytes() == (chunked / "p.bin").read_bytes()

    def test_a_payload_too_big_for_the_disk_is_refused_up_front(self, tmp_path: Path):
        # Running out of disk mid-benchmark surfaces as a non-zero exit from
        # the CLI under measurement, which reads as "this build is broken".
        huge = Payload("1024GiB", 1024 * 2**30)
        assert bench.disk_shortfall(tmp_path, [huge]) is not None
        assert bench.disk_shortfall(tmp_path, [Payload("1KiB", 1024)]) is None


def read_all(paths: dict[str, Path]) -> dict[str, bytes]:
    return {label: p.read_bytes() for label, p in paths.items()}


def subdir(root: Path, name: str) -> Path:
    out = root / name
    out.mkdir()
    return out
