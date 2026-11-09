"""The NFS front end with no platform and no SDK (DSPX-5543).

Every read goes through the real kernel NFS client, so these pin what an SDK
CLI will see: kept bytes as stored, dropped bytes as filler, each fetch in the
range server's log, and nothing left mounted or running afterwards.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

import nfsmount
import rangeserve
import tdfs
from fixtures.nfs_mount import Mounter, nfs_root
from rangeserve import PAYLOAD_GCM_OVERHEAD as GCM
from rangeserve import ExtentStore, FullFile, Request

MiB = 1 << 20
#: Five whole 2 MiB segments, so java appends an empty sixth to the tail.
BIG_JAVA = Path(__file__).parent / "golden" / "big-java-4.3.0-e0f8caf.tdf"


def content(start: int, end: int) -> bytes:
    """Bytes ``[start, end)`` of a synthetic file whose 8-byte words count up.

    Position-dependent, so a read served from the wrong offset cannot match.
    """
    words = np.arange(start // 8, -(-end // 8), dtype=">u8").tobytes()
    return words[start % 8 : start % 8 + end - start]


def fetched(log: list[Request], start: int, end: int, status: int) -> bool:
    """Whether logged GETs answered ``status`` cover ``[start, end)``."""
    spans = [
        (r.start, r.end)
        for r in log
        if r.method == "GET"
        and r.status == status
        and r.start is not None
        and r.end is not None
    ]
    return any(s <= start and end <= e for s, e in rangeserve.merge(spans))


def test_full_file(nfs_mount: Mounter, tmp_path: Path):
    size = 8 * MiB + 5
    src = tmp_path / "whole.tdf"
    src.write_bytes(content(0, size))
    path, log = nfs_mount(FullFile(src))
    # Streamed in small reads, as a CLI does.
    with path.open("rb", buffering=0) as f:
        got = b"".join(iter(lambda: f.read(64 << 10), b""))
    assert got == src.read_bytes()
    gets = [r for r in log if r.method == "GET"]
    assert gets and all(r.status == 206 for r in gets)
    assert sum(r.bytes_served for r in gets) >= size
    # Whole RSIZE READs, not a page at a time (Linux at read_ahead_kb=0).
    blocks = -(-size // nfsmount.RSIZE)
    assert len(gets) <= 2 * blocks + 4, f"{len(gets)} GETs for {blocks} blocks"


@pytest.mark.parametrize(
    "logical", [100 * 2**30, 5 * 2**40, 50 * 2**40], ids=["100GiB", "5TiB", "50TiB"]
)
def test_sparse(nfs_mount: Mounter, tmp_path: Path, logical: int):
    seg, head = MiB, 1000
    stride = seg + GCM
    segments = (logical - head - 4096) // stride
    payload_end = head + segments * stride
    # 16-byte ciphertext reads across and above 2^32 and 2^40, and at the
    # payload's end; plan the plaintext segments that hold them.
    targets = [t for t in (2**32 - 8, 2**32 + 5, 2**40 + 3) if t < payload_end]
    targets.append(payload_end - 100)
    indices = sorted({(t - head) // stride for t in targets})
    # The last planned bytes, whose READs reach furthest past the plan.
    edges = [head + (i + 1) * stride for i in indices]
    plan = rangeserve.retention_plan(
        [(i * seg, i * seg + 1) for i in indices],
        plaintext_length=segments * seg,
        segment_size=seg,
        payload_start=head,
        pad=nfsmount.PAD,
    )
    store = ExtentStore(tmp_path, logical)
    for s, e in rangeserve.merge([*plan, (payload_end, logical)]):
        store.add(s, content(s, e))
    path, log = nfs_mount(store)
    assert path.stat().st_size == logical

    reads = [
        (0, 64),
        *((t, t + 16) for t in targets),
        *((e - 16, e) for e in edges),
        (logical - 22, logical),
    ]
    # Buffered: each read pulls in a whole buffer, past the bytes asked for.
    with path.open("rb") as f:
        for s, e in reads:
            f.seek(s)
            assert f.read(e - s) == content(s, e), f"bytes {s}-{e}"
    dropped = logical // 2 + 3
    with pytest.raises(rangeserve.Dropped):
        store.check(dropped, dropped + 16)
    fd = os.open(path, os.O_RDONLY)
    try:
        for s, e in reads:
            assert os.pread(fd, e - s, s) == content(s, e), f"bytes {s}-{e}"
        assert os.pread(fd, 16, dropped) == nfsmount.filler(dropped, dropped + 16)
    finally:
        os.close(fd)

    for s, e in reads:
        assert fetched(log, s, e, 206), f"no logged fetch of {s}-{e}: {log}"
    assert fetched(log, dropped, dropped + 16, 410), f"no logged 410: {log}"
    store.close()


def test_sparse_java_golden(nfs_mount: Mounter, tmp_path: Path):
    data = BIG_JAVA.read_bytes()
    layout = {
        "payload_start": rangeserve.payload_start(BIG_JAVA),
        "plaintext_length": 10 * MiB,
        "segment_size": 2 * MiB,
    }
    tail = rangeserve.data_end(**layout)
    plan = rangeserve.retention_plan([(5, 6)], **layout, pad=nfsmount.PAD)
    store = ExtentStore(tmp_path, len(data))
    for s, e in rangeserve.merge([*plan, (tail, len(data))]):
        store.add(s, data[s:e])
    path, _ = nfs_mount(store, "big.tdf")

    assert tdfs.manifest(path) == tdfs.manifest(BIG_JAVA)
    with path.open("rb") as f:
        f.seek(-1, os.SEEK_END)
        assert f.read() == data[-1:]
        # The last tag, java's empty segment and the manifest's local header.
        f.seek(tail - 16)
        assert f.read(16 + GCM + 30) == data[tail - 16 : tail + GCM + 30]
    dropped = plan[0][1]
    assert dropped < tail - nfsmount.PAD, "the copy should be sparse"
    fd = os.open(path, os.O_RDONLY)
    try:
        assert os.pread(fd, 8, dropped) == nfsmount.filler(dropped, dropped + 8)
    finally:
        os.close(fd)
    store.close()


def test_teardown_after_failure(nfsserve_binary: Path, tmp_dir: Path, tmp_path: Path):
    src = tmp_path / "f.tdf"
    src.write_bytes(content(0, 4096))
    mounts: list[nfsmount.Mount] = []
    with (
        pytest.raises(RuntimeError, match="test failed"),
        rangeserve.serve(FullFile(src)) as (url, _),
        nfsmount.mounted(url, nfs_root(tmp_dir), nfsserve_binary) as m,
    ):
        mounts.append(m)
        assert m.file.read_bytes() == src.read_bytes()
        raise RuntimeError("test failed")
    (m,) = mounts
    assert m.server.poll() is not None
    assert str(m.file.parent) not in nfsmount.mount_table()
    assert not m.file.parent.exists()


KILLED_RUN = """
import sys, time
from pathlib import Path
import nfsmount, rangeserve
src, root, binary = map(Path, sys.argv[1:])
with (
    rangeserve.serve(rangeserve.FullFile(src)) as (url, _),
    nfsmount.mounted(url, root, binary) as m,
):
    print(m.file.parent, m.server.pid, flush=True)
    time.sleep(600)
"""


def test_killed_run_is_reaped(nfsserve_binary: Path, tmp_dir: Path, tmp_path: Path):
    src = tmp_path / "f.tdf"
    src.write_bytes(content(0, 4096))
    root = nfs_root(tmp_dir)
    run = subprocess.Popen(
        [sys.executable, "-c", KILLED_RUN, src, root, nfsserve_binary],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert run.stdout
    point, pid = run.stdout.readline().rsplit(maxsplit=1)
    run.kill()
    run.wait()

    # The server's stdin closes with its parent, so it exits on its own.
    deadline = time.monotonic() + 10
    while nfsmount._alive(int(pid)) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not nfsmount._alive(int(pid)), "nfsserve outlived the killed run"

    assert point in nfsmount.mount_table()
    nfsmount.reap(root)
    assert point not in nfsmount.mount_table()
    assert not Path(point).exists()
