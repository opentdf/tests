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
    zip64_disk_start: int | None = None,
    extra_prefix: bytes = b"",
    zip64_extra_len_override: int | None = None,
) -> bytes:
    """One central-directory header, with an optional ZIP64 extra field.

    ``zip64_*`` values are written into the extra field in APPNOTE 4.5.3's
    fixed order (uncompressed, compressed, offset); pass them only for the
    fields whose 32-bit slot holds the sentinel, which is the same contract
    the parser relies on.

    ``extra_prefix`` puts another extra-field record ahead of the ZIP64 one,
    and ``zip64_extra_len_override`` lies about the ZIP64 record's length.
    Both exist to build inputs a conformant writer would not: the first is
    what real writers actually emit, the second is the misparse under test.
    """
    extra = b""
    body = b""
    if zip64_usize is not None:
        body += struct.pack("<Q", zip64_usize)
    if zip64_csize is not None:
        body += struct.pack("<Q", zip64_csize)
    if zip64_offset is not None:
        body += struct.pack("<Q", zip64_offset)
    if zip64_disk_start is not None:
        body += struct.pack("<I", zip64_disk_start)
    if body or zip64_extra_len_override is not None:
        declared = (
            len(body) if zip64_extra_len_override is None else zip64_extra_len_override
        )
        extra = struct.pack("<HH", zipinspect.ZIP64_EXTRA_ID, declared) + body
    extra = extra_prefix + extra

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


def _write_at(path: Path, cd_offset: int, trailer: bytes) -> Path:
    """Write ``trailer`` at ``cd_offset``, leaving the gap before it sparse.

    The gap stands in for entry data the parser never reads. Making it a hole
    rather than real bytes is what lets these tests build a container whose
    central directory genuinely sits past 4 GiB -- ``file_size`` and
    ``cd_offset`` are then real ground truth for the consistency assertions,
    at a cost of one filesystem block. Sparse files are supported on both APFS
    and ext4, which is macOS dev boxes and the CI runners.
    """
    with path.open("wb") as f:
        if cd_offset:
            f.truncate(cd_offset)
            f.seek(cd_offset)
        f.write(trailer)
    return path


def synth_zip(path: Path, records: list[bytes], *, cd_offset: int = 0) -> Path:
    """Write a container that is nothing but a central directory and an EOCD.

    The parser never reads entry data, so leaving it out keeps these tests
    instant while exercising every field it does read. Pass ``cd_offset`` when
    the test needs the directory to sit at a plausible place after the entry
    data, which the consistency assertions check against.
    """
    if cd_offset >= zipinspect.ZIP64_SENTINEL_32:
        raise ValueError(
            f"cd_offset {cd_offset} does not fit the 32-bit EOCD; a directory "
            "this far into the file has to be located through the ZIP64 EOCD, "
            "so use synth_zip64_eocd"
        )
    cd = b"".join(records)
    eocd = (
        b"PK\x05\x06"
        + struct.pack("<HHHH", 0, 0, len(records), len(records))
        + struct.pack("<II", len(cd), cd_offset)
        + struct.pack("<H", 0)
    )
    return _write_at(path, cd_offset, cd + eocd)


def synth_zip64_eocd(
    path: Path,
    records: list[bytes],
    *,
    cd_offset: int = 0,
    eocd64_offset_override: int | None = None,
) -> Path:
    """Same, but located through a ZIP64 EOCD record and its locator.

    The 32-bit EOCD carries sentinels, so a reader that stops there sees
    0xFFFF entries at offset 0xFFFFFFFF. This is how a container whose
    central directory sits past 4 GiB has to be read.
    """
    cd = b"".join(records)
    eocd64 = (
        b"PK\x06\x06"
        + struct.pack("<Q", 44)  # size of this record, less the first 12 bytes
        + struct.pack("<HHII", 45, 45, 0, 0)
        + struct.pack("<QQQQ", len(records), len(records), len(cd), cd_offset)
    )
    eocd64_at = cd_offset + len(cd)
    locator = (
        b"PK\x06\x07"
        + struct.pack("<I", 0)
        + struct.pack(
            "<Q",
            eocd64_at if eocd64_offset_override is None else eocd64_offset_override,
        )
        + struct.pack("<I", 1)
    )
    eocd = (
        b"PK\x05\x06"
        + struct.pack("<HHHH", 0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF)
        + struct.pack("<II", 0xFFFFFFFF, 0xFFFFFFFF)
        + struct.pack("<H", 0)
    )
    return _write_at(path, cd_offset, cd + eocd64 + locator + eocd)


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


class _FakeConfig:
    """The three things ``pytest_collection_modifyitems`` asks of a config.

    A real ``pytest.Config`` would need a real session; the hook only reads
    two options, caches the resolved sizes in the stash, and calls one hook.
    """

    def __init__(self, *, sizes: list[str] | None = None, bench: bool = False):
        self.stash = pytest.Stash()
        self.deselected: list[pytest.Item] = []
        self._options: dict[str, object] = {
            "--bench": bench,
            "--sizes": sizes,
            "--large": False,
        }
        self.hook = SimpleNamespace(
            pytest_deselected=lambda items: self.deselected.extend(items)
        )

    def getoption(self, name: str, default: object = None) -> object:
        return self._options.get(name, default)


def _fake_item(name: str, *, marker: str | None = None, size: str | None = None):
    params = {} if size is None else {"size": size}
    return cast(
        pytest.Item,
        SimpleNamespace(
            name=name,
            callspec=SimpleNamespace(params=params),
            get_closest_marker=lambda want, m=marker: want if want == m else None,
        ),
    )


def _run_filter(config: _FakeConfig, items: list[pytest.Item]) -> list[str]:
    conftest.pytest_collection_modifyitems(cast(pytest.Config, config), items)
    return [i.name for i in items]


class TestZip64Deselection:
    """The collection filter itself, not just the predicate it delegates to."""

    def test_a_default_run_drops_the_zip64_cells(self):
        items = [_fake_item("zip64[small]", marker="zip64", size="small")]
        config = _FakeConfig()

        assert _run_filter(config, items) == []
        assert [i.name for i in config.deselected] == ["zip64[small]"]

    def test_a_medium_run_keeps_them(self):
        items = [_fake_item("zip64[medium]", marker="zip64", size="medium")]
        config = _FakeConfig(sizes=["medium"])

        assert _run_filter(config, items) == ["zip64[medium]"]
        assert config.deselected == []

    def test_a_mixed_run_keeps_only_the_cells_that_reach_the_window(self):
        """The reason the filter is per-item rather than per-session.

        ``--sizes small,medium`` collects both arms of every size-parametrized
        zip64 test. Judging by the session would keep the 128-byte arm, which
        passes green without touching the code path under test.
        """
        items = [
            _fake_item("zip64[small]", marker="zip64", size="small"),
            _fake_item("zip64[medium]", marker="zip64", size="medium"),
            _fake_item("roundtrip[small]", size="small"),
        ]
        config = _FakeConfig(sizes=["small", "medium"])

        assert _run_filter(config, items) == ["zip64[medium]", "roundtrip[small]"]
        assert [i.name for i in config.deselected] == ["zip64[small]"]

    def test_benchmarks_need_their_own_opt_in(self):
        """A medium run is not a benchmark run; the two markers are independent."""
        items = [
            _fake_item("bench", marker="benchmark", size="medium"),
            _fake_item("zip64", marker="zip64", size="medium"),
        ]
        config = _FakeConfig(sizes=["medium"])

        assert _run_filter(config, items) == ["zip64"]
        assert [i.name for i in config.deselected] == ["bench"]


# --- zipinspect.py -----------------------------------------------------------


class TestCentralDirectory:
    def test_reads_a_real_zip(self, tmp_path: Path):
        """Agreement with zipfile on an ordinary container, as a sanity floor."""
        p = tmp_path / "ordinary.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("0.payload", b"a" * 4096)
            z.writestr("0.manifest.json", b"{}")

        cd = zipinspect.central_directory(p)
        assert [e.name for e in cd.entries] == ["0.payload", "0.manifest.json"]
        with zipfile.ZipFile(p) as z:
            expected = {i.filename: i.header_offset for i in z.infolist()}
        assert {e.name: e.local_header_offset for e in cd.entries} == expected
        # The ground truth the consistency assertions need, against a
        # container built by something other than this file's helpers.
        assert cd.file_size == p.stat().st_size
        assert cd.cd_offset + cd.cd_size < cd.file_size
        zipinspect.assert_offsets_are_consistent(cd)

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

        (entry,) = zipinspect.central_directory(p).entries
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
        cd = zipinspect.central_directory(p)
        assert [e.name for e in cd.entries] == ["0.payload", "0.manifest.json"]
        assert cd.entries[1].raw_local_header_offset == MEDIUM_BYTES

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
        manifest = zipinspect.central_directory(p).entries[1]
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
        (entry,) = zipinspect.central_directory(p).entries
        assert entry.signed_read_of_offset() < 0
        assert entry.signed_read_of_offset() == MEDIUM_BYTES - ZIP64_WINDOW_HIGH

    def test_signed_read_is_harmless_below_the_window(self, tmp_path: Path):
        """Below 2**31 the two reads agree, which is why smaller payloads miss this."""
        offset = ZIP64_WINDOW_LOW - 1
        p = synth_zip(
            tmp_path / "safe.zip", [cen_record("0.manifest.json", raw_offset=offset)]
        )
        (entry,) = zipinspect.central_directory(p).entries
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
        (entry,) = zipinspect.central_directory(p).entries
        assert entry.local_header_offset == true_offset
        assert entry.uses_zip64_for_offset
        assert entry.has_zip64_extra

    def test_each_zip64_value_lands_in_its_own_field(self, tmp_path: Path):
        """The extra field is positional, so a transposed decode must be caught.

        Every value here is distinct and none is a round number: if the
        uncompressed and compressed slots were swapped, or the offset read
        from the wrong one, the numbers below would not match. An earlier
        version of this suite asserted only that parsing *succeeded*, and a
        deliberate transposition of the two size fields kept every test green.
        """
        p = synth_zip(
            tmp_path / "all-three.zip",
            [
                cen_record(
                    "0.payload",
                    raw_offset=ZIP64_SENTINEL_32,
                    raw_usize=ZIP64_SENTINEL_32,
                    raw_csize=ZIP64_SENTINEL_32,
                    zip64_usize=5 * 2**30 + 11,
                    zip64_csize=5 * 2**30 + 22,
                    zip64_offset=5 * 2**30 + 33,
                )
            ],
        )
        (entry,) = zipinspect.central_directory(p).entries
        assert entry.uncompressed_size == 5 * 2**30 + 11
        assert entry.compressed_size == 5 * 2**30 + 22
        assert entry.local_header_offset == 5 * 2**30 + 33

    def test_skips_a_foreign_extra_field_record(self, tmp_path: Path):
        """A ZIP64 record after an unrelated one must still be found.

        Real writers put an extended-timestamp record (0x5455) in the extra
        field, so the skip-and-continue path is the common case in the wild
        rather than an edge case.
        """
        timestamp = struct.pack("<HH", 0x5455, 5) + b"\x01\x00\x00\x00\x00"
        p = synth_zip(
            tmp_path / "foreign-extra.zip",
            [
                cen_record(
                    "0.manifest.json",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=7 * 2**30,
                    extra_prefix=timestamp,
                )
            ],
        )
        (entry,) = zipinspect.central_directory(p).entries
        assert entry.local_header_offset == 7 * 2**30
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


class TestMalformedExtraField:
    """The ZIP64 extra field is positional, so its length is load-bearing."""

    def test_rejects_more_values_than_the_sentinels_call_for(self, tmp_path: Path):
        """Sentinel on the offset alone, but all three values written.

        This is the misparse that motivated the length check. Decoding
        positionally regardless would take the *uncompressed size* out of the
        first slot and report it as the local header offset -- a plausible
        number, off by the size of the payload, with nothing to flag it.
        """
        p = synth_zip(
            tmp_path / "over-long-extra.zip",
            [
                cen_record(
                    "0.manifest.json",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_usize=MEDIUM_BYTES,
                    zip64_csize=MEDIUM_BYTES,
                    zip64_offset=MEDIUM_BYTES + 128,
                )
            ],
        )
        with pytest.raises(MalformedZipError, match="ZIP64 extra field is 24 bytes"):
            zipinspect.central_directory(p)

    def test_rejects_fewer_values_than_the_sentinels_call_for(self, tmp_path: Path):
        """Two sentinels, one value. The second read would run off the end."""
        p = synth_zip(
            tmp_path / "short-extra.zip",
            [
                cen_record(
                    "0.payload",
                    raw_offset=ZIP64_SENTINEL_32,
                    raw_usize=ZIP64_SENTINEL_32,
                    zip64_usize=5 * 2**30,
                )
            ],
        )
        with pytest.raises(MalformedZipError, match="ZIP64 extra field is 8 bytes"):
            zipinspect.central_directory(p)

    def test_rejects_an_empty_zip64_record(self, tmp_path: Path):
        """A 0x0001 record with no body carries no information.

        Accepting it would set ``has_zip64_extra`` on an entry that resolves
        nothing, so the reports would claim the writer opted into ZIP64 while
        every value still came from the 32-bit fields.
        """
        p = synth_zip(
            tmp_path / "empty-extra.zip",
            [cen_record("0.payload", raw_offset=0, zip64_extra_len_override=0)],
        )
        with pytest.raises(MalformedZipError, match="ZIP64 extra field is 0 bytes"):
            zipinspect.central_directory(p)

    def test_rejects_a_record_claiming_more_than_remains(self, tmp_path: Path):
        """A length past the end of the extra field is truncation, not absence."""
        p = synth_zip(
            tmp_path / "overrun-extra.zip",
            [
                cen_record(
                    "0.manifest.json",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=5 * 2**30,
                    zip64_extra_len_override=64,
                )
            ],
        )
        with pytest.raises(MalformedZipError, match="claims 64 bytes"):
            zipinspect.central_directory(p)

    def test_tolerates_the_trailing_disk_start_field(self, tmp_path: Path):
        """APPNOTE 4.5.3 allows a 4-byte disk-start value after the 64-bit ones.

        It is the one length the check has to be lax about, so it gets a test
        rather than being left to the reviewer to notice in the ``+ 4``.
        """
        p = synth_zip(
            tmp_path / "disk-start.zip",
            [
                cen_record(
                    "0.manifest.json",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=5 * 2**30,
                    zip64_disk_start=0,
                )
            ],
        )
        (entry,) = zipinspect.central_directory(p).entries
        assert entry.local_header_offset == 5 * 2**30
        assert entry.has_zip64_extra


class TestTruncatedContainers:
    """A malformed container must arrive as MalformedZipError, not struct.error.

    These inputs are SDK output and hand-built fixtures, so hitting one is an
    expected case. A bare ``struct.error`` from the middle of the parse names
    neither the file nor the field and reads like a bug in the test harness.
    """

    def test_truncated_eocd(self, tmp_path: Path):
        p = synth_zip(tmp_path / "t.zip", [cen_record("a", raw_offset=0)])
        p.write_bytes(p.read_bytes()[:-6])
        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(p)

    def test_truncated_central_directory_record(self, tmp_path: Path):
        record = cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES)
        p = tmp_path / "short-cen.zip"
        cd = record[:20]
        eocd = (
            b"PK\x05\x06"
            + struct.pack("<HHHH", 0, 0, 1, 1)
            + struct.pack("<II", len(cd), 0)
            + struct.pack("<H", 0)
        )
        p.write_bytes(cd + eocd)
        with pytest.raises(MalformedZipError, match="truncated"):
            zipinspect.central_directory(p)

    def test_central_directory_record_with_a_name_past_the_end(self, tmp_path: Path):
        """A plausible header whose variable-length fields overrun the buffer."""
        record = cen_record("0.manifest.json", raw_offset=0)
        # Claim a 4096-byte name where 15 bytes were written.
        record = record[:28] + struct.pack("<H", 4096) + record[30:]
        p = tmp_path / "long-name.zip"
        eocd = (
            b"PK\x05\x06"
            + struct.pack("<HHHH", 0, 0, 1, 1)
            + struct.pack("<II", len(record), 0)
            + struct.pack("<H", 0)
        )
        p.write_bytes(record + eocd)
        with pytest.raises(MalformedZipError, match="only .* remain"):
            zipinspect.central_directory(p)

    def test_zip64_locator_pointing_past_the_end_of_the_file(self, tmp_path: Path):
        """The dangerous one: an unchecked read here drives an unbounded one.

        A short read leaves garbage in ``cd_size``, and the parser would then
        ask for that many bytes of central directory.
        """
        p = synth_zip64_eocd(
            tmp_path / "eocd64-past-end.zip",
            [cen_record("0.payload", raw_offset=0)],
            eocd64_offset_override=2**40,
        )
        with pytest.raises(MalformedZipError, match="past the end"):
            zipinspect.central_directory(p)

    def test_central_directory_extending_past_the_end_of_the_file(self, tmp_path: Path):
        """A cd_size larger than the file must be refused before the read."""
        p = tmp_path / "cd-past-end.zip"
        eocd = (
            b"PK\x05\x06"
            + struct.pack("<HHHH", 0, 0, 1, 1)
            + struct.pack("<II", 2**31, 0)
            + struct.pack("<H", 0)
        )
        p.write_bytes(eocd)
        with pytest.raises(MalformedZipError, match="past the end"):
            zipinspect.central_directory(p)


class TestConformanceAssertions:
    def test_a_container_past_4gib_must_use_zip64(self, tmp_path: Path):
        """The check that can actually fail on writer output.

        A container this size has either a local header past 4 GiB or an entry
        whose data crosses it; both require the sentinel. This one claims
        neither, which is the shape of a writer that never learned ZIP64.

        The container is still located through a ZIP64 EOCD, because a central
        directory this far in cannot be addressed any other way -- the point is
        that no *entry* uses ZIP64, which is what the assertion checks.
        """
        cd_offset = 5 * 2**30
        p = synth_zip64_eocd(
            tmp_path / "big-no-zip64.zip",
            [cen_record("0.payload", raw_offset=0, raw_usize=1024, raw_csize=1024)],
            cd_offset=cd_offset,
        )
        cd = zipinspect.central_directory(p)
        assert cd.file_size > ZIP64_WINDOW_HIGH
        with pytest.raises(AssertionError, match="not one of its 1 entries"):
            zipinspect.assert_zip64_above_4gib(cd)

    def test_a_container_past_4gib_with_zip64_passes(self, tmp_path: Path):
        cd_offset = 5 * 2**30
        p = synth_zip64_eocd(
            tmp_path / "big-with-zip64.zip",
            [
                cen_record(
                    "0.payload",
                    raw_offset=ZIP64_SENTINEL_32,
                    zip64_offset=cd_offset - 1024,
                )
            ],
            cd_offset=cd_offset,
        )
        zipinspect.assert_zip64_above_4gib(zipinspect.central_directory(p))

    def test_a_container_below_4gib_is_not_required_to_use_zip64(self, tmp_path: Path):
        """The 2-4 GiB band has latitude; only above 2**32 is ZIP64 mandatory."""
        p = synth_zip(
            tmp_path / "medium.zip",
            [cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES)],
            cd_offset=MEDIUM_BYTES + 128,
        )
        zipinspect.assert_zip64_above_4gib(zipinspect.central_directory(p))

    def test_an_offset_truncated_mod_2_32_is_caught(self, tmp_path: Path):
        """The defect ``assert_zip64_above_4gib`` structurally cannot see.

        A writer that drops the high bits of a 5 GiB offset emits a value that
        parses perfectly and looks like an ordinary small offset. What gives
        it away is that the entry's data would then have to end well after the
        central directory starts.
        """
        true_offset = 5 * 2**30
        cd_offset = true_offset + 4096
        p = synth_zip64_eocd(
            tmp_path / "truncated-offset.zip",
            [
                cen_record(
                    "0.payload",
                    raw_offset=true_offset % ZIP64_WINDOW_HIGH,
                    raw_usize=ZIP64_SENTINEL_32,
                    raw_csize=ZIP64_SENTINEL_32,
                    zip64_usize=true_offset,
                    zip64_csize=true_offset,
                )
            ],
            cd_offset=cd_offset,
        )
        cd = zipinspect.central_directory(p)
        with pytest.raises(AssertionError, match="truncated mod 2\\*\\*32"):
            zipinspect.assert_offsets_are_consistent(cd)

    def test_an_entry_at_or_after_the_central_directory_is_caught(self, tmp_path: Path):
        p = synth_zip(
            tmp_path / "entry-after-cd.zip",
            [cen_record("0.payload", raw_offset=9000)],
            cd_offset=4096,
        )
        cd = zipinspect.central_directory(p)
        with pytest.raises(AssertionError, match="at or after the central directory"):
            zipinspect.assert_offsets_are_consistent(cd)

    def test_two_entries_claiming_one_offset_are_caught(self, tmp_path: Path):
        p = synth_zip(
            tmp_path / "dup-offset.zip",
            [
                cen_record("0.payload", raw_offset=512),
                cen_record("0.manifest.json", raw_offset=512),
            ],
            cd_offset=4096,
        )
        cd = zipinspect.central_directory(p)
        with pytest.raises(AssertionError, match="both claim a local header"):
            zipinspect.assert_offsets_are_consistent(cd)

    def test_a_well_formed_container_is_consistent(self, tmp_path: Path):
        p = synth_zip(
            tmp_path / "fine.zip",
            [
                cen_record("0.payload", raw_offset=0, raw_csize=2048),
                cen_record("0.manifest.json", raw_offset=2100, raw_csize=64),
            ],
            cd_offset=4096,
        )
        zipinspect.assert_offsets_are_consistent(zipinspect.central_directory(p))

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
        entries = zipinspect.central_directory(p).entries
        assert {e.name for e in zipinspect.entries_in_window(entries)} == {
            "raw",
            "sentinel",
        }

    def test_a_compressed_size_in_the_window_is_reported(self, tmp_path: Path):
        """The compressed size is a 32-bit field too, and was being skipped."""
        p = synth_zip(
            tmp_path / "csize-window.zip",
            [cen_record("0.payload", raw_offset=0, raw_csize=MEDIUM_BYTES)],
        )
        entries = zipinspect.central_directory(p).entries
        assert [e.name for e in zipinspect.entries_in_window(entries)] == ["0.payload"]

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
        entries = zipinspect.central_directory(p).entries
        assert {
            e.name for e in zipinspect.entries_with_raw_values_in_window(entries)
        } == {"raw"}

    def test_describe_includes_the_numbers_needed_to_debug(self, tmp_path: Path):
        p = synth_zip(
            tmp_path / "d.zip", [cen_record("0.manifest.json", raw_offset=MEDIUM_BYTES)]
        )
        text = zipinspect.describe(zipinspect.central_directory(p).entries)
        assert "0.manifest.json" in text
        assert str(MEDIUM_BYTES) in text
