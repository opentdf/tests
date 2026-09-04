"""Raw ZIP central-directory reader, for asserting on the *encoding*.

``zipfile`` cannot be used for this. It normalises ZIP64 away -- ask it for an
entry's header offset and you get the resolved value, whether that came from
the 32-bit field or from a ZIP64 extra field. The distinction it discards is
precisely what these tests are about, so the bytes are parsed here instead.

Only the tail of the file plus the central directory is read, so this stays
cheap on a multi-GiB container.

Reference: APPNOTE.TXT 4.3.12 (central directory header), 4.3.16 (end of
central directory), 4.5.3 (the ZIP64 extended information extra field).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from sizes import ZIP64_WINDOW_HIGH, in_zip64_window

# Signatures, little-endian.
_CEN_SIG = b"PK\x01\x02"
_EOCD_SIG = b"PK\x05\x06"
_EOCD64_SIG = b"PK\x06\x06"
_EOCD64_LOCATOR_SIG = b"PK\x06\x07"

#: Written into a 32-bit field to mean "the real value is in the ZIP64 extra
#: field". APPNOTE 4.4.1.4.
ZIP64_SENTINEL_32 = 0xFFFFFFFF
ZIP64_SENTINEL_16 = 0xFFFF

#: Header ID of the ZIP64 extended information extra field. APPNOTE 4.5.3.
ZIP64_EXTRA_ID = 0x0001

_EOCD_SIZE = 22
_EOCD64_LOCATOR_SIZE = 20
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

    Searched backwards: the signature can legitimately appear inside a file
    comment, and the last occurrence is the real one.
    """
    idx = data.rfind(_EOCD_SIG)
    if idx < 0:
        raise MalformedZipError("no end-of-central-directory record found")
    return idx


def _parse_zip64_extra(
    extra: bytes,
    *,
    want_uncompressed: bool,
    want_compressed: bool,
    want_offset: bool,
) -> tuple[bool, int | None, int | None, int | None]:
    """Pull the 64-bit values out of the ZIP64 extended information field.

    The field is positional, not tagged: values appear only for the 32-bit
    fields that held the sentinel, in a fixed order (uncompressed size,
    compressed size, local header offset, disk start). So which values are
    present depends on the record that referenced it, which is what the
    ``want_*`` flags carry in.

    Returns ``(present, uncompressed, compressed, offset)``; the values are
    None when the corresponding 32-bit field did not hold the sentinel.
    """
    pos = 0
    while pos + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, pos)
        pos += 4
        if pos + size > len(extra):
            break
        if header_id != ZIP64_EXTRA_ID:
            pos += size
            continue
        body = extra[pos : pos + size]
        # Read the 64-bit values in APPNOTE order, consuming one only for each
        # 32-bit field that actually held the sentinel. A truncated field
        # yields None rather than raising: a malformed extra field is a
        # finding for the caller's assertions, not a parse error.
        values: list[int | None] = []
        at = 0
        for want in (want_uncompressed, want_compressed, want_offset):
            if want and at + 8 <= len(body):
                values.append(struct.unpack_from("<Q", body, at)[0])
                at += 8
            else:
                values.append(None)
        return True, values[0], values[1], values[2]
    return False, None, None, None


def central_directory(path: Path) -> list[CentralDirectoryEntry]:
    """Parse every central-directory record in ``path``.

    Reads the tail of the file to locate the directory, then the directory
    itself. The payload is never touched, so cost is independent of container
    size.
    """
    size = path.stat().st_size
    with path.open("rb") as f:
        tail_len = min(size, _MAX_EOCD_SEARCH)
        f.seek(size - tail_len)
        tail = f.read(tail_len)

        eocd_at = _find_eocd(tail)
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
            f.seek(eocd64_offset)
            eocd64 = f.read(56)
            if eocd64[:4] != _EOCD64_SIG:
                raise MalformedZipError(
                    f"zip64 locator points at {eocd64_offset}, which is not a "
                    "zip64 end-of-central-directory record"
                )
            entry_count, cd_size, cd_offset = struct.unpack_from("<QQQ", eocd64, 32)

        f.seek(cd_offset)
        cd = f.read(cd_size)

    entries: list[CentralDirectoryEntry] = []
    pos = 0
    for _ in range(entry_count):
        if cd[pos : pos + 4] != _CEN_SIG:
            raise MalformedZipError(
                f"expected a central-directory header at {cd_offset + pos}"
            )
        (
            raw_compressed,
            raw_uncompressed,
            name_len,
            extra_len,
            comment_len,
        ) = struct.unpack_from("<IIHHH", cd, pos + 20)
        (raw_offset,) = struct.unpack_from("<I", cd, pos + 42)

        name_at = pos + 46
        extra_at = name_at + name_len
        name = cd[name_at:extra_at].decode("utf-8", errors="replace")
        extra = cd[extra_at : extra_at + extra_len]

        want_uncompressed = raw_uncompressed == ZIP64_SENTINEL_32
        want_compressed = raw_compressed == ZIP64_SENTINEL_32
        want_offset = raw_offset == ZIP64_SENTINEL_32
        has_extra, z_uncompressed, z_compressed, z_offset = _parse_zip64_extra(
            extra,
            want_uncompressed=want_uncompressed,
            want_compressed=want_compressed,
            want_offset=want_offset,
        )

        entries.append(
            CentralDirectoryEntry(
                name=name,
                raw_compressed_size=raw_compressed,
                raw_uncompressed_size=raw_uncompressed,
                raw_local_header_offset=raw_offset,
                compressed_size=(
                    z_compressed if z_compressed is not None else raw_compressed
                ),
                uncompressed_size=(
                    z_uncompressed if z_uncompressed is not None else raw_uncompressed
                ),
                local_header_offset=z_offset if z_offset is not None else raw_offset,
                has_zip64_extra=has_extra,
            )
        )
        pos = extra_at + extra_len + comment_len

    return entries


def describe(entries: list[CentralDirectoryEntry]) -> str:
    """One line per entry, for attaching to a failure message.

    A structural failure is nearly unreadable without the actual numbers, and
    reproducing it costs a multi-GiB encrypt.
    """
    header = (
        f"{'entry':<20} {'offset':>14} {'raw':>12} "
        f"{'usize':>14} {'zip64':>6} {'signed':>14}"
    )
    return "\n".join(
        [header]
        + [
            f"{e.name:<20} {e.local_header_offset:>14} "
            f"{e.raw_local_header_offset:>12} {e.uncompressed_size:>14} "
            f"{str(e.has_zip64_extra):>6} {e.signed_read_of_offset():>14}"
            for e in entries
        ]
    )


def assert_zip64_above_4gib(entries: list[CentralDirectoryEntry]) -> None:
    """Every value at or above 2**32 must use the ZIP64 sentinel plus extra field.

    Unlike the 2-4 GiB band, there is no latitude here: a 32-bit field
    physically cannot hold the value, so a writer that does not emit the
    sentinel has produced a container whose stated offsets are wrong.
    """
    for e in entries:
        if e.local_header_offset >= ZIP64_WINDOW_HIGH:
            assert e.uses_zip64_for_offset and e.has_zip64_extra, (
                f"entry {e.name!r} is at offset {e.local_header_offset}, at or "
                f"above 2**32, but its 32-bit field holds "
                f"{e.raw_local_header_offset} rather than the ZIP64 sentinel\n"
                + describe(entries)
            )
        if e.uncompressed_size >= ZIP64_WINDOW_HIGH:
            assert e.uses_zip64_for_sizes and e.has_zip64_extra, (
                f"entry {e.name!r} is {e.uncompressed_size} bytes, at or above "
                f"2**32, but its 32-bit size field holds "
                f"{e.raw_uncompressed_size} rather than the ZIP64 sentinel\n"
                + describe(entries)
            )


def entries_in_window(
    entries: list[CentralDirectoryEntry],
) -> list[CentralDirectoryEntry]:
    """Entries with an offset or size in ``[2**31, 2**32)``.

    These are the records a sign-extending reader mishandles. Both encodings
    -- a real unsigned 32-bit value, or the ZIP64 sentinel -- are legal here,
    which is why this returns them for reporting rather than asserting on
    which one the writer chose.
    """
    return [
        e
        for e in entries
        if in_zip64_window(e.local_header_offset)
        or in_zip64_window(e.uncompressed_size)
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
