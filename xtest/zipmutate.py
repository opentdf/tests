"""Deliberately-shaped ZIP trailers over a real TDF, for cross-SDK conformance
tests (DSPX-4591 follow-up).

A ZIP's central directory is metadata describing where the real bytes are.
As long as a mutation's resolved values still point at an entry's true,
physical local header, the CD/EOCD/ZIP64-EOCD/locator trailer can be
rewritten wholesale -- sentinel a field, reorder its extra-field TLVs,
inflate the declared entry count, pad the comment -- without moving or
repacking a single local header or payload byte. Only bytes from
``cd_offset`` onward change; everything before is copied verbatim.

Read the source through :mod:`zipinspect` -- the same oracle the conformance
assertions use -- then rebuild only the trailer. This module is write-only
and test-fixture-only: nothing here is a general-purpose ZIP writer, and
every entry point takes distinct ``src``/``dest`` paths and never mutates
``src``. That is what keeps a mutation from corrupting a session-memoized
``EncryptFactory`` ciphertext that another test still expects to read
faithfully.
"""

from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

import zipinspect


@dataclass(frozen=True, slots=True)
class MutableEntry:
    """One central-directory record, rebuildable with deliberate variations.

    Values loaded from an archive describe its physical bytes. Sentinel
    switches only change their encoding; adversarial tests may replace the
    values or the extra area explicitly to describe bytes that do not exist.
    """

    name: str
    local_header_offset: int
    compressed_size: int
    uncompressed_size: int
    crc32: int = 0
    #: Ordinary entries use 2.0; tests enabling ZIP64 fields set 4.5 explicitly.
    #: A lower declaration can still be used for malformed-input compatibility.
    version_needed_to_extract: int = 20
    #: A foreign extra-field TLV (e.g. an extended-timestamp record) placed
    #: *before* any ZIP64 record this builds, to test order independence.
    extra_prefix: bytes = b""
    #: Replace the entire extra area, including ZIP64, for malformed fixtures.
    extra_override: bytes | None = None
    comment: bytes = b""
    force_zip64_offset: bool = False
    force_zip64_compressed_size: bool = False
    force_zip64_uncompressed_size: bool = False

    @staticmethod
    def from_entry(e: zipinspect.CentralDirectoryEntry) -> MutableEntry:
        """A faithful starting point: same physical values, ZIP64 knobs off."""
        return MutableEntry(
            name=e.name,
            local_header_offset=e.local_header_offset,
            compressed_size=e.compressed_size,
            uncompressed_size=e.uncompressed_size,
            crc32=e.raw_crc32,
        )

    def to_bytes(self) -> bytes:
        """Encode as one central-directory record (APPNOTE 4.3.12)."""
        zip64_body = b""
        if self.force_zip64_uncompressed_size:
            zip64_body += struct.pack("<Q", self.uncompressed_size)
        if self.force_zip64_compressed_size:
            zip64_body += struct.pack("<Q", self.compressed_size)
        if self.force_zip64_offset:
            zip64_body += struct.pack("<Q", self.local_header_offset)
        zip64_tlv = (
            struct.pack("<HH", zipinspect.ZIP64_EXTRA_ID, len(zip64_body)) + zip64_body
            if zip64_body
            else b""
        )
        extra = self.extra_prefix + zip64_tlv
        if self.extra_override is not None:
            extra = self.extra_override

        raw_usize = (
            zipinspect.ZIP64_SENTINEL_32
            if self.force_zip64_uncompressed_size
            else self.uncompressed_size
        )
        raw_csize = (
            zipinspect.ZIP64_SENTINEL_32
            if self.force_zip64_compressed_size
            else self.compressed_size
        )
        raw_offset = (
            zipinspect.ZIP64_SENTINEL_32
            if self.force_zip64_offset
            else self.local_header_offset
        )

        encoded = self.name.encode()
        return (
            zipinspect.CEN_SIG
            + struct.pack("<HHHHHH", 45, self.version_needed_to_extract, 0, 0, 0, 0)
            + struct.pack("<I", self.crc32)
            + struct.pack("<II", raw_csize, raw_usize)
            + struct.pack("<HHH", len(encoded), len(extra), len(self.comment))
            + struct.pack("<HHI", 0, 0, 0)
            + struct.pack("<I", raw_offset)
            + encoded
            + extra
            + self.comment
        )


@dataclass(frozen=True, slots=True)
class MutableTrailer:
    """The central directory plus its EOCD (and ZIP64 EOCD/locator if forced)."""

    entries: list[MutableEntry]
    comment: bytes = b""
    #: Emit a ZIP64 EOCD + locator even though nothing here requires one --
    #: spec-legal (APPNOTE does not forbid it), and how a real container's
    #: ZIP64 locator gets pushed behind an oversized comment for testing.
    force_zip64_eocd: bool = False
    #: Which ordinary EOCD fields defer to ZIP64; the others remain truthful.
    #: Used only when force_zip64_eocd is true. Disk numbers always remain zero.
    zip64_eocd_fields: frozenset[str] = frozenset({"count", "size", "offset"})
    #: Lie about the entry count in the EOCD (or ZIP64 EOCD). None: truthful.
    #: The central directory's own bytes are never padded to match, so a
    #: reader that walks this many records runs off the real data.
    entry_count_override: int | None = None
    #: Malformed declarations; physical placement of the records is unchanged.
    cd_offset_override: int | None = None
    zip64_locator_offset_override: int | None = None

    def to_bytes(self, cd_offset: int) -> bytes:
        cd = b"".join(e.to_bytes() for e in self.entries)
        declared_offset = (
            cd_offset if self.cd_offset_override is None else self.cd_offset_override
        )
        declared_count = (
            len(self.entries)
            if self.entry_count_override is None
            else self.entry_count_override
        )
        if len(self.comment) > 0xFFFF:
            raise ValueError(
                f"EOCD comment is {len(self.comment)} bytes; a 16-bit length "
                "field caps it at 0xFFFF"
            )

        if self.force_zip64_eocd:
            if not self.zip64_eocd_fields <= {"count", "size", "offset"}:
                raise ValueError(f"unknown ZIP64 EOCD fields: {self.zip64_eocd_fields}")
            eocd64_offset = cd_offset + len(cd)
            eocd64 = (
                zipinspect.EOCD64_SIG
                + struct.pack("<Q", 44)  # size of this record, less the first 12 bytes
                + struct.pack("<HHII", 45, 45, 0, 0)
                + struct.pack(
                    "<QQQQ", declared_count, declared_count, len(cd), declared_offset
                )
            )
            locator = (
                zipinspect.EOCD64_LOCATOR_SIG
                + struct.pack("<I", 0)
                + struct.pack(
                    "<Q",
                    eocd64_offset
                    if self.zip64_locator_offset_override is None
                    else self.zip64_locator_offset_override,
                )
                + struct.pack("<I", 1)
            )
            eocd = (
                zipinspect.EOCD_SIG
                + struct.pack(
                    "<HHHH",
                    0,
                    0,
                    0xFFFF if "count" in self.zip64_eocd_fields else declared_count,
                    0xFFFF if "count" in self.zip64_eocd_fields else declared_count,
                )
                + struct.pack(
                    "<II",
                    0xFFFFFFFF if "size" in self.zip64_eocd_fields else len(cd),
                    0xFFFFFFFF
                    if "offset" in self.zip64_eocd_fields
                    else declared_offset,
                )
                + struct.pack("<H", len(self.comment))
                + self.comment
            )
            return cd + eocd64 + locator + eocd

        eocd = (
            zipinspect.EOCD_SIG
            + struct.pack("<HHHH", 0, 0, declared_count, declared_count)
            + struct.pack("<II", len(cd), declared_offset)
            + struct.pack("<H", len(self.comment))
            + self.comment
        )
        return cd + eocd


def load_trailer(path: Path) -> tuple[MutableTrailer, int]:
    """Parse ``path`` and return an editable trailer plus its ``cd_offset``.

    Every entry starts as a faithful round-trip
    (:meth:`MutableEntry.from_entry`); callers mutate individual entries or
    the trailer's own fields before passing the result to :func:`rewrite`.
    """
    cd = zipinspect.central_directory(path)
    trailer = MutableTrailer(entries=[MutableEntry.from_entry(e) for e in cd.entries])
    return trailer, cd.cd_offset


def rewrite(src: Path, dest: Path, trailer: MutableTrailer) -> Path:
    """Copy ``src``'s entry data verbatim, then append ``trailer`` as its CD/EOCD.

    ``src`` and ``dest`` must differ, checked here rather than left to whatever
    the caller's file-open mode happens to do: this is the one thing standing
    between a mutation and silently corrupting a ciphertext another test still
    expects to read faithfully.
    """
    if src.resolve() == dest.resolve():
        raise ValueError(f"rewrite requires distinct src and dest, both {src}")
    _, cd_offset = load_trailer(src)
    with src.open("rb") as f_in, dest.open("wb") as f_out:
        remaining = cd_offset
        while remaining:
            chunk = f_in.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise zipinspect.MalformedZipError(
                    f"{src} is shorter than its own central directory offset "
                    f"({cd_offset})"
                )
            f_out.write(chunk)
            remaining -= len(chunk)
        f_out.write(trailer.to_bytes(cd_offset))
    return dest


def corrupt_entry_bytes(
    src: Path, dest: Path, entry_name: str, *, at: int, patch: bytes
) -> Path:
    """Copy ``src`` to ``dest``, then overwrite ``patch`` inside one entry's data.

    ``at`` is relative to the start of ``entry_name``'s data region (located
    via :func:`zipinspect.local_file_header_data_offset`), not the file.
    Every structural field -- local headers, central directory, EOCD -- stays
    byte-identical and truthful; only the named window of that one entry's
    data changes. This invalidates the entry's CRC-32 and any payload
    authentication, so callers must account for those failures as well.
    """
    if src.resolve() == dest.resolve():
        raise ValueError(
            f"corrupt_entry_bytes requires distinct src and dest, both {src}"
        )
    cd = zipinspect.central_directory(src)
    try:
        entry = next(e for e in cd.entries if e.name == entry_name)
    except StopIteration:
        raise ValueError(
            f"{src} has no entry named {entry_name!r}; entries are "
            f"{[e.name for e in cd.entries]}"
        ) from None
    data_offset = zipinspect.local_file_header_data_offset(src, entry)
    patch_at = data_offset + at
    if at < 0 or at + len(patch) > entry.compressed_size:
        raise ValueError(
            f"patch of {len(patch)} bytes at relative offset {at} would run "
            f"outside entry {entry_name!r}'s {entry.compressed_size}-byte data region"
        )
    shutil.copyfile(src, dest)
    with dest.open("r+b") as f:
        f.seek(patch_at)
        f.write(patch)
    return dest
