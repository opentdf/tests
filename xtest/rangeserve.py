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
