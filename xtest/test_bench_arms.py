"""Unit tests for benchmark arm selection and payload generation.

Both decide *what* gets measured, before any measuring happens, and both fail
quietly when they get it wrong: a baseline that is silently a release
candidate, or a payload whose bytes changed between two runs that claim to be
comparable. Neither shows up as an error -- only as numbers that mean
something other than what the report says they mean.

No platform and no real SDK; the builds are stub ``cli.sh`` trees in
``tmp_path``.
"""

import random
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

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

    @pytest.mark.parametrize(
        ("spec", "label"),
        [
            ("1gib", "1GiB"),
            (" 1 GIB ", "1GiB"),
            ("1024MiB", "1GiB"),
            ("1024B", "1KiB"),
            ("1536KiB", "1536KiB"),
        ],
    )
    def test_the_label_is_canonical(self, spec: str, label: str):
        # The label is a filename, a cell id, and part of the seed. Two
        # spellings of one size naming two cells would measure it twice, on
        # different bytes, and report it as two results.
        assert parse_payload(spec).label == label

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
        for spec in ("1KiB,1024B", "1024B,1KiB"):
            assert [p.label for p in parse_payloads(spec)] == ["1KiB"]

    def test_an_empty_list_is_refused(self):
        with pytest.raises(ValueError, match="no payload sizes"):
            parse_payloads(" , ")

    def test_the_parser_needs_only_the_standard_library(self):
        # resolve-versions validates bench-payloads by importing perf.cells
        # with a bare python3, before any dependency is installed. -I -S
        # holds this interpreter to the standard library too.
        xtest = str(Path(__file__).parent)
        code = f"import sys; sys.path.insert(0, {xtest!r}); import perf.cells"
        run = subprocess.run(
            [sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True
        )
        assert run.returncode == 0, run.stderr


class TestCellMatrix:
    def test_the_default_matrix(self):
        # Each size's decrypt follows its encrypt, so a size's files are done
        # with before the next size starts -- which is what lets
        # --bench-prune-scratch delete its plaintext early.
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
        # The budget is shared out as each cell starts. Run last, the
        # expensive pair inherits whatever the cheap cells left unspent; run
        # first, it would be held to a bare even share. The control goes
        # before everything: without a noise floor no cell may report PASS.
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
        # bytes must still be those of one randbytes() call, as they were
        # before chunking, so a rerun measures the same input and a file
        # cached before the change stays valid. Three bytes past a whole
        # number of chunks exercises the short final chunk.
        payload = parse_payload("12291B")
        assert payload.n_bytes == 3 * 4096 + 3
        monkeypatch.setattr(bench, "_CHUNK_BYTES", 4096)
        bench.write_payload(tmp_path / "p.bin", payload, seed=7)
        whole = random.Random(f"7:{payload.label}").randbytes(payload.n_bytes)
        assert (tmp_path / "p.bin").read_bytes() == whole

    def test_the_chunk_size_keeps_the_stream_intact(self):
        # randbytes() draws 32-bit words. A chunk that is not a whole number
        # of words discards part of one and shifts every byte after it.
        assert bench._CHUNK_BYTES % 4 == 0


GIB = 2**30

#: A small size and a large one, so an estimate built on the largest size
#: cannot pass for one built on the sum, or the reverse.
TWO_SIZES = (Payload("32MiB", 32 * 2**20), Payload("1GiB", GIB))


def free_space(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    monkeypatch.setattr(
        shutil, "disk_usage", lambda p: SimpleNamespace(total=0, used=0, free=free)
    )


class TestScratchDisk:
    def test_a_payload_too_big_for_the_disk_is_refused_up_front(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Running out of disk mid-benchmark surfaces as a non-zero exit from
        # the CLI under measurement, which reads as "this build is broken".
        free_space(monkeypatch, 10 * GIB)
        huge = [Payload("1024GiB", 1024 * GIB)]
        small = [Payload("1KiB", 1024)]
        assert bench.disk_shortfall(tmp_path, huge, n_sdks=1, prune=True)
        assert bench.disk_shortfall(tmp_path, small, n_sdks=1, prune=True) is None

    def test_a_pruned_run_holds_the_plaintexts_and_one_cell(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Every plaintext, plus the largest decrypt cell's ciphertext and one
        # output per arm. Each cell's files go when it ends, so the number of
        # SDKs does not enter into it.
        total = sum(p.n_bytes for p in TWO_SIZES)
        need = total + 3 * GIB + bench._DISK_HEADROOM_BYTES
        free_space(monkeypatch, need)
        assert bench.disk_shortfall(tmp_path, TWO_SIZES, n_sdks=3, prune=True) is None
        assert bench.disk_shortfall(tmp_path, TWO_SIZES, n_sdks=3, prune=True, n_arms=3)
        free_space(monkeypatch, need - 1)
        assert bench.disk_shortfall(tmp_path, TWO_SIZES, n_sdks=3, prune=True)

    def test_an_unpruned_run_keeps_every_cells_files_for_every_sdk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Each SDK leaves a ciphertext per size and one output per arm from
        # both of that size's cells: five times the sum of the sizes, on top
        # of the plaintexts.
        total = sum(p.n_bytes for p in TWO_SIZES)
        need = total + 2 * 5 * total + bench._DISK_HEADROOM_BYTES
        free_space(monkeypatch, need)
        assert bench.disk_shortfall(tmp_path, TWO_SIZES, n_sdks=2, prune=False) is None
        free_space(monkeypatch, need - 1)
        refusal = bench.disk_shortfall(tmp_path, TWO_SIZES, n_sdks=2, prune=False)
        assert refusal is not None
        assert "--bench-prune-scratch" in refusal
        assert "XT_TMP_DIR" in refusal

    def test_a_scratch_dir_not_made_yet_is_measured_on_its_volume(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # pytest_configure runs the check before the tmp_dir fixture creates
        # the directory.
        probed: list[Path] = []

        def disk_usage(path: Path) -> SimpleNamespace:
            probed.append(Path(path))
            return SimpleNamespace(total=0, used=0, free=10 * GIB)

        monkeypatch.setattr(shutil, "disk_usage", disk_usage)
        small = [Payload("1KiB", 1024)]
        bench.disk_shortfall(tmp_path / "not" / "yet", small, n_sdks=1, prune=True)
        assert probed == [tmp_path]

    def test_a_failure_on_a_full_disk_is_blamed_on_the_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Otherwise ENOSPC from the CLI under measurement reads as that build
        # failing, and the larger cells after it fail the same way.
        free_space(monkeypatch, 4096)
        assert "scratch disk filled up" in (bench.disk_exhausted(tmp_path) or "")
        free_space(monkeypatch, GIB)
        assert bench.disk_exhausted(tmp_path) is None


class TestScratch:
    @staticmethod
    def plaintexts(root: Path) -> dict[str, Path]:
        return {label: touch(root / f"plain-{label}") for label in ("1KiB", "1MiB")}

    def test_pruning_frees_each_file_once_no_cell_needs_it(self, tmp_path: Path):
        control, encrypt, decrypt = cells_for(["go"], parse_payloads("1KiB"))
        plaintexts = self.plaintexts(tmp_path)
        scratch = bench.Scratch(plaintexts, [control, encrypt, decrypt], prune=True)

        output = touch(tmp_path / "out.tdf")
        scratch.release(encrypt, [output])
        scratch.release(encrypt, [])
        assert not output.exists()
        # The decrypt cell still makes its ciphertext from this plaintext.
        assert plaintexts["1KiB"].exists()

        scratch.release(decrypt, [])
        assert not plaintexts["1KiB"].exists()
        assert plaintexts["1MiB"].exists()
        scratch.release(control, [])
        assert not plaintexts["1MiB"].exists()

    def test_without_pruning_nothing_is_deleted(self, tmp_path: Path):
        # A local run keeps its outputs to inspect and its plaintexts to reuse.
        cells = cells_for(["go"], parse_payloads("1KiB"))
        plaintexts = self.plaintexts(tmp_path)
        scratch = bench.Scratch(plaintexts, cells, prune=False)
        output = touch(tmp_path / "out.tdf")
        for cell in cells:
            scratch.release(cell, [output])
        assert output.exists()
        assert all(p.exists() for p in plaintexts.values())


def read_all(paths: dict[str, Path]) -> dict[str, bytes]:
    return {label: p.read_bytes() for label, p in paths.items()}


def subdir(root: Path, name: str) -> Path:
    out = root / name
    out.mkdir()
    return out


def touch(path: Path) -> Path:
    path.write_bytes(b"x")
    return path


class TestBuildArms:
    def arms(self, cwd: Path) -> bench.BenchArms:
        install(cwd, "go", "v0.29.0", "main")
        for v in ("v0.29.0", "main"):
            # `supports` runs the stub, which then answers yes to everything.
            (cwd / "sdk" / "go" / "dist" / v / "cli.sh").chmod(0o755)
        return bench.BenchArms(tdfs.SDK("go", "v0.29.0"), tdfs.SDK("go", "main"))

    def test_arms_are_named_after_their_builds(self, cwd: Path):
        cell = next(c for c in cells_for(["go"]) if not c.control)
        built = bench.build_arms(
            cell,
            self.arms(cwd),
            pt_file=cwd / "pt",
            ct_file=None,
            tmp_dir=cwd,
            attr_values=[],
        )
        assert [a.name for a in built] == ["v0.29.0", "main"]
        assert len({a.invocation.output for a in built}) == 2

    def test_the_control_runs_the_baseline_twice_under_distinct_ids(self, cwd: Path):
        control = next(c for c in cells_for(["go"]) if c.control)
        built = bench.build_arms(
            control,
            self.arms(cwd),
            pt_file=cwd / "pt",
            ct_file=None,
            tmp_dir=cwd,
            attr_values=[],
        )
        assert {a.label for a in built} == {"go@v0.29.0"}
        assert len({a.name for a in built}) == 2, "ids key the sample vectors"
        assert len({a.invocation.output for a in built}) == 2
