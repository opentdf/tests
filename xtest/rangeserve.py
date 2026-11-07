"""Serve a TDF over HTTP ``Range`` requests, optionally with most of it missing.

DSPX-5111. A partial decrypt of a 100 GiB-50 TiB TDF needs only the ZIP head,
the encrypted segments covering the requested plaintext, and the tail
(manifest, central directory, end records). :func:`retention_plan` says which
ciphertext bytes those are, :class:`ExtentStore` keeps just them, and
:func:`serve` puts either a store or an ordinary file behind a loopback HTTP
server that logs every request.

A request touching a byte that was not kept gets ``410 Gone``, never zeros: a
reader that over-fetches must fail loudly rather than decrypt garbage, and
must not pass a test by accident. 410 is the signal; a front end that has to
answer anyway, like an NFS server, picks its own filler.

All ranges here are half-open ``(start, end)`` pairs.
"""

import bisect
import errno
import io
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple, Protocol

import zipinspect

#: AES-GCM adds a 12-byte IV and a 16-byte tag to every segment.
PAYLOAD_GCM_OVERHEAD = 28

_CHUNK = 1 << 20
#: How long ``serve`` waits for handler threads once their sockets are shut.
_JOIN_TIMEOUT = 10.0


class Dropped(Exception):
    """A read touched bytes that were deliberately not kept."""

    def __init__(self, message: str, offset: int | None = None):
        super().__init__(message)
        #: The first byte not kept, if the source knows it.
        self.offset = offset


def payload_start(path: Path) -> int:
    """Offset of the first byte of ``0.payload``'s data in the TDF at ``path``."""
    cd = zipinspect.central_directory(path)
    entry = next((e for e in cd.entries if e.name == "0.payload"), None)
    if entry is None:
        raise zipinspect.MalformedZipError(f"{path}: no 0.payload entry")
    return zipinspect.local_file_header_data_offset(path, entry)


def data_end(*, payload_start: int, plaintext_length: int, segment_size: int) -> int:
    """End of the last segment holding plaintext, where the tail starts.

    Java follows a whole number of segments with an empty one, its IV and
    tag, and go and java write one for empty plaintext. That is tail too.
    """
    segments = -(-plaintext_length // segment_size)
    return payload_start + plaintext_length + segments * PAYLOAD_GCM_OVERHEAD


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

    Always includes the head, ``[0, payload_start)``. Excludes the tail, from
    :func:`data_end` on, whose length is not known until the TDF is written.

    Plan before encrypt; only planned bytes are kept.
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
    """Bytes for :func:`serve`.

    ``check`` and ``read`` may be called concurrently, from handler threads.
    ``length`` is fixed while the source is served.
    """

    @property
    def length(self) -> int: ...

    def check(self, start: int, end: int) -> None:
        """Raise :class:`Dropped` if any of ``[start, end)`` was not kept."""
        ...

    def read(self, start: int, end: int) -> bytes:
        """Exactly ``end - start`` bytes.

        May raise :class:`Dropped` even after ``check`` passed.
        """
        ...


class FullFile:
    """An ordinary file: every byte is available."""

    def __init__(self, path: Path):
        self.path = path
        self._file = path.open("rb")
        self.length = os.fstat(self._file.fileno()).st_size

    def close(self) -> None:
        self._file.close()

    def check(self, start: int, end: int) -> None:
        pass

    def read(self, start: int, end: int) -> bytes:
        return _exactly(os.pread(self._file.fileno(), end - start, start), start, end)


class ExtentStore:
    """Kept extents of a large logical file, packed into one small data file.

    Not a sparse file: ext4 caps a file at 16 TiB, and the 50 TiB tier must
    not depend on the filesystem. Disk use is the kept bytes, nothing more.
    """

    def __init__(self, directory: Path, logical_length: int):
        self.length = logical_length
        self.data_path = directory / "extents.bin"
        # x: a second store here would otherwise truncate this one's bytes.
        self._data = self.data_path.open("x+b")
        # Sorted, non-overlapping (logical_start, logical_end, physical_start).
        self._index: list[tuple[int, int, int]] = []

    def close(self) -> None:
        self._data.close()

    @property
    def physical_size(self) -> int:
        return self.data_path.stat().st_size

    def add(self, offset: int, data: bytes | memoryview) -> None:
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
                raise Dropped(f"bytes {pos}-{end} were not kept", pos)
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
        data = b"".join(os.pread(fd, n, p) for p, n in self._pieces(start, end))
        return _exactly(data, start, end)


def _exactly(data: bytes, start: int, end: int) -> bytes:
    if len(data) != end - start:
        raise OSError(f"short read at {start}: {len(data)} of {end - start} bytes")
    return data


class ManifestTooLarge(Exception):
    """The TDF's tail did not fit in the sink's rolling buffer."""


class SourceReader:
    """``seek`` and ``read`` over a :class:`Source`, for :mod:`zipinspect`.

    Over an :class:`ExtentStore` that kept the tail, it reads the directory
    and manifest back without another copy of them.
    """

    def __init__(self, source: Source):
        self._source, self._pos = source, 0

    def seek(self, offset: int, /) -> int:
        self._pos = offset
        return offset

    def read(self, n: int, /) -> bytes:
        start = self._pos
        self._pos = max(start, min(start + n, self._source.length))
        return self._source.read(start, self._pos)


class _TailView:
    """The rolling tail buffer, addressed by offsets into the whole stream."""

    def __init__(self, buf: bytearray, base: int):
        self._buf, self._base, self._pos = buf, base, base

    def seek(self, offset: int, /) -> int:
        # The buffer covers the EOCD window, and a TDF's directory fits in it.
        if offset < self._base:
            raise zipinspect.MalformedZipError(
                f"the ZIP points back to {offset}, before the buffered tail "
                f"at {self._base}"
            )
        self._pos = offset
        return offset

    def read(self, n: int, /) -> bytes:
        start = self._pos - self._base
        self._pos += n
        return bytes(self._buf[start : start + n])


#: A local file header with the longest possible name.
_HEAD_MAX = zipinspect.LOCAL_FILE_HEADER_FIXED_SIZE + 0xFFFF


class SparseSink:
    """Keep only the planned extents and the tail of a TDF as it streams past.

    ``write`` the TDF in order, in chunks of any size, then ``close`` to get
    the :class:`ExtentStore`, or ``abort`` to discard it. The tail is
    everything from :func:`data_end` on: java's empty last segment if any,
    the manifest entry, central directory and end records. Its length is not
    known until the stream ends, so the last ``tail_ceiling`` bytes are held
    in memory. A tail longer than that raises :class:`ManifestTooLarge`
    rather than silently keeping part of it; at 50 TiB with 2 MiB segments
    the manifest alone is about 2.6 GB, so size the ceiling to the run.

    ``payload_start``, ``plaintext_length`` and ``segment_size`` are the
    layout ``plan`` was made for. ``payload_start`` is checked against the
    first local header as soon as it streams past, and the rest at close.
    After ``close``, ``tail_start`` is where ``0.payload`` ends.
    """

    tail_start: int | None = None

    def __init__(
        self,
        directory: Path,
        plan: Sequence[tuple[int, int]],
        *,
        tail_ceiling: int,
        payload_start: int,
        plaintext_length: int,
        segment_size: int,
    ):
        self._plan = merge(plan)
        if not self._plan or self._plan[0][0] > 0 or self._plan[0][1] < payload_start:
            raise ValueError(f"the plan does not keep the head, [0, {payload_start})")
        self.payload_start = payload_start
        self._data_end = data_end(
            payload_start=payload_start,
            plaintext_length=plaintext_length,
            segment_size=segment_size,
        )
        # read_central_directory reads this much from the end, whatever the ceiling.
        self._ceiling = max(tail_ceiling, zipinspect.MAX_EOCD_SEARCH)
        self._next = 0  # first plan extent not yet fully written
        self._pos = 0
        self._head: bytearray | None = bytearray()  # until it has been checked
        self._tail = bytearray()
        self._store = ExtentStore(directory, 2**63)  # length unknown until close
        self._done = False

    def write(self, data: bytes) -> None:
        if self._done:
            raise ValueError("write to a closed SparseSink")
        if self._head is not None:
            self._head += data[: _HEAD_MAX - len(self._head)]
            if len(self._head) == _HEAD_MAX:
                self._check_head()
        view = memoryview(data)
        start, end = self._pos, self._pos + len(data)
        i = self._next
        while i < len(self._plan) and self._plan[i][0] < end:
            lo, hi = max(self._plan[i][0], start), min(self._plan[i][1], end)
            if lo < hi:
                self._store.add(lo, view[lo - start : hi - start])
            if self._plan[i][1] > end:
                break
            i += 1
        self._next = i
        self._pos = end
        self._tail += data
        del self._tail[: -self._ceiling]

    def _check_head(self) -> None:
        assert self._head is not None
        head, self._head = self._head, None
        name, start = zipinspect.read_local_file_header(io.BytesIO(head), 0)
        # A rezipped TDF can put the manifest first; close() checks those.
        if name == "0.payload":
            self._check_payload_start(start)

    def _check_payload_start(self, start: int) -> None:
        if start != self.payload_start:
            raise ValueError(
                f"payload_start is {self.payload_start}, but 0.payload's data "
                f"starts at {start}"
            )

    def close(self) -> ExtentStore:
        if self._done:
            raise ValueError("SparseSink is already closed")
        try:
            store = self._finish()
        except BaseException:
            self.abort()
            raise
        self._done = True
        return store

    def abort(self, *, unlink: bool = True) -> None:
        """Close the store and, unless ``unlink`` is false, delete its file.

        A no-op once closed: a store ``close`` returned is the caller's.
        """
        if self._done:
            return
        self._done = True
        self._tail = bytearray()
        self._store.close()
        if unlink:
            self._store.data_path.unlink(missing_ok=True)

    def _finish(self) -> ExtentStore:
        if self._head is not None:
            self._check_head()
        total = self._pos
        if self._plan[-1][1] > total:
            raise ValueError(
                f"stream ended at {total}, before planned extent {self._plan[-1]}"
            )
        base = total - len(self._tail)
        cd = zipinspect.read_central_directory(_TailView(self._tail, base), total)
        payload = next((e for e in cd.entries if e.name == "0.payload"), None)
        if payload is None:
            raise zipinspect.MalformedZipError("no 0.payload entry")
        self._store.length = total
        at = payload.local_header_offset
        assert at < self.payload_start, "the payload's local header is in the head"
        _, start = zipinspect.read_local_file_header(SourceReader(self._store), at)
        self._check_payload_start(start)
        self.tail_start = start + payload.compressed_size
        if not 0 <= self.tail_start - self._data_end <= PAYLOAD_GCM_OVERHEAD:
            raise ValueError(
                f"0.payload ends at {self.tail_start}, but its last data segment "
                f"at {self._data_end}: plaintext_length or segment_size is wrong"
            )
        if self._data_end < base:
            raise ManifestTooLarge(
                f"the tail starts at {self._data_end}, but only bytes from {base} "
                "were buffered; raise tail_ceiling"
            )
        self._store.add(self._data_end, memoryview(self._tail)[self._data_end - base :])
        self._tail = bytearray()
        return self._store


class Request(NamedTuple):
    """One answered request.

    ``start`` and ``end`` are the half-open byte range the ``Range`` header
    resolved to (the whole source for a plain GET); None when there was
    none. ``dropped_at`` is the first byte not kept, on a 410 or a body cut
    short.
    """

    method: str
    range: str | None
    status: int
    bytes_served: int
    start: int | None = None
    end: int | None = None
    dropped_at: int | None = None


_RANGE = re.compile(r"bytes=(\d*)-(\d*)")
_EXPOSED = "Content-Range, Content-Length, Accept-Ranges"


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


def _disconnected(exc: BaseException) -> bool:
    # EPROTOTYPE is macOS's EPIPE when the peer goes away mid-send.
    return isinstance(exc, ConnectionError) or (
        isinstance(exc, OSError) and exc.errno in (errno.ENOTCONN, errno.EPROTOTYPE)
    )


class _Server(ThreadingHTTPServer):
    """Tracks open connections and handler threads, and what the handlers raised."""

    def __init__(self, handler: type[BaseHTTPRequestHandler]):
        super().__init__(("127.0.0.1", 0), handler)
        self.name = f"rangeserve-{self.server_address[1]}"
        self.errors: list[Exception] = []
        self._lock = threading.Lock()
        self._conns: set[socket.socket] = set()
        self._handlers: list[threading.Thread] = []

    def process_request(self, request, client_address) -> None:
        assert isinstance(request, socket.socket)  # TCP
        t = threading.Thread(
            target=self.process_request_thread,
            args=(request, client_address),
            name=f"{self.name}-conn",
            daemon=True,
        )
        with self._lock:
            self._conns.add(request)
            self._handlers = [h for h in self._handlers if h.is_alive()] + [t]
        t.start()

    def shutdown_request(self, request) -> None:
        with self._lock:
            self._conns.discard(request)
        super().shutdown_request(request)

    def handle_error(self, request, client_address) -> None:
        exc = sys.exception()
        if isinstance(exc, Exception) and not _disconnected(exc):
            self.errors.append(exc)
            super().handle_error(request, client_address)

    def close_and_join(self, timeout: float) -> list[threading.Thread]:
        """Shut every open connection, then join the handlers; return the stuck."""
        with self._lock:
            conns, handlers = list(self._conns), list(self._handlers)
        for conn in conns:
            with suppress(OSError):
                conn.shutdown(socket.SHUT_RDWR)
        deadline = time.monotonic() + timeout
        for h in handlers:
            h.join(max(0.0, deadline - time.monotonic()))
        self.server_close()
        return [h for h in handlers if h.is_alive()]


@contextmanager
def serve(
    source: Source, name: str = "payload.tdf"
) -> Iterator[tuple[str, list[Request]]]:
    """Serve ``source`` at ``/name`` on an ephemeral loopback port.

    Any path gets the same bytes; ``name`` is what a client takes the file to
    be called. CORS is open, for the browser-based SDK.

    Yields ``(url, log)``. ``log`` gains one :class:`Request` as each response
    finishes. On exit, idle keep-alive connections are shut and every handler
    thread is joined, so ``log`` is complete and nothing still reads
    ``source``. A handler that raised, or would not stop, fails the ``with``
    block with an :class:`ExceptionGroup`.
    """
    log: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            pass  # ``log`` is the access log; log_error still reaches stderr.

        def end_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", _EXPOSED)
            super().end_headers()

        def _reply(
            self, status: int, body: bytes = b"", *, request: Request | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            if status == 416:
                self.send_header("Content-Range", f"bytes */{source.length}")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            log.append(
                request or Request(self.command, self.headers["Range"], status, 0)
            )

        def _read(self, start: int, end: int) -> bytes:
            return _exactly(source.read(start, end), start, end)

        def do_HEAD(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(source.length))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            log.append(Request("HEAD", self.headers["Range"], 200, 0))

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Range")
            self.end_headers()
            log.append(Request("OPTIONS", self.headers["Range"], 204, 0))

        def do_GET(self) -> None:
            header = self.headers["Range"]
            start, end, status = 0, source.length, 200
            if header is not None:
                try:
                    resolved = _parse_range(header, source.length)
                except ValueError as e:
                    return self._reply(400, str(e).encode())
                if resolved is None:
                    return self._reply(416)
                (start, end), status = resolved, 206
            try:
                source.check(start, end)
                chunk = self._read(start, min(start + _CHUNK, end))
            except Dropped as e:
                return self._reply(
                    410,
                    str(e).encode(),
                    request=Request("GET", header, 410, 0, start, end, e.offset),
                )
            self.send_response(status)
            self.send_header("Content-Length", str(end - start))
            self.send_header("Accept-Ranges", "bytes")
            if status == 206:
                self.send_header(
                    "Content-Range", f"bytes {start}-{end - 1}/{source.length}"
                )
            self.end_headers()
            served, dropped_at = 0, None
            try:
                while True:
                    self.wfile.write(chunk)
                    served += len(chunk)
                    if (pos := start + served) == end:
                        break
                    chunk = self._read(pos, min(pos + _CHUNK, end))
            except Dropped as e:
                # Too late for a 410: cut the body short so the client sees it.
                dropped_at = e.offset
                self.close_connection = True
            finally:
                log.append(
                    Request("GET", header, status, served, start, end, dropped_at)
                )

    server = _Server(Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name=server.name,
        daemon=True,
    )
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}/{urllib.parse.quote(name)}", log
    finally:
        server.shutdown()
        thread.join()
        if stuck := server.close_and_join(_JOIN_TIMEOUT):
            server.errors.append(
                TimeoutError(f"{len(stuck)} handler threads outlived serve()")
            )
        if server.errors:
            raise ExceptionGroup("rangeserve handler errors", server.errors)
