"""Offline tests for ``zipmutate.py`` (DSPX-4591 follow-up).

No platform, no SDK, no subprocess -- mirrors ``test_zip64_units.py``'s
framing, and runs in ``check.yml`` on every PR for the same reason: a builder
bug here would otherwise surface only as a mysterious failure in
``test_zip_conformance.py``'s cross-SDK cells.

``zipinspect.py`` is used throughout as the independent oracle: these tests
build something with ``zipmutate`` and then check what comes back out through
the (separately tested) reader, rather than asserting on ``zipmutate``'s own
internals.
"""

import dataclasses
import struct
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import create_autospec

import pytest

import tdfs
import test_zip_conformance as conformance
import zipinspect
import zipmutate
from abac import Attribute
from fixtures.encryption import EncryptFactory
from zipinspect import MalformedZipError

#: The same extended-timestamp shape real writers emit, reused from
#: test_zip_conformance.py's fixture-level constant.
_FOREIGN_EXTRA_TLV = struct.pack("<HH", 0x5455, 5) + b"\x01\x00\x00\x00\x00"


def _ordinary_zip(path: Path) -> Path:
    """A small, real, STORED-entries ZIP -- the shape a TDF actually is."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("0.payload", b"payload-bytes-000")
        z.writestr("0.manifest.json", b'{"hello":"world"}')
    return path


class TestLoadTrailerAndRewrite:
    def test_unmodified_trailer_round_trips_exactly(self, tmp_path: Path):
        """The baseline: rewriting with no changes must reproduce the same
        entries, offsets and sizes zipinspect would report for the original.
        """
        src = _ordinary_zip(tmp_path / "src.zip")
        before = zipinspect.central_directory(src)

        trailer, cd_offset = zipmutate.load_trailer(src)
        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        after = zipinspect.central_directory(dest)
        assert [
            (e.name, e.local_header_offset, e.compressed_size) for e in after.entries
        ] == [
            (e.name, e.local_header_offset, e.compressed_size) for e in before.entries
        ]
        assert after.cd_offset == cd_offset
        zipinspect.assert_offsets_are_consistent(after)
        with zipfile.ZipFile(dest) as z:
            assert all(e.extract_version == 20 for e in z.infolist())

    def test_rejects_identical_src_and_dest(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)
        with pytest.raises(ValueError, match="distinct src and dest"):
            zipmutate.rewrite(src, src, trailer)

    @pytest.mark.parametrize("version_needed", [20, 45], ids=["compatibility", "zip64"])
    def test_zip64_offset_forced_with_a_foreign_extra_record_ahead_of_it(
        self, tmp_path: Path, version_needed: int
    ):
        """The inspector tolerates version 2.0 on a ZIP64 entry, although
        cross-SDK conformance requires a valid version 4.5 declaration.
        """
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        true_offset = None
        for i, entry in enumerate(trailer.entries):
            if entry.name == "0.manifest.json":
                true_offset = entry.local_header_offset

                trailer.entries[i] = dataclasses.replace(
                    entry,
                    force_zip64_offset=True,
                    extra_prefix=_FOREIGN_EXTRA_TLV,
                    version_needed_to_extract=version_needed,
                )
        assert true_offset is not None

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        cd = zipinspect.central_directory(dest)
        manifest = next(e for e in cd.entries if e.name == "0.manifest.json")
        assert manifest.has_zip64_extra
        assert manifest.uses_zip64_for_offset
        assert manifest.local_header_offset == true_offset
        with zipfile.ZipFile(dest) as z:
            assert z.getinfo("0.manifest.json").extract_version == version_needed
            assert z.getinfo("0.payload").extract_version == 20

    def test_zip64_sizes_forced_resolve_both_fields(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)
        payload = trailer.entries[0]
        assert payload.name == "0.payload"
        true_csize, true_usize = payload.compressed_size, payload.uncompressed_size
        trailer.entries[0] = dataclasses.replace(
            payload, force_zip64_sizes=True, version_needed_to_extract=45
        )

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        entry = zipinspect.central_directory(dest).entries[0]
        assert entry.uses_zip64_for_sizes
        assert entry.compressed_size == true_csize
        assert entry.uncompressed_size == true_usize

    @pytest.mark.parametrize("force_zip64", [False, True], ids=["zip", "zip64"])
    @pytest.mark.parametrize("comment_length", [0xFFEB, 0xFFEC, 0xFFFF])
    def test_long_comment_round_trips(
        self, tmp_path: Path, force_zip64: bool, comment_length: int
    ):
        """Exercise the locator at, partly before, and wholly before the
        old EOCD-only search window, with ordinary ZIP controls as well.
        """
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=force_zip64, comment=b"c" * comment_length
        )

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)
        cd = zipinspect.central_directory(dest)
        assert {e.name for e in cd.entries} == {"0.payload", "0.manifest.json"}
        with zipfile.ZipFile(src) as original, zipfile.ZipFile(dest) as rewritten:
            assert rewritten.comment == b"c" * comment_length
            for name in original.namelist():
                assert rewritten.read(name) == original.read(name)

    def test_comment_over_0xffff_is_rejected(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, cd_offset = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(trailer, comment=b"c" * (0xFFFF + 1))
        with pytest.raises(ValueError, match="0xFFFF"):
            trailer.to_bytes(cd_offset)


class TestEntryCountOverride:
    """The declared count is a lie the real CD bytes never agree to back up."""

    def test_plain_eocd_carries_the_overridden_count(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(trailer, entry_count_override=500)
        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        # Read the raw EOCD count field directly: central_directory() would
        # raise before ever reporting it, since the lie is the point.
        tail = dest.read_bytes()[-zipinspect.EOCD_SIZE :]
        assert tail[:4] == zipinspect.EOCD_SIG
        _, total_entries, _, _ = struct.unpack_from("<HHII", tail, 8)
        assert total_entries == 500

        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(dest)

    def test_forced_zip64_eocd_carries_the_overridden_count(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=True, entry_count_override=70_000
        )
        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        data = dest.read_bytes()
        eocd64_at = data.rfind(zipinspect.EOCD64_SIG)
        assert eocd64_at >= 0
        total_this_disk, total = struct.unpack_from("<QQ", data, eocd64_at + 24)
        assert total_this_disk == 70_000
        assert total == 70_000

        eocd_at = data.rfind(zipinspect.EOCD_SIG)
        this_disk_count, total_count = struct.unpack_from("<HH", data, eocd_at + 8)
        assert (this_disk_count, total_count) == (0xFFFF, 0xFFFF)

        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(dest)


class TestCorruptEntryBytes:
    def test_patches_only_the_named_window(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        dest = tmp_path / "dest.zip"
        cd = zipinspect.central_directory(src)
        entry = next(e for e in cd.entries if e.name == "0.payload")
        data_offset = zipinspect.local_file_header_data_offset(src, entry)

        zipmutate.corrupt_entry_bytes(src, dest, "0.payload", at=2, patch=b"PK\x01\x02")

        before = src.read_bytes()
        after = dest.read_bytes()
        assert len(before) == len(after)
        patch_start = data_offset + 2
        patch_end = patch_start + 4
        assert after[patch_start:patch_end] == b"PK\x01\x02"
        assert before[:patch_start] == after[:patch_start]
        assert before[patch_end:] == after[patch_end:]

    def test_rejects_identical_src_and_dest(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        with pytest.raises(ValueError, match="distinct src and dest"):
            zipmutate.corrupt_entry_bytes(src, src, "0.payload", at=0, patch=b"x")

    def test_rejects_an_unknown_entry_name(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        dest = tmp_path / "dest.zip"
        with pytest.raises(ValueError, match="no entry named"):
            zipmutate.corrupt_entry_bytes(src, dest, "does.not.exist", at=0, patch=b"x")

    def test_rejects_a_patch_that_would_run_past_the_entrys_data(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        dest = tmp_path / "dest.zip"
        entry = next(
            e
            for e in zipinspect.central_directory(src).entries
            if e.name == "0.payload"
        )
        with pytest.raises(ValueError, match="outside entry"):
            zipmutate.corrupt_entry_bytes(
                src,
                dest,
                "0.payload",
                at=entry.compressed_size - 1,
                patch=b"too-long-for-the-remaining-space",
            )


@pytest.mark.parametrize("outcome", ["roundtrip", "parser_error", "wrong_plaintext"])
def test_fake_record_conformance_requires_a_faithful_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
):
    """Run the actual conformance case offline: metadata remains readable,
    payload bytes stay intact, and neither failure nor wrong output passes.
    """
    src = _ordinary_zip(tmp_path / "src.zip")
    cd = zipinspect.central_directory(src)
    pt = tmp_path / "plaintext.bin"
    with zipfile.ZipFile(src) as z:
        pt.write_bytes(z.read("0.payload"))
    monkeypatch.setattr(conformance, "_base_container", lambda *args: src)
    sdk = create_autospec(tdfs.SDK, instance=True)

    def decrypt(ct_file: Path, rt_file: Path, container: str) -> None:
        assert container == "ztdf"
        assert ct_file.read_bytes()[: cd.cd_offset] == src.read_bytes()[: cd.cd_offset]
        with zipfile.ZipFile(ct_file) as z:
            assert z.comment.startswith(zipinspect.CEN_SIG)
            (fake_offset,) = struct.unpack_from("<I", z.comment, 42)
            assert fake_offset > ct_file.stat().st_size
            assert z.namelist() == ["0.payload", "0.manifest.json"]
            payload = z.read("0.payload")  # also validates the CRC-32
            assert payload == pt.read_bytes()
        if outcome == "parser_error":
            raise subprocess.CalledProcessError(
                1, "decrypt", stderr=b"ZIP parse failed"
            )
        rt_file.write_bytes(b"wrong" if outcome == "wrong_plaintext" else payload)

    sdk.decrypt.side_effect = decrypt

    def run_case() -> None:
        conformance.test_comment_containing_a_fake_central_directory_record(
            encrypt_sdk=sdk,
            decrypt_sdk=sdk,
            in_focus={sdk},
            zip_conformance_tdf=create_autospec(EncryptFactory, instance=True),
            zip_conformance_pt_file=pt,
            attribute_default_rsa=create_autospec(Attribute, instance=True),
            tmp_path=tmp_path,
        )

    if outcome == "parser_error":
        with pytest.raises(subprocess.CalledProcessError):
            run_case()
    elif outcome == "wrong_plaintext":
        with pytest.raises(AssertionError, match="does not match"):
            run_case()
    else:
        run_case()
    sdk.decrypt.assert_called_once()
