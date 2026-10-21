"""Serve a TDF over HTTP ``Range`` requests, optionally with most of it missing.

DSPX-5111. A partial decrypt of a 100 GiB-50 TiB TDF needs only the ZIP head,
the encrypted segments covering the requested plaintext, and the tail
(manifest, central directory, end records). :func:`retention_plan` says which
ciphertext bytes those are, :class:`ExtentStore` keeps just them, and
:func:`serve` puts either a store or an ordinary file behind a loopback HTTP
server that logs every request.

A request touching a byte that was not kept gets ``410 Gone``, never zeros: a
reader that over-fetches must fail loudly rather than decrypt garbage, and
must not pass a test by accident.

All ranges here are half-open ``(start, end)`` pairs.
"""

import bisect
import os
import re
import struct
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple, Protocol

import zipinspect

#: AES-GCM adds a 12-byte IV and a 16-byte tag to every segment.
PAYLOAD_GCM_OVERHEAD = 28

_LOCAL_HEADER_SIG = b"PK\x03\x04"
_LOCAL_HEADER_FIXED_SIZE = 30
_CHUNK = 1 << 20


class Dropped(Exception):
    """A read touched bytes that were deliberately not kept."""


def payload_start(path: Path) -> int:
    """Offset of the first byte of ``0.payload``'s data in the TDF at ``path``."""
    cd = zipinspect.central_directory(path)
    entry = next((e for e in cd.entries if e.name == "0.payload"), None)
    if entry is None:
        raise zipinspect.MalformedZipError(f"{path}: no 0.payload entry")
    with path.open("rb") as f:
        f.seek(entry.local_header_offset)
        header = f.read(_LOCAL_HEADER_FIXED_SIZE)
    if len(header) < _LOCAL_HEADER_FIXED_SIZE or header[:4] != _LOCAL_HEADER_SIG:
        raise zipinspect.MalformedZipError(
            f"{path}: no local file header at {entry.local_header_offset}"
        )
    name_len, extra_len = struct.unpack_from("<HH", header, 26)
    return entry.local_header_offset + _LOCAL_HEADER_FIXED_SIZE + name_len + extra_len


def merge(extents: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort extents and merge any that overlap or touch; drop empty ones."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(e for e in extents if e[1] > e[0]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def retention_plan(
    ranges: Sequence[tuple[int, int]],
    *,
    plaintext_length: int,
    segment_size: int,
    payload_start: int,
) -> list[tuple[int, int]]:
    """Ciphertext extents a partial decrypt of plaintext ``ranges`` reads.

    Always includes the head, ``[0, payload_start)``. Excludes the tail,
    whose start is not known until the payload has been written.

    Fixed before encrypt: ciphertext is not deterministic, so a dropped
    extent cannot be regenerated afterwards.
    """
    if segment_size <= 0:
        raise ValueError(f"segment_size must be positive, got {segment_size}")
    stride = segment_size + PAYLOAD_GCM_OVERHEAD
    extents = [(0, payload_start)]
    for start, end in ranges:
        if not 0 <= start <= end <= plaintext_length:
            raise ValueError(
                f"plaintext range {start}-{end} is outside 0-{plaintext_length}"
            )
        if start == end:
            continue
        first, last = start // segment_size, (end - 1) // segment_size
        last_size = min(segment_size, plaintext_length - last * segment_size)
        extents.append(
            (
                payload_start + first * stride,
                payload_start + last * stride + last_size + PAYLOAD_GCM_OVERHEAD,
            )
        )
    return merge(extents)


class Source(Protocol):
    @property
    def length(self) -> int: ...

    def check(self, start: int, end: int) -> None:
        """Raise :class:`Dropped` if any of ``[start, end)`` was not kept."""
        ...

    def read(self, start: int, end: int) -> bytes: ...


class FullFile:
    """An ordinary file: every byte is available."""

    def __init__(self, path: Path):
        self.path = path
        self.length = path.stat().st_size

    def check(self, start: int, end: int) -> None:
        pass

    def read(self, start: int, end: int) -> bytes:
        with self.path.open("rb") as f:
            return os.pread(f.fileno(), end - start, start)


class ExtentStore:
    """Kept extents of a large logical file, packed into one small data file.

    Not a sparse file: ext4 caps a file at 16 TiB, and the 50 TiB tier must
    not depend on the filesystem. Disk use is the kept bytes, nothing more.
    """

    def __init__(self, directory: Path, logical_length: int):
        self.length = logical_length
        self.data_path = directory / "extents.bin"
        self._data = self.data_path.open("w+b")
        # Sorted, non-overlapping (logical_start, logical_end, physical_start).
        self._index: list[tuple[int, int, int]] = []

    def close(self) -> None:
        self._data.close()

    @property
    def physical_size(self) -> int:
        return self.data_path.stat().st_size

    def add(self, offset: int, data: bytes) -> None:
        end = offset + len(data)
        if not data:
            return
        if offset < 0 or end > self.length:
            raise ValueError(f"extent {offset}-{end} is outside 0-{self.length}")
        i = bisect.bisect(self._index, (offset,))
        if (i > 0 and self._index[i - 1][1] > offset) or (
            i < len(self._index) and self._index[i][0] < end
        ):
            raise ValueError(f"extent {offset}-{end} overlaps one already kept")
        physical = self._data.seek(0, os.SEEK_END)
        self._data.write(data)
        self._data.flush()
        prev = self._index[i - 1] if i else None
        # Streaming writes arrive as many contiguous chunks; keep one entry.
        if prev and prev[1] == offset and prev[2] + (prev[1] - prev[0]) == physical:
            self._index[i - 1] = (prev[0], end, prev[2])
        else:
            self._index.insert(i, (offset, end, physical))

    def _pieces(self, start: int, end: int) -> Iterator[tuple[int, int]]:
        """Yield ``(physical_offset, n)`` covering ``[start, end)``, or raise."""
        i = bisect.bisect(self._index, (start, float("inf"))) - 1
        pos = start
        while pos < end:
            if (
                i < 0
                or i >= len(self._index)
                or not (self._index[i][0] <= pos < self._index[i][1])
            ):
                raise Dropped(f"bytes {pos}-{end} were not kept")
            lstart, lend, physical = self._index[i]
            n = min(lend, end) - pos
            yield physical + pos - lstart, n
            pos += n
            i += 1

    def check(self, start: int, end: int) -> None:
        for _ in self._pieces(start, end):
            pass

    def read(self, start: int, end: int) -> bytes:
        fd = self._data.fileno()
        return b"".join(os.pread(fd, n, p) for p, n in self._pieces(start, end))


class Request(NamedTuple):
    method: str
    range: str | None
    status: int
    bytes_served: int


_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def _parse_range(header: str, length: int) -> tuple[int, int] | None:
    """Resolve a single-range header to ``(start, end)``; None if unsatisfiable.

    Raises ValueError for anything that is not exactly one byte range.
    """
    m = _RANGE.fullmatch(header.strip())
    if not m or m.group(1) == m.group(2) == "":
        raise ValueError(f"unsupported Range: {header!r}")
    first, last = m.group(1), m.group(2)
    if first == "":
        start, end = max(0, length - int(last)), length
        return (start, end) if int(last) > 0 and length > 0 else None
    start = int(first)
    end = length if last == "" else min(int(last) + 1, length)
    if last != "" and int(last) < start:
        raise ValueError(f"unsupported Range: {header!r}")
    return (start, end) if start < length else None


@contextmanager
def serve(source: Source) -> Iterator[tuple[str, list[Request]]]:
    """Serve ``source`` on an ephemeral loopback port.

    Yields ``(url, log)``. ``log`` gains one :class:`Request` per request.
    The server thread is stopped and joined on exit.
    """
    log: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def _reply(self, status: int, body: bytes = b"", **headers: str) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            for k, v in headers.items():
                self.send_header(k.replace("_", "-"), v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            log.append(Request(self.command, self.headers["Range"], status, 0))

        def do_HEAD(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(source.length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            log.append(Request("HEAD", self.headers["Range"], 200, 0))

        def do_GET(self) -> None:
            header = self.headers["Range"]
            start, end, status = 0, source.length, 200
            if header is not None:
                try:
                    resolved = _parse_range(header, source.length)
                except ValueError as e:
                    return self._reply(400, str(e).encode())
                if resolved is None:
                    return self._reply(416, Content_Range=f"bytes */{source.length}")
                (start, end), status = resolved, 206
            try:
                source.check(start, end)
            except Dropped as e:
                return self._reply(410, str(e).encode())
            self.send_response(status)
            self.send_header("Content-Length", str(end - start))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header(
                    "Content-Range", f"bytes {start}-{end - 1}/{source.length}"
                )
            self.end_headers()
            served = 0
            try:
                for pos in range(start, end, _CHUNK):
                    self.wfile.write(source.read(pos, min(pos + _CHUNK, end)))
                    served = min(pos + _CHUNK, end) - start
            finally:
                log.append(Request("GET", header, status, served))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, name=f"rangeserve-{port}", daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/payload.tdf", log
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
