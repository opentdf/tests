"""The NFS front end with no platform and no SDK (DSPX-5543).

Every read goes through the real kernel NFS client, so these pin what an SDK
CLI will see: kept bytes as stored, dropped bytes as filler, each fetch in the
range server's log, and nothing left mounted or running afterwards.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

import nfsmount
import rangeserve
from fixtures.nfs_mount import nfs_root
from rangeserve import PAYLOAD_GCM_OVERHEAD as GCM
from rangeserve import ExtentStore, FullFile, Request

MiB = 1 << 20

Mounter = Callable[[rangeserve.Source], tuple[Path, list[Request]]]


def content(start: int, end: int) -> bytes:
    """Bytes ``[start, end)`` of a synthetic file whose 8-byte words count up.

    Position-dependent, so a read served from the wrong offset cannot match.
    """
    words = np.arange(start // 8, -(-end // 8), dtype=">u8").tobytes()
    return words[start % 8 : start % 8 + end - start]


def fetched(log: list[Request], start: int, end: int, status: int) -> bool:
    """Whether logged GETs answered ``status`` cover ``[start, end)``."""
    spans = []
    for r in log:
        if r.method == "GET" and r.status == status and r.range:
            first, last = r.range.removeprefix("bytes=").split("-")
            spans.append((int(first), int(last) + 1))
    return any(s <= start and end <= e for s, e in rangeserve.merge(spans))


def test_full_file(nfs_mount: Mounter, tmp_path: Path):
    src = tmp_path / "whole.tdf"
    src.write_bytes(content(0, 3 * MiB + 5))
    path, log = nfs_mount(FullFile(src))
    assert path.read_bytes() == src.read_bytes()
    gets = [r for r in log if r.method == "GET"]
    assert gets and all(r.status == 206 for r in gets)
    assert sum(r.bytes_served for r in gets) >= src.stat().st_size


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
    firsts = [(t - head) // stride * seg for t in targets]
    plan = rangeserve.retention_plan(
        [(p, p + 1) for p in firsts],
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

    reads = [(0, 64), *((t, t + 16) for t in targets), (logical - 22, logical)]
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
