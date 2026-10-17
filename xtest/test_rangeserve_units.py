"""Offline tests for the sparse TDF store and range server (DSPX-5111).

No platform, no SDK. The "TDF" is a stored ZIP whose payload has the layout
of real segments; nothing here decrypts, so random bytes stand in for
ciphertext.
"""

import random
import socket
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

import rangeserve
from rangeserve import PAYLOAD_GCM_OVERHEAD as GCM
from rangeserve import ExtentStore, FullFile, retention_plan, serve

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


@pytest.fixture
def tdf(tmp_path: Path) -> Path:
    path = tmp_path / "fake.tdf"
    ct_len = PT_LEN + 5 * GCM
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("0.payload", random.Random(5111).randbytes(ct_len))
        z.writestr("0.manifest.json", '{"payload": {}}' + " " * 3000)
    return path


def plan(*ranges: tuple[int, int], start: int = 100) -> list[tuple[int, int]]:
    return retention_plan(
        ranges, plaintext_length=PT_LEN, segment_size=SEG, payload_start=start
    )


# --- retention_plan ---------------------------------------------------------

STRIDE = SEG + GCM


def test_plan_first_segment():
    assert plan((0, 1)) == [(0, 100 + STRIDE)]


def test_plan_last_short_segment():
    last = 100 + 4 * STRIDE
    assert plan((PT_LEN - 1, PT_LEN)) == [(0, 100), (last, last + 300 + GCM)]


def test_plan_crosses_segment_boundary():
    got = plan((2 * SEG - 1, 2 * SEG + 1))
    assert got == [(0, 100), (100 + STRIDE, 100 + 3 * STRIDE)]


def test_plan_disjoint_and_overlapping_ranges():
    got = plan((2 * SEG + 5, 2 * SEG + 6), (3 * SEG, 3 * SEG + 1), (10, 20), start=50)
    assert got == [(0, 50 + STRIDE), (50 + 2 * STRIDE, 50 + 4 * STRIDE)]


def test_plan_empty_range_keeps_only_head():
    assert plan((7, 7)) == [(0, 100)]


@pytest.mark.parametrize("bad", [(-1, 3), (5, 4), (0, PT_LEN + 1)])
def test_plan_rejects_out_of_bounds(bad: tuple[int, int]):
    with pytest.raises(ValueError):
        plan(bad)


# --- store and server against a small TDF -----------------------------------


def test_payload_start_finds_data(tdf: Path):
    start = rangeserve.payload_start(tdf)
    with zipfile.ZipFile(tdf) as z:
        first = z.read("0.payload")[:64]
    assert tdf.read_bytes()[start : start + 64] == first


def test_full_mode_serves_whole_file(tdf: Path):
    data = tdf.read_bytes()
    with serve(FullFile(tdf)) as (url, log):
        assert get(url) == (200, data)
        assert get(url, "bytes=10-19") == (206, data[10:20])
        assert get(url, "bytes=-22") == (206, data[-22:])
        assert get(url, f"bytes={len(data) - 5}-") == (206, data[-5:])
        assert get(url, f"bytes=0-{len(data) * 2}") == (206, data)
        assert get(url, f"bytes={len(data)}-")[0] == 416
        assert get(url, "bytes=0-1,5-6")[0] == 400
    assert [r.status for r in log] == [200, 206, 206, 206, 206, 416, 400]
    assert log[1] == rangeserve.Request("GET", "bytes=10-19", 206, 10)


def test_head_reports_length(tdf: Path):
    with serve(FullFile(tdf)) as (url, log):
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            assert int(r.headers["Content-Length"]) == tdf.stat().st_size
            assert r.headers["Accept-Ranges"] == "bytes"
    assert log == [rangeserve.Request("HEAD", None, 200, 0)]


def test_sparse_store_serves_kept_and_refuses_dropped(tdf: Path, tmp_path: Path):
    data = tdf.read_bytes()
    start = rangeserve.payload_start(tdf)
    payload_end = start + PT_LEN + 5 * GCM
    kept = rangeserve.merge(
        plan((SEG - 1, SEG + 1), (2 * SEG + 1, 2 * SEG + 2), start=start)
        + [(payload_end, len(data))]  # the tail
    )
    store = ExtentStore(tmp_path, len(data))
    for s, e in kept:
        store.add(s, data[s:e])
    assert store.physical_size == sum(e - s for s, e in kept)

    dropped = [(kept[i][1], kept[i + 1][0]) for i in range(len(kept) - 1)]
    assert dropped, "plan should leave gaps"
    with serve(store) as (url, log):
        for s, e in kept:
            assert get(url, f"bytes={s}-{e - 1}") == (206, data[s:e])
        for s, e in dropped:
            assert get(url, f"bytes={s}-{e - 1}")[0] == 410
            # Straddling a kept/dropped edge is still refused.
            assert get(url, f"bytes={s - 1}-{s}")[0] == 410
        assert get(url)[0] == 410
    assert all(r.bytes_served == 0 for r in log if r.status == 410)
    store.close()


def test_store_rejects_overlap(tmp_path: Path):
    store = ExtentStore(tmp_path, 100)
    store.add(10, b"x" * 10)
    with pytest.raises(ValueError):
        store.add(15, b"y")
    with pytest.raises(ValueError):
        store.add(95, b"z" * 10)
    store.add(20, b"w" * 5)  # contiguous: merged, readable across the seam
    assert store.read(15, 25) == b"x" * 5 + b"w" * 5
    store.close()


# --- huge logical lengths, tiny disk ----------------------------------------


@pytest.mark.parametrize(
    "logical", [100 * 2**30, 5 * 2**40, 50 * 2**40], ids=["100GiB", "5TiB", "50TiB"]
)
def test_huge_logical_length_bounded_disk(tmp_path: Path, logical: int):
    pieces = {
        0: b"H" * 64,
        2**32 - 3: b"A" * 7,  # straddles 2^32
        2**40 + 11: b"B" * 13,
        logical - 4096: b"T" * 4096,
    }
    store = ExtentStore(tmp_path, logical)
    for off, b in pieces.items():
        if off + len(b) <= logical:
            store.add(off, b)
    assert store.physical_size <= 64 + 7 + 13 + 4096
    with serve(store) as (url, _):
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as r:
            assert int(r.headers["Content-Length"]) == logical
        assert get(url, "bytes=-4096") == (206, b"T" * 4096)
        assert get(url, f"bytes={2**32 - 3}-{2**32 + 3}") == (206, b"A" * 7)
        want = (206, b"B" * 13) if 2**40 < logical else (416, b"")
        assert get(url, f"bytes={2**40 + 11}-{2**40 + 23}") == want
        assert get(url, f"bytes={logical // 2}-{logical // 2 + 1}")[0] == 410
    store.close()


# --- lifecycle --------------------------------------------------------------


def test_server_stops_on_exit(tdf: Path):
    with serve(FullFile(tdf)) as (url, _):
        port = int(url.split(":")[2].split("/")[0])
        assert get(url, "bytes=0-0")[0] == 206
    assert not any(t.name == f"rangeserve-{port}" for t in threading.enumerate())
    with (
        pytest.raises(ConnectionRefusedError),
        socket.create_connection(("127.0.0.1", port), timeout=2),
    ):
        pass


def test_fixture_serves_several(range_server, tdf: Path):
    a, _ = range_server(FullFile(tdf))
    b, _ = range_server(FullFile(tdf))
    assert a != b
    assert get(a, "bytes=0-3") == get(b, "bytes=0-3")
