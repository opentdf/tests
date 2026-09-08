"""Offline tests for the ZIP64 boundary machinery (DSPX-4592).

No platform, no SDK, no subprocess. These run in ``check.yml`` on every PR,
because the multi-GiB test they support runs only on a nightly cron -- a
parser bug found six weeks later, in a job nobody watches, on a fixture that
takes twenty minutes to reproduce, is a bad trade against a few seconds here.

The central directories are synthesized byte by byte rather than produced by
``zipfile``. A real 2.1 GiB container is exactly what cannot be built in a
unit test, and ``zipfile`` will not emit a 32-bit field holding a value in
``[2**31, 2**32)`` on request -- which is the encoding under test.
"""

import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import conftest
import zipinspect
from sizes import MEDIUM_BYTES, ZIP64_WINDOW_HIGH, ZIP64_WINDOW_LOW
from zipinspect import ZIP64_SENTINEL_32, MalformedZipError

# --- Synthetic container construction ---------------------------------------


def cen_record(
    name: str,
    *,
    raw_offset: int,
    raw_usize: int = 0,
    raw_csize: int = 0,
    zip64_offset: int | None = None,
    zip64_usize: int | None = None,
    zip64_csize: int | None = None,
) -> bytes:
    """One central-directory header, with an optional ZIP64 extra field.

    ``zip64_*`` values are written into the extra field in APPNOTE 4.5.3's
    fixed order (uncompressed, compressed, offset); pass them only for the
    fields whose 32-bit slot holds the sentinel, which is the same contract
    the parser relies on.
    """
    extra = b""
    body = b""
    if zip64_usize is not None:
        body += struct.pack("<Q", zip64_usize)
    if zip64_csize is not None:
        body += struct.pack("<Q", zip64_csize)
    if zip64_offset is not None:
        body += struct.pack("<Q", zip64_offset)
    if body:
        extra = struct.pack("<HH", zipinspect.ZIP64_EXTRA_ID, len(body)) + body

    encoded = name.encode()
    return (
        b"PK\x01\x02"
        + struct.pack("<HHHHHH", 45, 45, 0, 0, 0, 0)  # versions, flags, method, time
        + struct.pack("<I", 0)  # crc
        + struct.pack("<II", raw_csize, raw_usize)
        + struct.pack("<HHH", len(encoded), len(extra), 0)  # name/extra/comment lens
        + struct.pack("<HHI", 0, 0, 0)  # disk, int attrs, ext attrs
        + struct.pack("<I", raw_offset)
        + encoded
        + extra
    )


def synth_zip(path: Path, records: list[bytes]) -> Path:
    """Write a container that is nothing but a central directory and an EOCD.

    The parser never reads entry data, so leaving it out keeps these tests
    instant while exercising every field it does read.
    """
    cd = b"".join(records)
    cd_offset = 0
    eocd = (
        b"PK\x05\x06"
        + struct.pack("<HHHH", 0, 0, len(records), len(records))
        + struct.pack("<II", len(cd), cd_offset)
        + struct.pack("<H", 0)
    )
    path.write_bytes(cd + eocd)
    return path


def synth_zip64_eocd(
    path: Path,
    records: list[bytes],
    *,
    eocd64_offset_override: int | None = None,
) -> Path:
    """Same, but located through a ZIP64 EOCD record and its locator.

    The 32-bit EOCD carries sentinels, so a reader that stops there sees
    0xFFFF entries at offset 0xFFFFFFFF. This is how a container whose
    central directory sits past 4 GiB has to be read.
    """
    cd = b"".join(records)
    cd_offset = 0
    eocd64 = (
        b"PK\x06\x06"
        + struct.pack("<Q", 44)  # size of this record, less the first 12 bytes
        + struct.pack("<HHII", 45, 45, 0, 0)
        + struct.pack("<QQQQ", len(records), len(records), len(cd), cd_offset)
    )
    eocd64_at = len(cd)
    locator = (
        b"PK\x06\x07"
        + struct.pack("<I", 0)
        + struct.pack("<Q", eocd64_offset_override or eocd64_at)
        + struct.pack("<I", 1)
    )
    eocd = (
        b"PK\x05\x06"
        + struct.pack("<HHHH", 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)
        + struct.pack("<II", 0xFFFFFFFF, 0xFFFFFFFF)
        + struct.pack("<H", 0)
    )
    path.write_bytes(cd + eocd64 + locator + eocd)
    return path


class TestZip64Selection:
    @pytest.mark.parametrize(
        ("item_size", "expected"), [("small", False), ("medium", True)]
    )
    def test_mixed_session_uses_each_items_size(self, item_size: str, expected: bool):
        item = cast(
            pytest.Item,
            SimpleNamespace(callspec=SimpleNamespace(params={"size": item_size})),
        )

        assert (
            conftest._item_exercises_zip64_window(item, ["small", "medium"]) is expected
        )

    def test_item_without_size_uses_session_selection(self):
        item = cast(
            pytest.Item,
            SimpleNamespace(callspec=SimpleNamespace(params={"container": "ztdf"})),
        )

        assert conftest._item_exercises_zip64_window(item, ["small", "medium"])
        assert not conftest._item_exercises_zip64_window(item, ["small"])


# --- zipinspect.py -----------------------------------------------------------


class TestCentralDirectory:
    def test_reads_a_real_zip(self, tmp_path: Path):
        """Agreement with zipfile on an ordinary container, as a sanity floor."""
        p = tmp_path / "ordinary.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("0.payload", b"a" * 4096)
            z.writestr("0.manifest.json", b"{}")

        entries = zipinspect.central_directory(p)
        assert [e.name for e in entries] == ["0.payload", "0.manifest.json"]
        with zipfile.ZipFile(p) as z:
            expected = {i.filename: i.header_offset for i in z.infolist()}
        assert {e.name: e.local_header_offset for e in entries} == expected

    def test_local_header_zip64_is_not_mistaken_for_central_directory_zip64(
        self, tmp_path: Path
    ):
        """``force_zip64`` is a local-header decision and must not be read as a CD one.

        The two are independent: a writer can emit the ZIP64 extra field in
        the local header while the central directory's values still fit in 32
        bits, which is exactly what this produces. Reporting
        ``has_zip64_extra`` for it would make the conformance assertions think
        a writer had opted into ZIP64 for a field it had not.
        """
        p = tmp_path / "z64-local.zip"
        with zipfile.ZipFile(p, "w") as z:
            with z.open("0.payload", "w", force_zip64=True) as f:
                f.write(b"b" * 8192)

        (entry,) = zipinspect.central_directory(p)
        assert entry.uncompressed_size == 8192
        assert not entry.has_zip64_extra
        assert not entry.uses_zip64_for_sizes

    def test_reads_a_zip64_end_of_central_directory(self, tmp_path: Path):
        """When the EOCD holds sentinels, the real values come from the ZIP64 EOCD.

        A container whose central directory starts past 4 GiB -- which the
        'large' size produces -- can only be located this way, so the branch
        is on the path for the very sizes this module exists to cover.
        """
        records = [
            cen_record("0.payload", raw_offset=0),
            cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES),
        ]
        p = synth_zip64_eocd(tmp_path / "z64-eocd.zip", records)
        entries = zipinspect.central_directory(p)
        assert [e.name for e in entries] == ["0.payload", "0.manifest.json"]
        assert entries[1].raw_local_header_offset == MEDIUM_BYTES

    def test_rejects_a_locator_pointing_at_nothing(self, tmp_path: Path):
        p = synth_zip64_eocd(
            tmp_path / "bad-locator.zip",
            [cen_record("0.payload", raw_offset=0)],
            eocd64_offset_override=1,
        )
        with pytest.raises(MalformedZipError, match="zip64 locator"):
            zipinspect.central_directory(p)

    def test_raw_value_in_the_window_is_preserved(self, tmp_path: Path):
        """A 32-bit field holding a real 2.1 GiB value must not be normalised away.

        This is the go-writer shape: legal APPNOTE, and the input that a
        sign-extending reader mishandles. If the parser resolved it through
        the ZIP64 path the test would lose the ability to tell the two
        encodings apart.
        """
        p = synth_zip(
            tmp_path / "window.zip",
            [
                cen_record("0.payload", raw_offset=0, raw_usize=MEDIUM_BYTES),
                cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES + 64),
            ],
        )
        entries = zipinspect.central_directory(p)
        manifest = entries[1]
        assert manifest.raw_local_header_offset == MEDIUM_BYTES + 64
        assert manifest.local_header_offset == MEDIUM_BYTES + 64
        assert not manifest.has_zip64_extra
        assert not manifest.uses_zip64_for_offset

    def test_signed_read_of_a_windowed_offset_goes_negative(self, tmp_path: Path):
        """The defect itself, reproduced arithmetically.

        java-sdk's pre-#393 ``readInt()`` widens this field with a signed
        read. Anything at or above 2**31 comes back negative and the
        subsequent seek fails or lands on nonsense.
        """
        p = synth_zip(
            tmp_path / "signed.zip",
            [cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES)],
        )
        (entry,) = zipinspect.central_directory(p)
        assert entry.signed_read_of_offset() < 0
        assert entry.signed_read_of_offset() == MEDIUM_BYTES - ZIP64_WINDOW_HIGH

    def test_signed_read_is_harmless_below_the_window(self, tmp_path: Path):
        """Below 2**31 the two reads agree, which is why smaller payloads miss this."""
        offset = ZIP64_WINDOW_LOW - 1
        p = synth_zip(
            tmp_path / "safe.zip", [cen_record("0.manifest.json", raw_offset=offset)]
        )
        (entry,) = zipinspect.central_directory(p)
        assert entry.signed_read_of_offset() == offset

    def test_sentinel_resolves_through_the_extra_field(self, tmp_path: Path):
        """The web-sdk shape: always ZIP64, so the 32-bit field is 0xFFFFFFFF."""
        true_offset = 6 * 2**30
        p = synth_zip(
            tmp_path / "sentinel.zip",
            [
                cen_record(
                    "0.manifest.json",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=true_offset,
                )
            ],
        )
        (entry,) = zipinspect.central_directory(p)
        assert entry.local_header_offset == true_offset
        assert entry.uses_zip64_for_offset
        assert entry.has_zip64_extra

    def test_rejects_a_file_with_no_eocd(self, tmp_path: Path):
        p = tmp_path / "junk.bin"
        p.write_bytes(b"not a zip at all")
        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(p)

    def test_rejects_a_sentinel_with_no_zip64_extra(self, tmp_path: Path):
        """A sentinel with nothing to resolve it is malformed, not a real value.

        Falling back to the raw 0xFFFFFFFF here would land inside
        ``[2**31, 2**32)`` and get reported as an ordinary in-window value,
        which is exactly the mislabeling this module exists to avoid.
        """
        p = synth_zip(
            tmp_path / "sentinel-no-extra.zip",
            [cen_record("0.manifest.json", raw_offset=ZIP64_SENTINEL_32)],
        )
        with pytest.raises(MalformedZipError, match="local header offset"):
            zipinspect.central_directory(p)


class TestConformanceAssertions:
    def test_above_4gib_without_the_sentinel_fails(self, tmp_path: Path):
        """A 32-bit field cannot hold this value, so omitting the sentinel is a defect."""
        p = synth_zip(
            tmp_path / "bad.zip",
            [
                cen_record(
                    "0.manifest.json",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=5 * 2**30,
                )
            ],
        )
        entries = zipinspect.central_directory(p)
        # Rewrite the entry to claim a >4 GiB offset with no ZIP64 encoding,
        # which is the state a non-conformant writer would leave behind.
        broken = [
            zipinspect.CentralDirectoryEntry(
                name="0.manifest.json",
                raw_compressed_size=0,
                raw_uncompressed_size=0,
                raw_local_header_offset=12345,
                compressed_size=0,
                uncompressed_size=0,
                local_header_offset=5 * 2**30,
                has_zip64_extra=False,
            )
        ]
        zipinspect.assert_zip64_above_4gib(entries)  # the conformant one passes
        with pytest.raises(AssertionError, match="ZIP64 sentinel"):
            zipinspect.assert_zip64_above_4gib(broken)

    def test_above_4gib_uncompressed_size_without_the_sentinel_fails(self):
        """The size branches had no test of their own; the offset test above doesn't touch them."""
        broken = [
            zipinspect.CentralDirectoryEntry(
                name="0.payload",
                raw_compressed_size=0,
                raw_uncompressed_size=12345,
                raw_local_header_offset=0,
                compressed_size=0,
                uncompressed_size=5 * 2**30,
                local_header_offset=0,
                has_zip64_extra=False,
            )
        ]
        with pytest.raises(AssertionError, match="ZIP64 sentinel"):
            zipinspect.assert_zip64_above_4gib(broken)

    def test_above_4gib_compressed_size_without_the_sentinel_fails(self):
        """Compressed size must be checked against its own raw field, not the uncompressed one.

        A TDF is STORED, not DEFLATEd, so the compressed field is at least as
        likely to cross 2**32 as the uncompressed one -- but a check that only
        looks at ``uses_zip64_for_sizes`` (an OR over both raw fields) would
        let a correctly-sentineled uncompressed field paper over a broken
        compressed one. This entry has exactly that shape.
        """
        broken = [
            zipinspect.CentralDirectoryEntry(
                name="0.payload",
                raw_compressed_size=12345,
                raw_uncompressed_size=ZIP64_SENTINEL_32,
                raw_local_header_offset=0,
                compressed_size=5 * 2**30,
                uncompressed_size=5 * 2**30,
                local_header_offset=0,
                has_zip64_extra=True,
            )
        ]
        with pytest.raises(AssertionError, match="compressed-size field"):
            zipinspect.assert_zip64_above_4gib(broken)

    def test_above_4gib_sizes_with_the_sentinel_pass(self, tmp_path: Path):
        """The positive counterpart: both size fields correctly ZIP64-encoded."""
        p = synth_zip(
            tmp_path / "big-sizes.zip",
            [
                cen_record(
                    "0.payload",
                    raw_offset=0,
                    raw_usize=ZIP64_SENTINEL_32,
                    raw_csize=ZIP64_SENTINEL_32,
                    zip64_usize=5 * 2**30,
                    zip64_csize=5 * 2**30 + 1,
                )
            ],
        )
        entries = zipinspect.central_directory(p)
        zipinspect.assert_zip64_above_4gib(entries)

    def test_window_entries_are_reported_for_either_encoding(self, tmp_path: Path):
        """Both a raw value and a sentinel in the band are legal and both are listed."""
        p = synth_zip(
            tmp_path / "mixed.zip",
            [
                cen_record("raw", raw_offset=MEDIUM_BYTES),
                cen_record(
                    "sentinel",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=MEDIUM_BYTES + 1024,
                ),
                cen_record("small", raw_offset=1024),
            ],
        )
        entries = zipinspect.central_directory(p)
        assert {e.name for e in zipinspect.entries_in_window(entries)} == {
            "raw",
            "sentinel",
        }

    def test_only_raw_window_values_exercise_signed_read(self, tmp_path: Path):
        """The sentinel redirects to ZIP64 data and is not a signed read risk."""
        p = synth_zip(
            tmp_path / "mixed.zip",
            [
                cen_record("raw", raw_offset=MEDIUM_BYTES),
                cen_record(
                    "sentinel",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=MEDIUM_BYTES + 1024,
                ),
            ],
        )
        entries = zipinspect.central_directory(p)
        assert {
            e.name for e in zipinspect.entries_with_raw_values_in_window(entries)
        } == {"raw"}

    def test_describe_includes_the_numbers_needed_to_debug(self, tmp_path: Path):
        p = synth_zip(
            tmp_path / "d.zip", [cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES)]
        )
        text = zipinspect.describe(zipinspect.central_directory(p))
        assert "0.manifest.json" in text
        assert str(MEDIUM_BYTES) in text
