"""A ZIP writer for the validity corpus, honouring every lie it is told.

Deliberately not ``zipfile``: most corpus cases are archives ``zipfile``
refuses to write, and the rest need exact control over every header field.
It is a fixture builder, not a general-purpose writer.
"""

import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

STORED = 0
DEFLATED = 8

_LFH_SIG = 0x04034B50
_CEN_SIG = 0x02014B50
_EOCD_SIG = 0x06054B50
_EOCD64_SIG = 0x06064B50
_LOCATOR_SIG = 0x07064B50
_DD_SIG = 0x08074B50
_SENTINEL_32 = 0xFFFFFFFF
_SENTINEL_16 = 0xFFFF

#: 1980-01-01 00:00, the DOS epoch. Fixed so the corpus is byte-stable.
_DOS_TIME = 0
_DOS_DATE = (1 << 5) | 1

FLAG_ENCRYPTED = 0x0001
_FLAG_DATA_DESCRIPTOR = 0x0008


@dataclass(frozen=True, slots=True)
class Entry:
    """One archive member. Every declared value can be made to lie."""

    name: str
    data: bytes
    method: int = STORED
    #: Declared CRC-32. None: the CRC of ``crc_of`` if given, else of ``data``.
    crc32: int | None = None
    crc_of: bytes | None = None
    #: Declared sizes. None: ``len(data)``, and for the uncompressed size the
    #: length of ``crc_of`` when that stands in for deflated bytes.
    compressed_size: int | None = None
    uncompressed_size: int | None = None
    #: General-purpose flag bits other than the data-descriptor bit.
    flags: int = 0
    #: Sizes and CRC go after the data (flag bit 3) rather than in the local
    #: header. How the Go and Java writers stream.
    data_descriptor: bool = False
    #: ZIP64 extra fields in both headers, with sentinel sizes and offset.
    #: How web-sdk writes every entry, whatever its size.
    zip64: bool = False

    def declared(self) -> tuple[int, int, int]:
        crc = self.crc32
        if crc is None:
            crc = zlib.crc32(self.crc_of if self.crc_of is not None else self.data)
        csize = len(self.data) if self.compressed_size is None else self.compressed_size
        usize = self.uncompressed_size
        if usize is None:
            usize = len(self.crc_of) if self.crc_of is not None else len(self.data)
        return crc & 0xFFFFFFFF, csize, usize


@dataclass(slots=True)
class Built:
    """An archive's bytes, plus where each structure landed in them."""

    data: bytes
    #: ``(label, offset)`` for every structure boundary, in file order.
    boundaries: list[tuple[str, int]] = field(default_factory=list)


def build_zip(
    entries: Sequence[Entry],
    *,
    comment: bytes = b"",
    zip64_eocd: bool = False,
    cd_size: int | None = None,
    cd_offset: int | None = None,
    entry_count: int | None = None,
    local_offsets: dict[int, int] | None = None,
    locator_offset: int | None = None,
) -> Built:
    """Write ``entries`` as a ZIP, honouring every override verbatim.

    The overrides change what the trailer *declares*; nothing is moved to
    match. ``local_offsets`` maps an entry index to the local-header offset
    its central-directory record should claim.
    """
    out = bytearray()
    marks: list[tuple[str, int]] = []
    cen = bytearray()
    cen_starts: list[int] = []
    for i, e in enumerate(entries):
        crc, csize, usize = e.declared()
        name = e.name.encode()
        flags = e.flags | (_FLAG_DATA_DESCRIPTOR if e.data_descriptor else 0)
        version = 45 if e.zip64 else 20
        offset = len(out)
        marks.append((f"lfh{i}", offset))

        if e.zip64:
            lfh_extra = struct.pack("<HHQQ", 1, 16, usize, csize)
            l_crc, l_csize, l_usize = (
                (0, _SENTINEL_32, _SENTINEL_32)
                if e.data_descriptor
                else (crc, _SENTINEL_32, _SENTINEL_32)
            )
        else:
            lfh_extra = b""
            l_crc, l_csize, l_usize = (
                (0, 0, 0) if e.data_descriptor else (crc, csize, usize)
            )
        out += struct.pack(
            "<IHHHHHIIIHH",
            _LFH_SIG,
            version,
            flags,
            e.method,
            _DOS_TIME,
            _DOS_DATE,
            l_crc,
            l_csize,
            l_usize,
            len(name),
            len(lfh_extra),
        )
        out += name + lfh_extra
        marks.append((f"data{i}", len(out)))
        out += e.data
        if e.data_descriptor:
            marks.append((f"dd{i}", len(out)))
            if e.zip64:
                out += struct.pack("<IIQQ", _DD_SIG, crc, csize, usize)
            else:
                out += struct.pack("<IIII", _DD_SIG, crc, csize, usize)

        declared_offset = (local_offsets or {}).get(i, offset)
        if e.zip64:
            cen_extra = struct.pack("<HHQQQ", 1, 24, usize, csize, declared_offset)
            c_csize, c_usize, c_offset = _SENTINEL_32, _SENTINEL_32, _SENTINEL_32
        else:
            cen_extra = b""
            c_csize, c_usize, c_offset = csize, usize, declared_offset
        cen_starts.append(len(cen))
        cen += struct.pack(
            "<IHHHHHHIIIHHHHHII",
            _CEN_SIG,
            version,
            version,
            flags,
            e.method,
            _DOS_TIME,
            _DOS_DATE,
            crc,
            c_csize,
            c_usize,
            len(name),
            len(cen_extra),
            0,
            0,
            0,
            0,
            c_offset,
        )
        cen += name + cen_extra

    true_cd_offset = len(out)
    marks.append(("cd", true_cd_offset))
    marks += [(f"cen{i}", true_cd_offset + at) for i, at in enumerate(cen_starts)][1:]
    out += cen
    count = len(entries) if entry_count is None else entry_count
    size = len(cen) if cd_size is None else cd_size
    start = true_cd_offset if cd_offset is None else cd_offset

    if zip64_eocd:
        eocd64_at = len(out)
        marks.append(("eocd64", eocd64_at))
        out += struct.pack(
            "<IQHHIIQQQQ", _EOCD64_SIG, 44, 45, 45, 0, 0, count, count, size, start
        )
        marks.append(("locator", len(out)))
        out += struct.pack(
            "<IIQI",
            _LOCATOR_SIG,
            0,
            eocd64_at if locator_offset is None else locator_offset,
            1,
        )
        e_count, e_size, e_start = _SENTINEL_16, _SENTINEL_32, _SENTINEL_32
    else:
        e_count, e_size, e_start = count, size, start
    marks.append(("eocd", len(out)))
    out += struct.pack(
        "<IHHHHIIH", _EOCD_SIG, 0, 0, e_count, e_count, e_size, e_start, len(comment)
    )
    out += comment
    return Built(bytes(out), marks)


def zip_bytes(entries: Sequence[Entry], **kw: Any) -> bytes:
    return build_zip(entries, **kw).data


def deflate(data: bytes) -> bytes:
    """Raw DEFLATE (no zlib header), as a ZIP method-8 entry holds it."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()
