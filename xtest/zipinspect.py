"""Raw ZIP central-directory reader, for asserting on the *encoding*.

``zipfile`` cannot be used for this. It normalises ZIP64 away -- ask it for an
entry's header offset and you get the resolved value, whether that came from
the 32-bit field or from a ZIP64 extra field. The distinction it discards is
precisely what these tests are about, so the bytes are parsed here instead.

Only the tail of the file plus the central directory is read, so this stays
cheap on a multi-GiB container.

Reference: APPNOTE.TXT 4.3.12 (central directory header), 4.3.14 (zip64 end of
central directory record), 4.3.15 (zip64 end of central directory locator),
4.3.16 (end of central directory), 4.5.3 (the ZIP64 extended information extra
field).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from sizes import ZIP64_WINDOW_HIGH, in_zip64_window

# Signatures, little-endian.
_CEN_SIG = b"PK\x01\x02"
_EOCD_SIG = b"PK\x05\x06"
_EOCD64_SIG = b"PK\x06\x06"
_EOCD64_LOCATOR_SIG = b"PK\x06\x07"

#: Written into a 32-bit field to mean "the real value is in the ZIP64 extra
#: field". APPNOTE 4.4.1.4.
ZIP64_SENTINEL_32 = 0xFFFFFFFF

#: Header ID of the ZIP64 extended information extra field. APPNOTE 4.5.3.
ZIP64_EXTRA_ID = 0x0001

_EOCD_SIZE = 22
_EOCD64_SIZE = 56
_EOCD64_LOCATOR_SIZE = 20
#: Bytes of a central-directory record before the variable-length name.
_CEN_FIXED_SIZE = 46
#: A ZIP comment is a 16-bit length, so the EOCD cannot start further back
#: than this from the end of the file.
_MAX_EOCD_SEARCH = _EOCD_SIZE + 0xFFFF


class MalformedZipError(Exception):
    """The container is not a ZIP we can parse at all."""


@dataclass(frozen=True, slots=True)
class CentralDirectoryEntry:
    """One central-directory record, with the raw fields kept alongside.

    ``raw_*`` are the 32-bit values exactly as they appear on the wire.
    The unprefixed attributes are the resolved values, ZIP64 extra field
    applied where present. Comparing the two is how a caller tells "this
    writer emitted a real 2.1 GiB value in a 32-bit field" from "this writer
    emitted the sentinel and put the value in the extra field".
    """

    name: str
    raw_compressed_size: int
    raw_uncompressed_size: int
    raw_local_header_offset: int
    compressed_size: int
    uncompressed_size: int
    local_header_offset: int
    has_zip64_extra: bool

    @property
    def uses_zip64_for_offset(self) -> bool:
        return self.raw_local_header_offset == ZIP64_SENTINEL_32

    @property
    def uses_zip64_for_sizes(self) -> bool:
        """True if *either* size field defers to the ZIP64 extra field.

        Deliberately an OR, for the "did this writer opt into ZIP64 at all"
        question. It is the wrong predicate for checking one field's encoding:
        a correctly-sentineled uncompressed size would paper over a broken
        compressed one.
        """
        return ZIP64_SENTINEL_32 in (
            self.raw_compressed_size,
            self.raw_uncompressed_size,
        )

    def signed_read_of_offset(self) -> int:
        """What a reader that sign-extends a 32-bit read would compute.

        The defect this module exists to catch, expressed directly: for a raw
        value at or above 2**31 this returns a negative number, and a seek to
        it fails or lands on nonsense.
        """
        return struct.unpack("<i", struct.pack("<I", self.raw_local_header_offset))[0]


def _find_eocd(data: bytes) -> int:
    """Offset of the EOCD record within the tail buffer.

    Searched backwards because the signature can also occur *before* the real
    record -- inside entry data, or in a central-directory record's name or
    extra field -- and only the last occurrence can be the EOCD itself. (A
    signature planted inside the trailing file comment would defeat this, but
    it would defeat every ZIP reader; the format is genuinely ambiguous there.)
    """
    idx = data.rfind(_EOCD_SIG)
    if idx < 0:
        raise MalformedZipError("no end-of-central-directory record found")
    return idx


class Zip64Extra(NamedTuple):
    """Decoded ZIP64 extended information field. A tuple, but a named one.

    The bare 4-tuple this replaces was two adjacent ``int | None`` size fields
    in a fixed order, which is exactly the shape where transposing the decode
    goes unnoticed -- both call sites and both mutations type-check.
    """

    present: bool
    uncompressed_size: int | None
    compressed_size: int | None
    local_header_offset: int | None


def _parse_zip64_extra(
    extra: bytes,
    *,
    name: str,
    want_uncompressed: bool,
    want_compressed: bool,
    want_offset: bool,
) -> Zip64Extra:
    """Pull the 64-bit values out of the ZIP64 extended information field.

    The field is positional, not tagged: values appear only for the 32-bit
    fields that held the sentinel, in a fixed order (uncompressed size,
    compressed size, local header offset, disk start). So which values are
    present depends on the record that referenced it, which is what the
    ``want_*`` flags carry in.

    Because it is positional, a length that does not match the record's
    sentinels makes *every* value in it ambiguous, and decoding it anyway
    yields a plausible wrong number rather than an obvious one -- a writer
    that sentinels only the offset but emits all three values would have its
    uncompressed size read back as the offset. So the length is checked
    against the ``want_*`` flags and a mismatch raises. The only slack is the
    trailing 4-byte disk-start field, which is cheap to tolerate.
    """
    wants = (want_uncompressed, want_compressed, want_offset)
    expected = 8 * sum(wants)
    pos = 0
    while pos + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, pos)
        pos += 4
        if pos + size > len(extra):
            raise MalformedZipError(
                f"entry {name!r}: extra field record {header_id:#06x} claims "
                f"{size} bytes but only {len(extra) - pos} remain"
            )
        if header_id != ZIP64_EXTRA_ID:
            pos += size
            continue
        if size == 0 or size not in (expected, expected + 4):
            raise MalformedZipError(
                f"entry {name!r}: ZIP64 extra field is {size} bytes, but the "
                f"record's 32-bit fields call for {expected} "
                f"(uncompressed={want_uncompressed}, "
                f"compressed={want_compressed}, offset={want_offset}). "
                "APPNOTE 4.5.3 makes the field positional, so a length "
                "mismatch leaves every value in it ambiguous."
            )
        body = extra[pos : pos + size]
        # Read the 64-bit values in APPNOTE order, consuming one only for each
        # 32-bit field that actually held the sentinel. The length check above
        # guarantees there are exactly as many as the flags asked for.
        values: list[int | None] = []
        at = 0
        for want in wants:
            if want:
                values.append(struct.unpack_from("<Q", body, at)[0])
                at += 8
            else:
                values.append(None)
        return Zip64Extra(True, values[0], values[1], values[2])
    return Zip64Extra(False, None, None, None)


@dataclass(frozen=True, slots=True)
class CentralDirectory:
    """The parsed directory, plus the ground truth needed to check it against.

    The entries alone cannot catch a writer that truncates an offset mod
    2**32: the truncated value parses cleanly and is indistinguishable from an
    ordinary small offset. Catching that needs to know where the directory
    actually starts and how big the file actually is, which is what
    ``cd_offset`` and ``file_size`` carry out of the parse instead of being
    discarded. See :func:`assert_offsets_are_consistent`.
    """

    entries: list[CentralDirectoryEntry]
    cd_offset: int
    cd_size: int
    file_size: int


def central_directory(path: Path) -> CentralDirectory:
    """Parse every central-directory record in ``path``.

    Reads the tail of the file to locate the directory, then the directory
    itself. The payload is never touched, so cost is independent of container
    size.

    Every read out of those two buffers is bounds-checked first. The inputs
    here are SDK output under test and hand-built byte fixtures, so a
    malformed one is an expected case: it must arrive as
    :class:`MalformedZipError` naming the problem, not as a bare
    ``struct.error`` from somewhere in the middle of the parse.
    """
    file_size = path.stat().st_size
    with path.open("rb") as f:
        tail_len = min(file_size, _MAX_EOCD_SEARCH)
        f.seek(file_size - tail_len)
        tail = f.read(tail_len)

        eocd_at = _find_eocd(tail)
        if eocd_at + _EOCD_SIZE > len(tail):
            raise MalformedZipError(
                f"end-of-central-directory record at {eocd_at} is truncated: "
                f"{len(tail) - eocd_at} of {_EOCD_SIZE} bytes"
            )
        (
            cd_entries_this_disk,
            cd_entries_total,
            cd_size,
            cd_offset,
        ) = struct.unpack_from("<HHII", tail, eocd_at + 8)
        del cd_entries_this_disk

        entry_count = cd_entries_total
        # ZIP64: the 32-bit EOCD holds sentinels and the real values live in
        # the ZIP64 EOCD record, found via the locator that precedes the EOCD.
        locator_at = eocd_at - _EOCD64_LOCATOR_SIZE
        if locator_at >= 0 and tail[locator_at : locator_at + 4] == _EOCD64_LOCATOR_SIG:
            (eocd64_offset,) = struct.unpack_from("<Q", tail, locator_at + 8)
            if eocd64_offset + _EOCD64_SIZE > file_size:
                raise MalformedZipError(
                    f"zip64 locator points at {eocd64_offset}, past the end of "
                    f"a {file_size}-byte file"
                )
            f.seek(eocd64_offset)
            eocd64 = f.read(_EOCD64_SIZE)
            if eocd64[:4] != _EOCD64_SIG:
                raise MalformedZipError(
                    f"zip64 locator points at {eocd64_offset}, which is not a "
                    "zip64 end-of-central-directory record"
                )
            entry_count, cd_size, cd_offset = struct.unpack_from("<QQQ", eocd64, 32)

        # Before the seek, not after: cd_size comes straight off the wire and
        # a garbage value here would otherwise drive an unbounded read.
        if cd_offset + cd_size > file_size:
            raise MalformedZipError(
                f"central directory claims {cd_size} bytes at offset "
                f"{cd_offset}, past the end of a {file_size}-byte file"
            )
        f.seek(cd_offset)
        cd = f.read(cd_size)

    entries: list[CentralDirectoryEntry] = []
    pos = 0
    for _ in range(entry_count):
        if cd[pos : pos + 4] != _CEN_SIG:
            raise MalformedZipError(
                f"expected a central-directory header at {cd_offset + pos}"
            )
        if pos + _CEN_FIXED_SIZE > len(cd):
            raise MalformedZipError(
                f"central-directory header at {cd_offset + pos} is truncated: "
                f"{len(cd) - pos} of {_CEN_FIXED_SIZE} bytes"
            )
        (
            raw_compressed,
            raw_uncompressed,
            name_len,
            extra_len,
            comment_len,
        ) = struct.unpack_from("<IIHHH", cd, pos + 20)
        (raw_offset,) = struct.unpack_from("<I", cd, pos + 42)

        name_at = pos + _CEN_FIXED_SIZE
        extra_at = name_at + name_len
        end = extra_at + extra_len + comment_len
        if end > len(cd):
            raise MalformedZipError(
                f"central-directory header at {cd_offset + pos} claims "
                f"{name_len}+{extra_len}+{comment_len} bytes of name, extra "
                f"and comment, but only {len(cd) - name_at} remain"
            )
        name = cd[name_at:extra_at].decode("utf-8", errors="replace")
        extra = cd[extra_at : extra_at + extra_len]

        want_uncompressed = raw_uncompressed == ZIP64_SENTINEL_32
        want_compressed = raw_compressed == ZIP64_SENTINEL_32
        want_offset = raw_offset == ZIP64_SENTINEL_32
        z = _parse_zip64_extra(
            extra,
            name=name,
            want_uncompressed=want_uncompressed,
            want_compressed=want_compressed,
            want_offset=want_offset,
        )

        # A 32-bit field holding the sentinel promises the real value lives in
        # the extra field. If the field is not there at all, that is a
        # malformed container, not a legitimate "no ZIP64 here" reading:
        # falling back to the raw sentinel (0xFFFFFFFF) below would mislabel it
        # as an ordinary in-window value. (A field that *is* there but the
        # wrong length has already raised inside _parse_zip64_extra.)
        if want_uncompressed and z.uncompressed_size is None:
            raise MalformedZipError(
                f"entry {name!r}: uncompressed size holds the ZIP64 sentinel "
                "but there is no ZIP64 extra field to resolve it"
            )
        if want_compressed and z.compressed_size is None:
            raise MalformedZipError(
                f"entry {name!r}: compressed size holds the ZIP64 sentinel "
                "but there is no ZIP64 extra field to resolve it"
            )
        if want_offset and z.local_header_offset is None:
            raise MalformedZipError(
                f"entry {name!r}: local header offset holds the ZIP64 sentinel "
                "but there is no ZIP64 extra field to resolve it"
            )

        entries.append(
            CentralDirectoryEntry(
                name=name,
                raw_compressed_size=raw_compressed,
                raw_uncompressed_size=raw_uncompressed,
                raw_local_header_offset=raw_offset,
                compressed_size=(
                    z.compressed_size
                    if z.compressed_size is not None
                    else raw_compressed
                ),
                uncompressed_size=(
                    z.uncompressed_size
                    if z.uncompressed_size is not None
                    else raw_uncompressed
                ),
                local_header_offset=(
                    z.local_header_offset
                    if z.local_header_offset is not None
                    else raw_offset
                ),
                has_zip64_extra=z.present,
            )
        )
        pos = end

    return CentralDirectory(
        entries=entries,
        cd_offset=cd_offset,
        cd_size=cd_size,
        file_size=file_size,
    )


def describe(entries: list[CentralDirectoryEntry]) -> str:
    """One line per entry, for attaching to a failure message.

    A structural failure is nearly unreadable without the actual numbers, and
    reproducing it costs a multi-GiB encrypt.
    """
    header = (
        f"{'entry':<20} {'offset':>14} {'raw':>12} "
        f"{'usize':>14} {'csize':>14} {'zip64':>6} {'signed':>14}"
    )
    return "\n".join(
        [header]
        + [
            f"{e.name:<20} {e.local_header_offset:>14} "
            f"{e.raw_local_header_offset:>12} {e.uncompressed_size:>14} "
            f"{e.compressed_size:>14} "
            f"{str(e.has_zip64_extra):>6} {e.signed_read_of_offset():>14}"
            for e in entries
        ]
    )


def assert_offsets_are_consistent(cd: CentralDirectory) -> None:
    """Cross-check the directory against where it actually sits in the file.

    This is what catches a writer that truncates an offset mod 2**32. Such a
    value parses perfectly -- an entry genuinely at 5 GiB written as
    ``5 GiB - 2**32`` looks exactly like an entry at 0.7 GiB -- so no amount
    of inspecting the record on its own will find it. What gives it away is
    that the container disagrees with itself: the entry's data would then have
    to end long after the central directory begins.

    Every clause here is true of any conformant ZIP, so a failure is a real
    writer defect and not a quirk this suite has decided to dislike.
    """
    assert cd.cd_offset + cd.cd_size <= cd.file_size, (
        f"central directory claims {cd.cd_size} bytes at offset "
        f"{cd.cd_offset}, which runs past the end of the {cd.file_size}-byte "
        f"container\n" + describe(cd.entries)
    )

    seen: dict[int, str] = {}
    for e in cd.entries:
        assert e.local_header_offset < cd.cd_offset, (
            f"entry {e.name!r} claims its local header is at "
            f"{e.local_header_offset}, at or after the central directory at "
            f"{cd.cd_offset}\n" + describe(cd.entries)
        )
        # The local header and its data both precede the directory, so the
        # data alone cannot overrun it. Compressed size is the right field:
        # a TDF is STORED, so it is the number of bytes actually on disk.
        end = e.local_header_offset + e.compressed_size
        assert end <= cd.cd_offset, (
            f"entry {e.name!r} claims {e.compressed_size} bytes at offset "
            f"{e.local_header_offset}, ending at {end}, past the central "
            f"directory at {cd.cd_offset}. An offset truncated mod 2**32 "
            f"looks exactly like this.\n" + describe(cd.entries)
        )
        clash = seen.get(e.local_header_offset)
        assert clash is None, (
            f"entries {clash!r} and {e.name!r} both claim a local header at "
            f"{e.local_header_offset}\n" + describe(cd.entries)
        )
        seen[e.local_header_offset] = e.name


def assert_zip64_above_4gib(cd: CentralDirectory) -> None:
    """A container that crosses 4 GiB must use ZIP64 somewhere.

    Above 2**32 there is no latitude: a 32-bit field physically cannot hold
    the value, so the format requires the sentinel plus an extra field.

    Note what this does *not* assert. "Every resolved value at or above 2**32
    uses the sentinel" is unfalsifiable on parser output -- a raw 32-bit field
    tops out at 2**32-1, so a resolved value that large can only have come
    from the extra field in the first place. The check has to be anchored to
    the file's real size instead, which is why it takes the whole
    :class:`CentralDirectory`. The writer defect it leaves uncovered --
    truncation mod 2**32 -- is :func:`assert_offsets_are_consistent`'s.
    """
    if cd.file_size < ZIP64_WINDOW_HIGH:
        return
    assert any(e.uses_zip64_for_offset or e.uses_zip64_for_sizes for e in cd.entries), (
        f"the container is {cd.file_size} bytes, at or above 2**32, but not "
        f"one of its {len(cd.entries)} entries uses a ZIP64 sentinel. Either "
        f"a local header past 4 GiB or an entry whose data crosses it has to "
        f"exist in a file this size, and either one requires ZIP64.\n"
        + describe(cd.entries)
    )


def entries_in_window(
    entries: list[CentralDirectoryEntry],
) -> list[CentralDirectoryEntry]:
    """Entries with an offset or either size in ``[2**31, 2**32)``.

    These are the records a sign-extending reader mishandles. Both encodings
    -- a real unsigned 32-bit value, or the ZIP64 sentinel -- are legal here,
    which is why this returns them for reporting rather than asserting on
    which one the writer chose.
    """
    return [
        e
        for e in entries
        if any(
            in_zip64_window(value)
            for value in (
                e.local_header_offset,
                e.uncompressed_size,
                e.compressed_size,
            )
        )
    ]


def entries_with_raw_values_in_window(
    entries: list[CentralDirectoryEntry],
) -> list[CentralDirectoryEntry]:
    """Entries that exercise unsigned reads of real 32-bit values in the window.

    ``0xffffffff`` is numerically in the window, but it is a sentinel directing
    the reader to the ZIP64 extra field. It therefore does not exercise the
    signed 32-bit read defect this predicate identifies.
    """
    return [
        e
        for e in entries
        if any(
            value != ZIP64_SENTINEL_32 and in_zip64_window(value)
            for value in (
                e.raw_compressed_size,
                e.raw_uncompressed_size,
                e.raw_local_header_offset,
            )
        )
    ]
