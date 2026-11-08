"""Offline tests for the streaming harness (DSPX-5108).

No platform, no SDK: a short Python script stands in for ``cli.sh``. Its
"encrypt" writes a STORED ZIP shaped like a TDF (12-byte IV and 16-byte tag
around each 1000-byte segment) through a non-seekable stream, the way a
streaming SDK does, and its "decrypt" inverts that. ``FAKE`` selects a fault.

These pin the verdicts: each fault must raise, not pass and not hang.
"""

import os
import sys
import time
from pathlib import Path

import pytest

import streamharness as sh
from rangeserve import ExtentStore, ManifestTooLarge, SparseSink, payload_start
from streamharness import (
    Budget,
    ChildFailed,
    ContentMismatch,
    CountedSink,
    EarlyEOF,
    FifoInput,
    FifoOutput,
    FileSink,
    Plaintext,
    Route,
    ShortInput,
    SinkError,
    StreamTimeout,
    Validator,
    WrongLength,
)

FAKE_CLI = r"""
import io, json, os, shutil, stat, sys, time, zipfile

op, src, dst = sys.argv[1:4]
fake = os.environ.get("FAKE", "ok")
regular = stat.S_ISREG(os.stat(src).st_mode)
if fake == "hang":
    time.sleep(3600)
if fake == "fail":
    sys.exit("fake cli: boom")
if fake == "write-then-hang":
    with open(os.environ["FAKE_PIDFILE"], "w") as f:
        f.write(str(os.getpid()))
    with open(dst, "wb") as f:
        f.write(b"x" * 100)
        f.flush()
        time.sleep(3600)
if fake == "regular-only" and not regular:
    sys.exit(f"not a regular file [{src}]")
with open(src, "rb") as f:
    data = f.read(int(os.environ["FAKE_READ"])) if fake == "early-eof" else f.read()
if fake == "spool-fifo" and not regular:
    spool = os.path.join(os.environ["TMPDIR"], "spool")
    with open(spool, "wb") as s:
        s.write(data)
    time.sleep(0.6)
    os.unlink(spool)

if op == "decrypt":
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("0.manifest.json"))
        payload = z.read("0.payload")
    out, pos = bytearray(), 0
    for s in manifest["encryptionInformation"]["integrityInformation"]["segments"]:
        out += payload[pos + 12 : pos + s["encryptedSegmentSize"] - 16]
        pos += s["encryptedSegmentSize"]
    if fake == "short-write":
        out = out[:-1]
    if fake == "corrupt-fifo" and not regular:
        out[0] ^= 1
    with open(dst, "wb") as f:
        f.write(out)
    sys.exit(0)

if fake == "short-write":
    data = data[:-1]
segs = [data[i : i + 1000] for i in range(0, len(data), 1000)]
manifest = {
    "schemaVersion": "4.3.0",
    "encryptionInformation": {
        "method": {"algorithm": "AES-256-GCM"},
        "keyAccess": [{"type": "wrapped"}],
        "integrityInformation": {
            "segmentHashAlg": "GMAC",
            "rootSignature": {"alg": "HS256"},
            "segmentSizeDefault": 1000,
            "encryptedSegmentSizeDefault": 1028,
            "segments": [
                {"segmentSize": len(s), "encryptedSegmentSize": len(s) + 28}
                for s in segs
            ],
        },
    },
}
with open(dst, "wb") as out, zipfile.ZipFile(out, "w") as z:
    with z.open("0.payload", "w", force_zip64=True) as p:
        for s in segs:
            p.write(bytes(12) + s + bytes(16))
    z.writestr("0.manifest.json", json.dumps(manifest))
"""

N = 50_000


def fake(op: str, **env: str) -> sh.Command:
    def command(src: Path, dst: Path) -> tuple[list[str], dict[str, str]]:
        return [sys.executable, "-c", FAKE_CLI, op, str(src), str(dst)], env

    return command


def test_plaintext_is_position_derivable():
    pt = Plaintext(10_000)
    whole = pt(0, 10_000)
    assert pt(4093, 1000) == whole[4093:5093]
    assert pt.read(17, 33) == whole[17:33]
    assert Plaintext(10_000)(0, 64) == whole[:64]
    assert Plaintext(10_000, seed=b"other")(0, 64) != whole[:64]
    far = Plaintext(50 << 40)
    assert far(far.length - 5, 5) == far(far.length - 21, 21)[16:]
    with pytest.raises(ValueError):
        pt(9_999, 2)


def test_roundtrip_counts_and_validates(tmp_path: Path):
    pt = Plaintext(N)
    kept = tmp_path / "ct.tdf"
    enc = sh.encrypt(
        fake("encrypt"),
        pt,
        route=Route("fifo", "fifo"),
        scratch=tmp_path,
        downstream=FileSink(kept),
    )
    ev = enc.result
    assert enc.bytes_in == N
    assert enc.bytes_out == ev.byte_count == kept.stat().st_size
    assert ev.manifest.segment_count == 50
    assert ev.manifest.segment_sizes == ((1000, 50),)
    assert ev.payload_length == N + 50 * 28

    dec = sh.decrypt(
        fake("decrypt"), kept, pt, N, route=Route("fifo", "fifo"), scratch=tmp_path
    )
    assert dec.result == dec.bytes_out == N
    assert [p.name for p in tmp_path.iterdir()] == ["ct.tdf"]


def test_short_input_fails(tmp_path: Path):
    real = Plaintext(N - 10)

    class Lying:
        length = N

        def check(self, start: int, end: int) -> None:
            pass

        def read(self, start: int, end: int) -> bytes:
            return real.read(start, min(end, real.length))

    with pytest.raises(ShortInput):
        sh.run(
            fake("encrypt"),
            src=FifoInput(Lying()),
            dst=FifoOutput(CountedSink(plaintext_length=N)),
            scratch=tmp_path,
        )


def test_cli_that_stops_reading_fails(tmp_path: Path):
    # Bigger than any pipe buffer, so the unread remainder cannot hide in one.
    pt = Plaintext(4 << 20)
    with pytest.raises(EarlyEOF):
        sh.run(
            fake("encrypt", FAKE="early-eof", FAKE_READ="1000"),
            src=FifoInput(pt),
            dst=FifoOutput(CountedSink()),
            scratch=tmp_path,
        )


def test_sink_failure_fails_and_stops_the_cli(tmp_path: Path):
    class Full:
        def write(self, data: bytes) -> None:
            raise OSError("disk full")

        def close(self) -> None:
            pass

    pidfile = tmp_path.parent / f"{tmp_path.name}.pid"
    started = time.monotonic()
    with pytest.raises(SinkError, match="disk full"):
        sh.run(
            # Never notices the reader has gone; only a kill stops it.
            fake("encrypt", FAKE="write-then-hang", FAKE_PIDFILE=str(pidfile)),
            src=FifoInput(Plaintext(N)),
            dst=FifoOutput(Full()),
            scratch=tmp_path,
            budget=Budget(timeout_s=60),
        )
    assert time.monotonic() - started < 30
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_interrupted_run_stops_the_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pidfile = tmp_path.parent / f"{tmp_path.name}.pid"

    def interrupted(*_: object) -> bool:
        while not pidfile.exists():
            time.sleep(0.01)
        raise KeyboardInterrupt

    monkeypatch.setattr(sh, "_wait", interrupted)
    with pytest.raises(KeyboardInterrupt):
        sh.run(
            fake("encrypt", FAKE="write-then-hang", FAKE_PIDFILE=str(pidfile)),
            src=FifoInput(Plaintext(N)),
            dst=FifoOutput(CountedSink()),
            scratch=tmp_path,
        )
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


@pytest.mark.parametrize("op", ["encrypt", "decrypt"])
def test_wrong_byte_count_fails(tmp_path: Path, op: str):
    pt = Plaintext(N)
    kept = tmp_path / "ct.tdf"
    if op == "decrypt":
        sh.encrypt(
            fake("encrypt"),
            pt,
            route=Route("fifo", "fifo"),
            scratch=tmp_path,
            downstream=FileSink(kept),
        )
    with pytest.raises(WrongLength):
        if op == "encrypt":
            sh.encrypt(
                fake("encrypt", FAKE="short-write"),
                pt,
                route=Route("fifo", "fifo"),
                scratch=tmp_path,
                downstream=FileSink(kept),
            )
        else:
            sh.decrypt(
                fake("decrypt", FAKE="short-write"),
                kept,
                pt,
                N,
                route=Route("fifo", "fifo"),
                scratch=tmp_path,
            )
    # A failed encrypt leaves no partial ciphertext behind.
    assert kept.exists() == (op == "decrypt")


def test_child_failure_fails(tmp_path: Path):
    with pytest.raises(ChildFailed, match="boom"):
        sh.run(
            fake("decrypt", FAKE="fail"),
            src=FifoInput(Plaintext(N)),
            dst=FifoOutput(Validator(Plaintext(N), N)),
            scratch=tmp_path,
        )


def test_timeout_kills_the_cli(tmp_path: Path):
    started = time.monotonic()
    with pytest.raises(StreamTimeout):
        sh.run(
            fake("encrypt", FAKE="hang"),
            src=FifoInput(Plaintext(N)),
            dst=FifoOutput(CountedSink()),
            scratch=tmp_path,
            budget=Budget(timeout_s=1),
        )
    assert time.monotonic() - started < 15
    assert list(tmp_path.iterdir()) == []


def test_counted_sink_ceiling_and_sparse_sink_chaining(tmp_path: Path):
    big = Plaintext(2_000_000)  # ~2000 segments: a manifest over 64 KiB
    with pytest.raises(ManifestTooLarge):
        sh.run(
            fake("encrypt"),
            src=FifoInput(big),
            dst=FifoOutput(CountedSink(tail_ceiling=0)),
            scratch=tmp_path,
        )

    kept = tmp_path / "ct.tdf"
    enc = sh.encrypt(
        fake("encrypt"),
        Plaintext(N),
        route=Route("fifo", "fifo"),
        scratch=tmp_path,
        downstream=FileSink(kept),
    )
    start = payload_start(kept)
    assert enc.result.payload_start == start

    # The same manifest, from the SparseSink's store rather than a second
    # buffer: this CountedSink's own ceiling could not hold it.
    store = tmp_path / "store"
    store.mkdir()
    sparse = SparseSink(
        store,
        [(0, start)],
        tail_ceiling=1 << 20,
        payload_start=start,
        plaintext_length=big.length,
        segment_size=1000,
    )
    sink = CountedSink(tail_ceiling=0, downstream=sparse, plaintext_length=big.length)
    r = sh.run(
        fake("encrypt"), src=FifoInput(big), dst=FifoOutput(sink), scratch=tmp_path
    )
    assert r.result.manifest.segment_count == 2000
    assert isinstance(sink.downstream_result, ExtentStore)
    assert sink.downstream_result.length == sink.count


def test_probe_falls_back_and_says_why(tmp_path: Path):
    p = sh.probe(
        fake("encrypt", FAKE="regular-only"),
        fake("decrypt", FAKE="spool-fifo"),
        Plaintext(N),
        scratch=tmp_path,
    )
    first_enc, first_dec = p.attempts[0], p.attempts[2]
    assert first_enc.route == Route("fifo", "fifo")
    assert first_enc.error and "not a regular file" in first_enc.error
    assert p.encrypt.route == Route("file", "fifo") and p.encrypt.streams
    # Accepted the FIFO, but only by copying it to TMPDIR: not streaming.
    assert first_dec.error is None and first_dec.spooled
    assert p.decrypt.route == Route("file", "fifo") and p.decrypt.streams


def test_probe_fails_a_route_that_corrupts_rather_than_refuses(tmp_path: Path):
    with pytest.raises(ContentMismatch):
        sh.probe(
            fake("encrypt"),
            fake("decrypt", FAKE="corrupt-fifo"),
            Plaintext(N),
            scratch=tmp_path,
        )
