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
import zipfile
from pathlib import Path

import pytest

import zipinspect
import zipmutate
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

    def test_rejects_identical_src_and_dest(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)
        with pytest.raises(ValueError, match="distinct src and dest"):
            zipmutate.rewrite(src, src, trailer)

    def test_zip64_offset_forced_with_a_foreign_extra_record_ahead_of_it(
        self, tmp_path: Path
    ):
        """DSPX-4591 finding 2's shape: a foreign TLV first, ZIP64 sentinel
        gated on nothing but the sentinel itself.
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
                    version_needed_to_extract=20,
                )
        assert true_offset is not None

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        cd = zipinspect.central_directory(dest)
        manifest = next(e for e in cd.entries if e.name == "0.manifest.json")
        assert manifest.has_zip64_extra
        assert manifest.uses_zip64_for_offset
        assert manifest.local_header_offset == true_offset

    def test_zip64_sizes_forced_resolve_both_fields(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)
        payload = trailer.entries[0]
        assert payload.name == "0.payload"
        true_csize, true_usize = payload.compressed_size, payload.uncompressed_size
        trailer.entries[0] = dataclasses.replace(payload, force_zip64_sizes=True)

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        entry = zipinspect.central_directory(dest).entries[0]
        assert entry.uses_zip64_for_sizes
        assert entry.compressed_size == true_csize
        assert entry.uncompressed_size == true_usize

    def test_max_length_comment_round_trips(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(trailer, comment=b"c" * 0xFFFF)

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)
        cd = zipinspect.central_directory(dest)
        assert {e.name for e in cd.entries} == {"0.payload", "0.manifest.json"}

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
