"""Stream an SDK CLI's input and output instead of storing them (DSPX-5108).

A 100 GiB-50 TiB test cannot keep a plaintext, a ciphertext and a decrypted
copy on the runner. Here the plaintext is generated on demand and fed to the
CLI through a FIFO, and the CLI's output is drained from another FIFO into a
consumer that counts it and keeps only bounded evidence.

- :class:`Plaintext` is the canonical generator. Any ``(offset, length)`` is
  computable directly, at GB/s, and it is a :class:`rangeserve.Source`, so it
  can be served over HTTP or mounted as a file.
- :class:`CountedSink` counts a TDF as it passes, keeps its last
  ``tail_ceiling`` bytes, and at close parses the central directory and
  manifest out of them. Every byte goes on, unchanged, to an optional
  downstream consumer such as :class:`rangeserve.SparseSink`.
- :class:`Validator` checks decrypted output against the generator by position.
- :func:`run` runs one CLI invocation with those attached, under a timeout and
  a :class:`Budget`, and records wall time, peak RSS and peak scratch use.
- :func:`probe` finds which of a FIFO and a regular file each CLI accepts as
  input and as output, falling back until a route works.

Nothing here alters what a CLI writes. Every way a run can be wrong -- a short
source, a CLI that stops reading, a failing consumer, a wrong byte count, a
non-zero exit, a hang -- raises a :class:`StreamError` subclass.
"""

from __future__ import annotations

import errno
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, ExitStack, closing
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Literal, Protocol

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import zipinspect
from perf.measure import _LAUNCHER, _RSS_SCALE, _read_result
from rangeserve import (
    PAYLOAD_GCM_OVERHEAD,
    ExtentStore,
    FullFile,
    ManifestTooLarge,
    Source,
    SourceReader,
    SparseSink,
)

_CHUNK = 1 << 20
_POLL_S = 0.01
_SCRATCH_SAMPLE_S = 0.05
#: Per stream, head and tail each. The go shim alone echoes a long command line.
_CAPTURE_BYTES = 16 << 10
#: How long an I/O thread may outlive the CLI. Only a descendant still holding
#: a FIFO open after the CLI exits can use it up.
_JOIN_S = 30.0
_LAUNCHER_GRACE_S = 30.0
#: How long the launcher gets to kill the CLI's group after SIGTERM.
_TERM_GRACE_S = 10.0

#: Holds the manifest of a 100 GiB TDF with 2 MiB segments (~5 MB) many times
#: over. At 50 TiB the manifest is ~2.6 GB; size the ceiling to the run.
DEFAULT_TAIL_CEILING = 64 << 20

#: A local file header with the longest possible name; enough to find where
#: the first entry's data starts.
_HEAD_MAX = zipinspect.LOCAL_FILE_HEADER_FIXED_SIZE + 0xFFFF


class StreamError(Exception):
    """A streamed run did not do exactly what was asked."""


class ShortInput(StreamError):
    """The source produced fewer bytes than its declared length."""


class EarlyEOF(StreamError):
    """The CLI stopped reading its input before the end."""


class SinkError(StreamError):
    """The output consumer raised."""


class ChildFailed(StreamError):
    """The CLI could not start, exited non-zero, or wrote no output."""


class StreamTimeout(StreamError):
    """The CLI ran past the budget's timeout and was killed."""


class WrongLength(StreamError):
    """The output holds more or fewer bytes than it should."""


class ContentMismatch(StreamError):
    """Decrypted output differs from the plaintext."""


class BadOutput(StreamError):
    """The output could not be parsed as what it claims to be."""


class BudgetExceeded(StreamError):
    """The run used more memory or scratch than the budget allows."""


# --- input ------------------------------------------------------------------


class Plaintext:
    """Deterministic bytes, computable at any offset: an AES-128-CTR keystream.

    Block ``i`` is ``AES(key, i)``, so ``self(offset, n)`` starts the counter
    at ``offset // 16`` and never generates what precedes it. A 128-bit
    counter reaches far past 50 TiB. Not the line format ``pt_file`` writes,
    which breaks at ~931 GiB (DSPX-4735).

    Call it as ``(offset, length) -> bytes``, or use it as a
    :class:`rangeserve.Source`.
    """

    def __init__(self, length: int, *, seed: bytes = b"DSPX-5108"):
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        self.length = length
        self._key = hashlib.sha256(seed).digest()[:16]

    def __call__(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.length:
            raise ValueError(
                f"bytes {offset}-{offset + length} are outside 0-{self.length}"
            )
        block, skip = divmod(offset, 16)
        ctr = modes.CTR(block.to_bytes(16, "big"))
        enc = Cipher(algorithms.AES(self._key), ctr).encryptor()
        return enc.update(bytes(skip + length))[skip:]

    def check(self, start: int, end: int) -> None:
        pass

    def read(self, start: int, end: int) -> bytes:
        return self(start, end - start)


# --- output -----------------------------------------------------------------


class Consumer[T](Protocol):
    """Anything fed with ``write`` in stream order and finished with ``close``.

    An optional ``abort()`` is called instead of ``close`` when the run fails.
    """

    def write(self, data: bytes, /) -> object: ...

    def close(self) -> T: ...


def _abort(consumer: object) -> None:
    abort = getattr(consumer, "abort", None)
    if callable(abort):
        abort()


class FileSink:
    """Keep a full copy, for a control small enough to store. Abort removes it."""

    def __init__(self, path: Path):
        self.path = path
        self._f = path.open("wb")

    def write(self, data: bytes) -> None:
        self._f.write(data)

    def close(self) -> Path:
        self._f.close()
        return self.path

    def abort(self) -> None:
        self._f.close()
        self.path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class ManifestSummary:
    """A TDF manifest with its per-segment array reduced to counts and sizes.

    A segment with no explicit size counts at the manifest-level default, as
    readers resolve it.
    """

    size: int
    schema_version: str | None
    algorithm: str | None
    key_access_types: tuple[str, ...]
    segment_hash_alg: str | None
    root_signature_alg: str | None
    segment_count: int
    segment_size_default: int
    encrypted_segment_size_default: int
    #: ``(plaintext segment size, count)``, most common first.
    segment_sizes: tuple[tuple[int, int], ...]
    #: Segments that left a size to the manifest-level default.
    elided_sizes: int
    plaintext_length: int
    encrypted_length: int

    @classmethod
    def parse(cls, raw: bytes) -> ManifestSummary:
        m = json.loads(raw)
        ei = m.get("encryptionInformation") or {}
        ii = ei.get("integrityInformation") or {}
        seg_default = int(ii.get("segmentSizeDefault") or 0)
        enc_default = int(ii.get("encryptedSegmentSizeDefault") or 0)
        sizes: Counter[int] = Counter()
        elided = plaintext = encrypted = 0
        segments = ii.get("segments") or []
        for s in segments:
            pt, ct = s.get("segmentSize"), s.get("encryptedSegmentSize")
            elided += pt is None or ct is None
            pt = seg_default if pt is None else int(pt)
            ct = enc_default if ct is None else int(ct)
            sizes[pt] += 1
            plaintext += pt
            encrypted += ct
        return cls(
            size=len(raw),
            schema_version=m.get("schemaVersion"),
            algorithm=(ei.get("method") or {}).get("algorithm"),
            key_access_types=tuple(k.get("type", "") for k in ei.get("keyAccess", [])),
            segment_hash_alg=ii.get("segmentHashAlg"),
            root_signature_alg=(ii.get("rootSignature") or {}).get("alg"),
            segment_count=len(segments),
            segment_size_default=seg_default,
            encrypted_segment_size_default=enc_default,
            segment_sizes=tuple(sizes.most_common()),
            elided_sizes=elided,
            plaintext_length=plaintext,
            encrypted_length=encrypted,
        )


@dataclass(frozen=True, slots=True)
class TdfEvidence:
    """What a :class:`CountedSink` keeps of a TDF: sizes and structure, no data."""

    byte_count: int
    central_directory: zipinspect.CentralDirectory
    payload_length: int
    #: Where ``0.payload``'s data starts: the ``payload_start`` a
    #: :class:`rangeserve.SparseSink` plan for this route needs. None if the
    #: payload is not the first entry.
    payload_start: int | None
    manifest: ManifestSummary

    def check(self, plaintext_length: int) -> None:
        """Raise unless this is a consistent TDF of ``plaintext_length`` bytes."""
        m = self.manifest
        if m.plaintext_length != plaintext_length:
            raise WrongLength(
                f"manifest segments hold {m.plaintext_length} plaintext bytes; "
                f"{plaintext_length} were sent"
            )
        if m.encrypted_length != self.payload_length:
            raise WrongLength(
                f"manifest segments hold {m.encrypted_length} ciphertext bytes, "
                f"but 0.payload is {self.payload_length}"
            )
        overhead = self.payload_length - plaintext_length
        if overhead != PAYLOAD_GCM_OVERHEAD * m.segment_count:
            raise WrongLength(
                f"0.payload is {overhead} bytes longer than the plaintext; "
                f"{m.segment_count} AES-GCM segments account for "
                f"{PAYLOAD_GCM_OVERHEAD * m.segment_count}"
            )
        try:
            zipinspect.assert_offsets_are_consistent(self.central_directory)
        except AssertionError as e:
            raise BadOutput(str(e)) from e


class _TailView:
    """The rolling tail, addressed by offsets into the whole stream."""

    def __init__(self, buf: bytearray, total: int):
        self._buf, self._base = buf, total - len(buf)
        self._pos = self._base

    def seek(self, offset: int, /) -> int:
        if offset < self._base:
            raise ManifestTooLarge(
                f"the TDF tail reaches back to {offset}, but only bytes from "
                f"{self._base} were kept; raise tail_ceiling"
            )
        self._pos = offset
        return offset

    def read(self, n: int, /) -> bytes:
        start = self._pos - self._base
        self._pos += n
        with memoryview(self._buf) as view:
            return bytes(view[start : start + n])


def _entry_data(
    f: zipinspect.Seekable, entry: zipinspect.CentralDirectoryEntry
) -> bytes:
    _, start = zipinspect.read_local_file_header(f, entry.local_header_offset)
    f.seek(start)
    data = f.read(entry.compressed_size)
    if len(data) != entry.compressed_size:
        raise zipinspect.MalformedZipError(
            f"{entry.name!r} is {entry.compressed_size} bytes, but only "
            f"{len(data)} follow its local header"
        )
    return data


def _evidence(
    f: zipinspect.Seekable, total: int, head: bytes | bytearray
) -> TdfEvidence:
    cd = zipinspect.read_central_directory(f, total)
    by_name = {e.name: e for e in cd.entries}
    payload = by_name.get("0.payload")
    manifest = by_name.get("0.manifest.json")
    if payload is None or manifest is None:
        raise zipinspect.MalformedZipError(
            f"no 0.payload and 0.manifest.json among {sorted(by_name)}"
        )
    start = None
    at = payload.local_header_offset
    if at + zipinspect.LOCAL_FILE_HEADER_FIXED_SIZE <= len(head):
        _, start = zipinspect.read_local_file_header(io.BytesIO(head), at)
    return TdfEvidence(
        byte_count=total,
        central_directory=cd,
        payload_length=payload.compressed_size,
        payload_start=start,
        manifest=ManifestSummary.parse(_entry_data(f, manifest)),
    )


class CountedSink:
    """Count a TDF as it streams past, and keep bounded evidence of it.

    The last ``tail_ceiling`` bytes are held in memory: for any TDF whose
    manifest fits, that is the manifest, central directory and end records.
    :meth:`close` parses them into a :class:`TdfEvidence`, or raises
    :class:`ManifestTooLarge` rather than summarising part of a manifest. With
    ``plaintext_length`` it also checks the TDF holds exactly that many bytes.

    Each chunk is passed to ``downstream`` before ``write`` returns, so a slow
    downstream backpressures the CLI rather than buffering here.

    A :class:`rangeserve.SparseSink` downstream keeps the tail itself, so this
    holds none and parses its store instead; its ``tail_ceiling`` is the one
    that counts. Its layout must match the route being run: go writes a ZIP64
    local header when it cannot measure its input, the FIFO route, which puts
    ``payload_start`` at 59 rather than 39. :attr:`TdfEvidence.payload_start`
    reports what a run produced, and the SparseSink fails within the first
    64 KiB on a mismatch.
    """

    def __init__(
        self,
        *,
        tail_ceiling: int = DEFAULT_TAIL_CEILING,
        downstream: Consumer[Any] | None = None,
        plaintext_length: int | None = None,
    ):
        # The EOCD search reads up to this much from the end, whatever the ceiling.
        self._ceiling = max(tail_ceiling, zipinspect.MAX_EOCD_SEARCH)
        self._head = bytearray()
        self._tail = bytearray()
        self._downstream = downstream
        self._sparse = downstream if isinstance(downstream, SparseSink) else None
        self._plaintext_length = plaintext_length
        self.count = 0
        #: What ``downstream.close()`` returned, once closed.
        self.downstream_result: object = None

    def write(self, data: bytes) -> None:
        self.count += len(data)
        if len(self._head) < _HEAD_MAX:
            self._head += data[: _HEAD_MAX - len(self._head)]
        if self._sparse is None:
            self._tail += data
            del self._tail[: -self._ceiling]
        if self._downstream is not None:
            self._downstream.write(data)

    def close(self) -> TdfEvidence:
        store: ExtentStore | None = None
        try:
            if self._sparse is not None:
                # Checks its layout and keeps the tail; aborts itself if not.
                store = self._sparse.close()
                f: zipinspect.Seekable = SourceReader(store)
            else:
                f = _TailView(self._tail, self.count)
            evidence = _evidence(f, self.count, self._head)
            if self._plaintext_length is not None:
                evidence.check(self._plaintext_length)
        except (zipinspect.MalformedZipError, ValueError) as e:
            self._discard(store)
            raise BadOutput(f"TDF rejected: {e}") from e
        except BaseException:
            self._discard(store)
            raise
        self._tail = bytearray()
        if store is not None:
            self.downstream_result = store
        elif self._downstream is not None:
            self.downstream_result = self._downstream.close()
        return evidence

    def _discard(self, store: ExtentStore | None) -> None:
        if store is None:
            self.abort()
        else:
            # A closed SparseSink's abort is a no-op: the store is ours now.
            store.close()
            store.data_path.unlink(missing_ok=True)

    def abort(self) -> None:
        if self._downstream is not None:
            _abort(self._downstream)


class Validator:
    """Compare a stream with ``expected`` by position, and demand its exact length."""

    def __init__(self, expected: Callable[[int, int], bytes], length: int):
        self._expected = expected
        self.length = length
        self.count = 0

    def write(self, data: bytes) -> None:
        end = self.count + len(data)
        if end > self.length:
            raise WrongLength(f"output runs past {self.length} bytes, to {end}")
        want = self._expected(self.count, len(data))
        if data != want:
            i = next(
                i for i, (a, b) in enumerate(zip(data, want, strict=True)) if a != b
            )
            raise ContentMismatch(
                f"output differs from the plaintext at byte {self.count + i}"
            )
        self.count = end

    def close(self) -> int:
        if self.count != self.length:
            raise WrongLength(f"output ended at {self.count} of {self.length} bytes")
        return self.count


# --- running a CLI ----------------------------------------------------------


#: ``(src, dst) -> (argv, env overrides)``, e.g. ``tdfs.SDK.encrypt_command``.
Command = Callable[[Path, Path], tuple[list[str], dict[str, str]]]

#: A seekable local view of a source, e.g. the DSPX-5543 NFS mount.
Mount = Callable[[Source], AbstractContextManager[Path]]


@dataclass(frozen=True, slots=True)
class FifoInput:
    """Feed ``source`` to the CLI through a FIFO named ``name``."""

    source: Source
    name: str = "input"


@dataclass(frozen=True, slots=True)
class FileInput:
    """An existing regular file: a stored ciphertext, or a mounted source."""

    path: Path


@dataclass(frozen=True, slots=True)
class MaterializedInput:
    """Write ``source`` out as a regular file first. Costs its length in scratch."""

    source: Source
    name: str = "input"


@dataclass(frozen=True, slots=True)
class FifoOutput[T]:
    """Drain the CLI's output from a FIFO named ``name`` into ``consumer``."""

    consumer: Consumer[T]
    name: str = "output"


@dataclass(frozen=True, slots=True)
class FileOutput[T]:
    """Let the CLI write a regular file, then replay it into ``consumer``.

    Costs the whole output in scratch, briefly.
    """

    consumer: Consumer[T]
    name: str = "output"


type Input = FifoInput | FileInput | MaterializedInput
type Output[T] = FifoOutput[T] | FileOutput[T]


def parse_bytes(text: str) -> int:
    """``"2GiB"`` -> 2147483648. Binary units only, so there is no ambiguity."""
    units = {"TiB": 1 << 40, "GiB": 1 << 30, "MiB": 1 << 20, "KiB": 1 << 10, "B": 1}
    t = text.strip()
    for suffix, scale in units.items():
        if t.endswith(suffix):
            return int(float(t.removesuffix(suffix)) * scale)
    return int(t)


@dataclass(frozen=True, slots=True)
class Budget:
    """Resource limits for one CLI invocation on the target device.

    ``None`` records without limiting. Exceeding a limit fails the run, and
    the scratch limit is enforced while the CLI runs, before a full disk does.
    """

    timeout_s: float = 600.0
    max_rss_bytes: int | None = None
    max_scratch_bytes: int | None = None

    @classmethod
    def from_env(cls, timeout_s: float = 600.0) -> Budget:
        """Read ``XT_STREAM_TIMEOUT`` (s), ``XT_STREAM_MAX_RSS``, ``XT_STREAM_MAX_SCRATCH``."""
        rss = os.environ.get("XT_STREAM_MAX_RSS")
        scratch = os.environ.get("XT_STREAM_MAX_SCRATCH")
        return cls(
            timeout_s=float(os.environ.get("XT_STREAM_TIMEOUT") or timeout_s),
            max_rss_bytes=parse_bytes(rss) if rss else None,
            max_scratch_bytes=parse_bytes(scratch) if scratch else None,
        )


@dataclass(frozen=True, slots=True)
class Run[T]:
    """One CLI invocation and what it cost."""

    argv: tuple[str, ...]
    #: What the output consumer's ``close()`` returned.
    result: T
    bytes_in: int
    bytes_out: int
    wall_s: float
    cpu_s: float
    #: Largest single process in the CLI's tree, as :mod:`perf.measure` reports.
    peak_rss_bytes: int
    #: The launcher's own RSS; a reading at or below it is censored.
    rss_floor_bytes: int
    #: The whole scratch root, including files kept from earlier runs.
    peak_scratch_bytes: int
    #: The CLI's ``TMPDIR``. Near ``bytes_in`` means it spooled its input.
    peak_tmp_bytes: int
    stderr: str


class _Pump:
    """State shared between the run loop and its I/O threads."""

    def __init__(self) -> None:
        self.child_done = threading.Event()
        self.abort = threading.Event()
        self._lock = threading.Lock()
        self.cause: BaseException | None = None
        self.bytes_in = 0
        self.bytes_out = 0
        self.input_opened = False
        self.input_closed_early = False

    def fail(self, e: BaseException) -> None:
        with self._lock:
            if self.cause is None:
                self.cause = e
        self.abort.set()

    def thread(self, target: Callable[[], None]) -> threading.Thread:
        def body() -> None:
            try:
                target()
            # Signals only reach the main thread, so Exception is everything a
            # worker can raise that the run must report.
            except Exception as e:
                self.fail(e)

        t = threading.Thread(target=body, daemon=True)
        t.start()
        return t


def _feed(path: Path, source: Source, pump: _Pump) -> None:
    """Write ``source`` into the FIFO once the CLI opens it."""
    fd = None
    while fd is None:
        try:
            # Non-blocking so a CLI that never opens its input cannot hang us:
            # ENXIO until a reader exists.
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as e:
            if e.errno != errno.ENXIO:
                raise
            if pump.child_done.wait(_POLL_S) or pump.abort.is_set():
                return
    os.set_blocking(fd, True)
    pump.input_opened = True
    try:
        pos, end = 0, source.length
        while pos < end and not pump.abort.is_set():
            n = min(_CHUNK, end - pos)
            data = source.read(pos, pos + n)
            if len(data) != n:
                raise ShortInput(
                    f"source gave {len(data)} of {n} bytes at {pos}, "
                    f"short of its declared {end}"
                )
            view = memoryview(data)
            while view:
                try:
                    written = os.write(fd, view)
                except BrokenPipeError:
                    pump.input_closed_early = True
                    return
                pump.bytes_in += written
                view = view[written:]
            pos += n
    finally:
        os.close(fd)


def _deliver(data: bytes, consumer: Consumer[object], pump: _Pump) -> None:
    pump.bytes_out += len(data)
    try:
        consumer.write(data)
    except StreamError:
        raise
    except Exception as e:
        raise SinkError(
            f"output consumer failed at byte {pump.bytes_out}: {e!r}"
        ) from e


def _drain(path: Path, consumer: Consumer[object], pump: _Pump) -> None:
    """Read the FIFO into ``consumer`` until the CLI closes it."""
    # Non-blocking open always succeeds, and lets the CLI's own open succeed.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        # Until a writer appears, a read returns b"" -- the same as after it
        # has gone. EAGAIN or data is the first sign it has arrived.
        while True:
            done = pump.child_done.is_set()
            try:
                data = os.read(fd, _CHUNK)
            except BlockingIOError:
                break
            if data:
                _deliver(data, consumer, pump)
                break
            if done or pump.abort.is_set():
                return
            time.sleep(_POLL_S)
        os.set_blocking(fd, True)
        while not pump.abort.is_set() and (data := os.read(fd, _CHUNK)):
            _deliver(data, consumer, pump)
    finally:
        os.close(fd)


class _Capture:
    """The first and last few KiB of a stream, and how much fell between."""

    def __init__(self, stream: IO[bytes], pump: _Pump):
        self._fd = stream.fileno()
        self.head, self.tail, self.total = bytearray(), bytearray(), 0
        self.thread = pump.thread(self._run)

    def _run(self) -> None:
        while chunk := os.read(self._fd, 1 << 16):
            self.total += len(chunk)
            room = _CAPTURE_BYTES - len(self.head)
            if room > 0:
                self.head += chunk[:room]
                chunk = chunk[room:]
            self.tail += chunk
            del self.tail[:-_CAPTURE_BYTES]

    def text(self) -> str:
        dropped = self.total - len(self.head) - len(self.tail)
        gap = f"\n[... {dropped} bytes elided ...]\n".encode() if dropped else b""
        return (bytes(self.head) + gap + bytes(self.tail)).decode(errors="replace")


def _du(root: Path) -> int:
    """Apparent size of the regular files under ``root``; nothing here is sparse."""
    total = 0
    for dirpath, _, files in os.walk(root):
        for name in files:
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


class _ScratchMeter:
    def __init__(self, root: Path, tmp: Path, limit: int | None, pump: _Pump):
        self._root, self._tmp, self._limit, self._pump = root, tmp, limit, pump
        self.peak = self.peak_tmp = 0

    def sample(self) -> None:
        total = _du(self._root)
        self.peak = max(self.peak, total)
        self.peak_tmp = max(self.peak_tmp, _du(self._tmp))
        if self._limit is not None and total > self._limit:
            self._pump.fail(
                BudgetExceeded(
                    f"scratch reached {total} bytes, over the budget's {self._limit}"
                )
            )

    def start(self) -> threading.Thread:
        def loop() -> None:
            while not self._pump.child_done.wait(_SCRATCH_SAMPLE_S):
                self.sample()

        return self._pump.thread(loop)


def _child_env(overrides: Mapping[str, str], tmp: Path) -> dict[str, str]:
    """The CLI's environment, with every temp-file default pointed at ``tmp``."""
    env = dict(os.environ) | dict(overrides)
    # Where the go shim's `go run` links otdfctl: build output, not a spool.
    env.setdefault("GOTMPDIR", tempfile.gettempdir())
    env["TMPDIR"] = str(tmp)
    # The JVM ignores TMPDIR.
    java = env.get("JAVA_TOOL_OPTIONS", "")
    env["JAVA_TOOL_OPTIONS"] = f"{java} -Djava.io.tmpdir={tmp}".strip()
    return env


def _materialize(source: Source, path: Path) -> None:
    with path.open("wb") as f:
        for pos in range(0, source.length, _CHUNK):
            end = min(pos + _CHUNK, source.length)
            data = source.read(pos, end)
            if len(data) != end - pos:
                raise ShortInput(
                    f"source gave {len(data)} of {end - pos} bytes at {pos}, "
                    f"short of its declared {source.length}"
                )
            f.write(data)


def _last_line(text: str) -> str:
    """The last stderr line worth quoting: not a Java or Node stack frame."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    said = [ln for ln in lines if not ln.startswith(("at ", "..."))] or lines
    return said[-1][:300] if said else "(no stderr)"


def _stop(proc: subprocess.Popen[bytes]) -> None:
    """Stop the launcher, letting it take the CLI's process group with it."""
    proc.terminate()
    try:
        proc.wait(_TERM_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()  # Wedged; its CLI may outlive it.
        proc.wait()


def _wait(proc: subprocess.Popen[bytes], pump: _Pump, timeout_s: float) -> bool:
    """Wait for the launcher; True if an abort made us stop it."""
    backstop = time.monotonic() + timeout_s + _LAUNCHER_GRACE_S
    terminated = False
    while True:
        try:
            proc.wait(timeout=0.05)
            return terminated
        except subprocess.TimeoutExpired:
            pass
        if pump.abort.is_set() and not terminated:
            # The launcher kills the CLI's process group on SIGTERM.
            proc.terminate()
            terminated = True
        if time.monotonic() > backstop:
            _stop(proc)


def run[T](
    command: Command,
    *,
    src: Input,
    dst: Output[T],
    scratch: Path,
    budget: Budget = Budget(),
) -> Run[T]:
    """Run ``command(src_path, dst_path)`` once, streaming both ends.

    FIFOs, materialised inputs, file outputs and the CLI's ``TMPDIR`` live in
    a fresh directory under ``scratch``, removed on every path. The consumer
    is closed only on success, and aborted otherwise.

    Raises:
        StreamError: a subclass naming the first thing that went wrong.
    """
    pump = _Pump()
    rundir: Path | None = None
    proc: subprocess.Popen[bytes] | None = None
    captures: list[tuple[IO[bytes], threading.Thread]] = []
    succeeded = False
    try:
        scratch.mkdir(parents=True, exist_ok=True)
        rundir = Path(tempfile.mkdtemp(prefix="run-", dir=scratch))
        tmp = rundir / "tmp"
        tmp.mkdir()
        match src:
            case FifoInput(name=name):
                src_path = rundir / name
                os.mkfifo(src_path)
            case MaterializedInput(source=source, name=name):
                src_path = rundir / name
                _materialize(source, src_path)
            case FileInput(path=path):
                # Shims that cd before reading their arguments need it absolute.
                src_path = path.absolute()
        dst_path = rundir / dst.name
        if isinstance(dst, FifoOutput):
            os.mkfifo(dst_path)
        argv, overrides = command(src_path, dst_path)
        meter = _ScratchMeter(scratch, tmp, budget.max_scratch_bytes, pump)
        meter.sample()

        result_path = rundir / "rusage"
        proc = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                str(_LAUNCHER),
                str(result_path),
                repr(float(budget.timeout_s)),
                *argv,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_child_env(overrides, tmp),
        )
        assert proc.stdout is not None and proc.stderr is not None
        out, err = _Capture(proc.stdout, pump), _Capture(proc.stderr, pump)
        captures = [(proc.stdout, out.thread), (proc.stderr, err.thread)]
        threads = [out.thread, err.thread, meter.start()]
        if isinstance(src, FifoInput):
            source = src.source
            threads.append(pump.thread(lambda: _feed(src_path, source, pump)))
        if isinstance(dst, FifoOutput):
            consumer = dst.consumer
            threads.append(pump.thread(lambda: _drain(dst_path, consumer, pump)))

        terminated = _wait(proc, pump, budget.timeout_s)
        pump.child_done.set()
        deadline = time.monotonic() + _JOIN_S
        for t in threads:
            t.join(max(0.0, deadline - time.monotonic()))
        stuck = sum(t.is_alive() for t in threads)
        meter.sample()
        stderr = err.text()

        if pump.cause is not None:
            pump.cause.add_note(f"CLI stderr ends: {_last_line(stderr)}")
            raise pump.cause
        if terminated:
            raise StreamError("run aborted without a recorded cause")
        reading = _read_result(result_path, argv)
        exit_code = os.waitstatus_to_exitcode(reading.status)
        if reading.exec_errno:
            raise ChildFailed(
                f"could not start {argv[0]!r}: {os.strerror(reading.exec_errno)}"
            )
        if reading.timed_out:
            raise StreamTimeout(
                f"killed after {budget.timeout_s:g}s; stderr ends: {_last_line(stderr)}"
            )
        if exit_code != 0:
            raise ChildFailed(
                f"exited {exit_code}: {_last_line(stderr)}\n--- stderr ---\n{stderr}"
            )
        if stuck:
            raise StreamError(
                f"{stuck} I/O thread(s) still blocked {_JOIN_S:g}s after the CLI "
                "exited; a descendant is holding a FIFO open"
            )

        if isinstance(src, FifoInput):
            if not pump.input_opened:
                raise EarlyEOF("the CLI exited 0 without opening its input")
            if pump.input_closed_early or pump.bytes_in != src.source.length:
                raise EarlyEOF(
                    f"the CLI stopped reading after {pump.bytes_in} of "
                    f"{src.source.length} bytes"
                )
            bytes_in = pump.bytes_in
        else:
            bytes_in = src_path.stat().st_size

        if isinstance(dst, FifoOutput):
            try:
                still_fifo = stat.S_ISFIFO(os.lstat(dst_path).st_mode)
            except FileNotFoundError:
                still_fifo = False
            if not still_fifo:
                raise ChildFailed(
                    "the CLI replaced or removed its output FIFO, so its "
                    "output cannot be streamed"
                )
        else:
            if not dst_path.is_file():
                raise ChildFailed("the CLI exited 0 but wrote no output file")
            # The replay briefly holds the output twice; the meter must see it.
            next_sample = 0.0
            with dst_path.open("rb") as f:
                while data := f.read(_CHUNK):
                    _deliver(data, dst.consumer, pump)
                    if time.monotonic() >= next_sample:
                        meter.sample()
                        next_sample = time.monotonic() + _SCRATCH_SAMPLE_S
                        if pump.cause is not None:
                            raise pump.cause
            meter.sample()
            if pump.cause is not None:
                raise pump.cause
            dst_path.unlink()
        try:
            result = dst.consumer.close()
        except StreamError, ManifestTooLarge:
            # A ceiling too small for the run is a configuration error, not a
            # property of the CLI.
            raise
        except Exception as e:
            raise BadOutput(f"output rejected at close: {e!r}") from e
        succeeded = True

        peak_rss = reading.maxrss_raw * _RSS_SCALE
        if budget.max_rss_bytes is not None and peak_rss > budget.max_rss_bytes:
            raise BudgetExceeded(
                f"peak RSS {peak_rss} bytes, over the budget's {budget.max_rss_bytes}"
            )
        return Run(
            argv=tuple(argv),
            result=result,
            bytes_in=bytes_in,
            bytes_out=pump.bytes_out,
            wall_s=reading.wall_ns / 1e9,
            cpu_s=(reading.utime_us + reading.stime_us) / 1e6,
            peak_rss_bytes=peak_rss,
            rss_floor_bytes=reading.floor_bytes,
            peak_scratch_bytes=meter.peak,
            peak_tmp_bytes=meter.peak_tmp,
            stderr=stderr,
        )
    finally:
        pump.abort.set()
        pump.child_done.set()
        if proc is not None and proc.poll() is None:
            # Interrupted (Ctrl-C, an outer timeout): SIGKILL would orphan the CLI.
            _stop(proc)
        for pipe, reader in captures:
            # A reader still blocked on it would read whatever reuses the fd.
            if not reader.is_alive():
                pipe.close()
        if not succeeded:
            _abort(dst.consumer)
        if rundir is not None:
            shutil.rmtree(rundir, ignore_errors=True)


# --- encrypt, decrypt, probe ------------------------------------------------


type Adapter = Literal["fifo", "file"]


@dataclass(frozen=True, slots=True)
class Route:
    """How the CLI's ``src`` and ``dst`` paths are provided."""

    src: Adapter
    dst: Adapter

    def __str__(self) -> str:
        return f"{self.src}->{self.dst}"


def encrypt(
    command: Command,
    plaintext: Source,
    *,
    route: Route,
    scratch: Path,
    budget: Budget = Budget(),
    downstream: Consumer[Any] | None = None,
    tail_ceiling: int = DEFAULT_TAIL_CEILING,
    mount: Mount | None = None,
) -> Run[TdfEvidence]:
    """Encrypt ``plaintext`` and check the TDF holds exactly its length.

    A ``file`` input is ``mount(plaintext)`` when given, else a materialised
    copy in scratch. Pass ``downstream`` to keep the ciphertext -- a
    :class:`FileSink`, or a :class:`rangeserve.SparseSink`.
    """
    sink = CountedSink(
        tail_ceiling=tail_ceiling,
        downstream=downstream,
        plaintext_length=plaintext.length,
    )
    dst: Output[TdfEvidence] = (
        FifoOutput(sink, "output.tdf")
        if route.dst == "fifo"
        else FileOutput(sink, "output.tdf")
    )
    with ExitStack() as stack:
        src: Input
        if route.src == "fifo":
            src = FifoInput(plaintext, "plaintext")
        elif mount is not None:
            src = FileInput(stack.enter_context(mount(plaintext)))
        else:
            src = MaterializedInput(plaintext, "plaintext")
        return run(command, src=src, dst=dst, scratch=scratch, budget=budget)


def decrypt(
    command: Command,
    ciphertext: Path,
    expected: Callable[[int, int], bytes],
    length: int,
    *,
    route: Route,
    scratch: Path,
    budget: Budget = Budget(),
) -> Run[int]:
    """Decrypt ``ciphertext`` and validate the output against ``expected``."""
    validator = Validator(expected, length)
    dst: Output[int] = (
        FifoOutput(validator, "output.bin")
        if route.dst == "fifo"
        else FileOutput(validator, "output.bin")
    )
    if route.src == "file":
        src = FileInput(ciphertext)
        return run(command, src=src, dst=dst, scratch=scratch, budget=budget)
    with closing(FullFile(ciphertext)) as stored:
        src = FifoInput(stored, "input.tdf")
        return run(command, src=src, dst=dst, scratch=scratch, budget=budget)


#: Most streaming first. Each rung after the first keeps one end proven by an
#: earlier rung, so the first that works also says which end the failures
#: were about.
LADDER = (
    Route("fifo", "fifo"),
    Route("file", "fifo"),
    Route("fifo", "file"),
    Route("file", "file"),
)


@dataclass(frozen=True, slots=True)
class Attempt:
    """One rung of a probe: a route, and how the CLI got on with it."""

    op: Literal["encrypt", "decrypt"]
    route: Route
    run: Run[Any] | None
    #: Why the route is unsupported; None if the run succeeded.
    error: str | None = None

    @property
    def spooled(self) -> bool:
        """Succeeded, but only by copying at least half its input to TMPDIR."""
        r = self.run
        return r is not None and r.bytes_in > 0 and 2 * r.peak_tmp_bytes >= r.bytes_in

    @property
    def streams(self) -> bool:
        return self.error is None and not self.spooled


#: How a CLI refuses a route. Anything else -- a wrong length, corrupt output,
#: a failing sink, a blown budget -- is a defect, and fails the probe rather
#: than being reported as an unsupported route.
REFUSALS: tuple[type[StreamError], ...] = (ChildFailed, EarlyEOF, StreamTimeout)


class ProbeFailed(StreamError):
    """Not one route worked, so there is no capability to report."""


@dataclass(frozen=True, slots=True)
class Probe:
    attempts: tuple[Attempt, ...]
    #: The chosen routes: the first that streams, else the first that worked.
    encrypt: Attempt
    decrypt: Attempt


def _climb(
    op: str, attempt: Callable[[Route], Attempt]
) -> tuple[list[Attempt], Attempt]:
    """Try :data:`LADDER` until a route streams; return every rung and the choice."""
    tried: list[Attempt] = []
    for route in LADDER:
        tried.append(attempt(route))
        if tried[-1].streams:
            return tried, tried[-1]
    worked = [a for a in tried if a.error is None]
    if not worked:
        raise ProbeFailed(
            f"{op} failed on every route:\n"
            + "\n".join(f"  {a.route}: {a.error}" for a in tried)
        )
    return tried, worked[0]


def _brief(e: StreamError) -> str:
    first = str(e).splitlines()[0] if str(e) else ""
    return f"{type(e).__name__}: {first}"


def probe(
    encrypt_command: Command,
    decrypt_command: Command,
    plaintext: Plaintext,
    *,
    scratch: Path,
    budget: Budget = Budget(),
) -> Probe:
    """Find the most streaming route each of encrypt and decrypt accepts.

    A route is recorded as unsupported only when the CLI refuses it (see
    :data:`REFUSALS`) and a later one works, so a CLI that cannot encrypt at
    all raises :class:`ProbeFailed`, and one that accepts a route and then gets
    it wrong raises that error, rather than either reporting "unsupported". The chosen encrypt and decrypt runs are
    full controls: exact byte counts, and the output validated by position.
    """
    ciphertext = scratch / "probe.tdf"

    def enc(route: Route, *, keep: bool = False) -> Attempt:
        try:
            r = encrypt(
                encrypt_command,
                plaintext,
                route=route,
                scratch=scratch,
                budget=budget,
                downstream=FileSink(ciphertext),
            )
        except REFUSALS as e:
            return Attempt("encrypt", route, None, _brief(e))
        a = Attempt("encrypt", route, r)
        # Only the chosen run's ciphertext stays, so later rungs' scratch
        # peaks are their own.
        if not (a.streams or keep):
            ciphertext.unlink()
        return a

    encrypts, chosen_enc = _climb("encrypt", enc)
    if not chosen_enc.streams:
        chosen_enc = enc(chosen_enc.route, keep=True)
        encrypts.append(chosen_enc)
        if chosen_enc.error:
            raise ProbeFailed(
                f"encrypt {chosen_enc.route} failed on rerun: {chosen_enc.error}"
            )

    def dec(route: Route) -> Attempt:
        try:
            r = decrypt(
                decrypt_command,
                ciphertext,
                plaintext,
                plaintext.length,
                route=route,
                scratch=scratch,
                budget=budget,
            )
        except REFUSALS as e:
            return Attempt("decrypt", route, None, _brief(e))
        return Attempt("decrypt", route, r)

    decrypts, chosen_dec = _climb("decrypt", dec)
    ciphertext.unlink(missing_ok=True)
    return Probe(tuple(encrypts + decrypts), chosen_enc, chosen_dec)
