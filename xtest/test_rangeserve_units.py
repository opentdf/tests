"""Offline tests for the sparse TDF store and range server (DSPX-5111).

No platform, no SDK: the java goldens stand in for SDK output.
"""

import http.client
import random
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import rangeserve
import zipinspect
from rangeserve import PAYLOAD_GCM_OVERHEAD as GCM
from rangeserve import ExtentStore, FullFile, retention_plan, serve

MiB = 1 << 20
GOLDEN = Path(__file__).parent / "golden"
SMALL = GOLDEN / "small-java-4.3.0-e0f8caf.tdf"
#: Five whole 2 MiB segments, so java appends an empty sixth.
BIG = GOLDEN / "big-java-4.3.0-e0f8caf.tdf"
BIG_LAYOUT = {
    "payload_start": 39,
    "plaintext_length": 10 * MiB,
    "segment_size": 2 * MiB,
}

SEG = 1000
PT_LEN = 4 * SEG + 300  # four whole segments and a short fifth


def get(url: str, range_header: str | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url)
    if range_header:
        req.add_header("Range", range_header)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def plan(*ranges: tuple[int, int], start: int = 100) -> list[tuple[int, int]]:
    return retention_plan(
        ranges, plaintext_length=PT_LEN, segment_size=SEG, payload_start=start
    )


# --- layout -----------------------------------------------------------------

STRIDE = SEG + GCM


def test_plan_last_short_segment():
    last = 100 + 4 * STRIDE
    assert plan((PT_LEN - 1, PT_LEN)) == [(0, 100), (last, last + 300 + GCM)]


def test_plan_crosses_segment_boundary():
    got = plan((2 * SEG - 1, 2 * SEG + 1))
    assert got == [(0, 100), (100 + STRIDE, 100 + 3 * STRIDE)]


def test_plan_disjoint_and_overlapping_ranges():
    got = plan((2 * SEG + 5, 2 * SEG + 6), (3 * SEG, 3 * SEG + 1), (10, 20), start=50)
    assert got == [(0, 50 + STRIDE), (50 + 2 * STRIDE, 50 + 4 * STRIDE)]


@pytest.mark.parametrize(
    ("name", "start", "pt_len", "trailer"),
    [
        ("big-java-4.3.0-e0f8caf.tdf", 39, 10 * MiB, GCM),
        ("no-splitids-java.tdf", 3446, 5120, 0),
    ],
    ids=["whole-segments", "manifest-first"],
)
def test_layout_matches_java_goldens(name: str, start: int, pt_len: int, trailer: int):
    path = GOLDEN / name
    cd = zipinspect.central_directory(path)
    payload = next(e for e in cd.entries if e.name == "0.payload")
    assert rangeserve.payload_start(path) == start
    end = rangeserve.data_end(
        payload_start=start, plaintext_length=pt_len, segment_size=2 * MiB
    )
    assert start + payload.compressed_size == end + trailer


# --- store and server -------------------------------------------------------


def test_full_mode_serves_whole_file():
    data = SMALL.read_bytes()
    with serve(FullFile(SMALL)) as (url, log):
        assert url.endswith("/payload.tdf")
        assert get(url) == (200, data)
        assert get(url, "bytes=10-19") == (206, data[10:20])
        assert get(url, "bytes=-22") == (206, data[-22:])
        assert get(url, f"bytes={len(data) - 5}-") == (206, data[-5:])
        assert get(url, f"bytes=0-{len(data) * 2}") == (206, data)
        assert get(url, f"bytes={len(data)}-")[0] == 416
        assert get(url, "bytes=0-1,5-6")[0] == 400
        preflight = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(preflight, timeout=10) as r:
            assert r.status == 204
            assert r.headers["Access-Control-Allow-Headers"] == "Range"
            assert r.headers["Access-Control-Allow-Origin"] == "*"
    assert [r.status for r in log] == [200, 206, 206, 206, 206, 416, 400, 204]
    assert log[1] == rangeserve.Request("GET", "bytes=10-19", 206, 10, 10, 20)


def test_sparse_store_serves_kept_and_refuses_dropped(tmp_path: Path):
    data = BIG.read_bytes()
    seg = BIG_LAYOUT["segment_size"]
    kept = rangeserve.merge(
        retention_plan([(seg - 1, seg + 1), (3 * seg + 1, 3 * seg + 2)], **BIG_LAYOUT)
        + [(rangeserve.data_end(**BIG_LAYOUT), len(data))]  # the tail
    )
    store = ExtentStore(tmp_path, len(data))
    for s, e in kept:
        store.add(s, data[s:e])
    assert store.physical_size == sum(e - s for s, e in kept)

    dropped = [(kept[i][1], kept[i + 1][0]) for i in range(len(kept) - 1)]
    assert len(dropped) == 2, "segments 2 and 4"
    with serve(store) as (url, log):
        for s, e in kept:
            assert get(url, f"bytes={s}-{e - 1}") == (206, data[s:e])
        for s, e in dropped:
            assert get(url, f"bytes={s}-{e - 1}")[0] == 410
            # Straddling a kept/dropped edge is still refused.
            assert get(url, f"bytes={s - 1}-{s}")[0] == 410
        assert get(url)[0] == 410
    refused = [r for r in log if r.status == 410]
    assert all(r.bytes_served == 0 for r in refused)
    assert {r.dropped_at for r in refused} == {s for s, _ in dropped}
    store.close()


def test_store_rejects_overlap(tmp_path: Path):
    store = ExtentStore(tmp_path, 100)
    with pytest.raises(FileExistsError):
        ExtentStore(tmp_path, 100)
    store.add(10, b"x" * 10)
    with pytest.raises(ValueError):
        store.add(15, b"y")
    with pytest.raises(ValueError):
        store.add(95, b"z" * 10)
    store.add(20, b"w" * 5)  # contiguous: merged, readable across the seam
    assert store.read(15, 25) == b"x" * 5 + b"w" * 5
    store.close()


def test_50tib_logical_length_bounded_disk(tmp_path: Path):
    logical = 50 * 2**40
    pieces = {
        0: b"H" * 64,
        2**32 - 3: b"A" * 7,  # straddles 2^32
        2**40 + 11: b"B" * 13,
        logical - 4096: b"T" * 4096,
    }
    store = ExtentStore(tmp_path, logical)
    for off, b in pieces.items():
        store.add(off, b)
    assert store.physical_size == 64 + 7 + 13 + 4096
    with serve(store) as (url, log):
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            assert int(r.headers["Content-Length"]) == logical
            assert r.headers["Accept-Ranges"] == "bytes"
        assert get(url, "bytes=-4096") == (206, b"T" * 4096)
        assert get(url, f"bytes={2**32 - 3}-{2**32 + 3}") == (206, b"A" * 7)
        assert get(url, f"bytes={2**40 + 11}-{2**40 + 23}") == (206, b"B" * 13)
        assert get(url, f"bytes={logical // 2}-{logical // 2 + 1}")[0] == 410
    assert log[0] == rangeserve.Request("HEAD", None, 200, 0)
    store.close()


# --- lifecycle --------------------------------------------------------------


def test_server_stops_on_exit():
    with serve(FullFile(SMALL)) as (url, _):
        port = urllib.parse.urlsplit(url).port
        assert port
        # Left idle on a keep-alive connection, its handler blocks on a read.
        idle = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        idle.request("GET", "/", headers={"Range": "bytes=0-0"})
        assert idle.getresponse().read() == b"P"
    assert not [t for t in threading.enumerate() if f"rangeserve-{port}" in t.name]
    idle.close()
    with (
        pytest.raises(ConnectionRefusedError),
        socket.create_connection(("127.0.0.1", port), timeout=2),
    ):
        pass


def test_handler_error_fails_the_block():
    class Short(FullFile):
        def read(self, start: int, end: int) -> bytes:
            return super().read(start, end)[1:]

    with pytest.raises(ExceptionGroup), serve(Short(SMALL)) as (url, _):
        with pytest.raises(OSError):
            get(url, "bytes=0-9")


# --- SparseSink ---------------------------------------------------------------


def random_chunks(data: bytes) -> Iterator[bytes]:
    rng = random.Random(654)
    pos = 0
    while pos < len(data):
        n = rng.choice((0, 1, rng.randrange(1 << 16), rng.randrange(1 << 22)))
        yield data[pos : pos + n]
        pos += n


def test_sink_keeps_plan_and_tail(tmp_path: Path):
    data = BIG.read_bytes()
    seg = BIG_LAYOUT["segment_size"]
    kept = retention_plan(
        [(seg - 1, seg + 1), (3 * seg + 1, 3 * seg + 2)], **BIG_LAYOUT
    )
    sink = rangeserve.SparseSink(tmp_path, kept, tail_ceiling=1 << 16, **BIG_LAYOUT)
    chunks = list(random_chunks(data))
    assert {0, 1} <= {len(c) for c in chunks}
    for c in chunks:
        sink.write(c)
    store = sink.close()

    # From the last data segment on, java's empty one included.
    tail = (rangeserve.data_end(**BIG_LAYOUT), len(data))
    assert (sink.payload_start, sink.tail_start) == (39, tail[0] + GCM)
    assert store.length == len(data)
    for s, e in [*kept, tail]:
        assert store.read(s, e) == data[s:e]
    # So every other byte is in a data segment the plan dropped.
    assert store.physical_size == sum(e - s for s, e in [*kept, tail])
    store.close()


@pytest.mark.parametrize(
    "wrong",
    [{"payload_start": 59}, {"segment_size": 4 * MiB}],
    ids=["payload_start", "segment_size"],
)
def test_sink_refuses_wrong_layout(tmp_path: Path, wrong: dict[str, int]):
    layout = BIG_LAYOUT | wrong
    kept = retention_plan([], **layout)
    sink = rangeserve.SparseSink(tmp_path, kept, tail_ceiling=0, **layout)
    with pytest.raises(ValueError):
        sink.write(BIG.read_bytes())
        sink.close()


def test_sink_refuses_tail_over_ceiling(tmp_path: Path):
    tdf = tmp_path / "t.tdf"
    with zipfile.ZipFile(tdf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("0.payload", random.Random(5111).randbytes(PT_LEN + 5 * GCM))
        z.writestr("0.manifest.json", "{}" + " " * 200_000)
    layout = {"payload_start": 39, "plaintext_length": PT_LEN, "segment_size": SEG}
    sink = rangeserve.SparseSink(
        tmp_path, plan(start=39), tail_ceiling=1 << 16, **layout
    )
    for c in random_chunks(tdf.read_bytes()):
        sink.write(c)
    with pytest.raises(rangeserve.ManifestTooLarge):
        sink.close()
    assert not (tmp_path / "extents.bin").exists()


def test_sink_refuses_short_stream(tmp_path: Path):
    kept = [(0, 39), (500, 600)]
    sink = rangeserve.SparseSink(tmp_path, kept, tail_ceiling=0, **BIG_LAYOUT)
    sink.write(BIG.read_bytes()[:550])
    with pytest.raises(ValueError):
        sink.close()
