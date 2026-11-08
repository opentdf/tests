"""Partial decrypt of a TDF too large to store, through an NFS mount (DSPX-5545).

Each SDK encrypts ``--sparse`` bytes of generated plaintext (100 GiB + 112 KiB
on the weekly run, so the last segment is short) once. The ciphertext streams into a store that keeps only the
extents the planned reads need, plus the ZIP tail, so local disk holds the
manifest and a few segments. Every reader then partially decrypts each
planned range from an NFS mount of the store (DSPX-5543), as an ordinary
seekable file, and the output is checked against the generator by position.

Dropped extents read as filler, not errors, so a passing decrypt does not
prove the reader stayed inside the plan; the mount's request log does, under
the per-PR NFS cells' bound (DSPX-5544).

This is partial-read capability, not a full decrypt.
"""

import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import pytest

import nfsmount
import rangeserve
import streamharness as sh
import tdfs
from fixtures.nfs_mount import Mounter, nfs_root
from fixtures.sparse import Settings, plan_ranges, range_names
from fixtures.streaming import encrypt_command
from test_partial_decrypt import SOURCES, Layout, fetch_budget, read_extent

pytestmark = pytest.mark.sparse

#: What scratch may hold beyond the plan and the manifest: the ZIP's headers,
#: directory and end records, the harness's files, and whatever a CLI leaves
#: in its TMPDIR.
DISK_OVERHEAD = 16 << 20

#: web-sdk's GLOBAL_BYTE_LIMIT, the lowest encrypt cap any SDK has had.
ENCRYPT_CAP = 64 * 10**9

#: Partial reads are at most a segment or two, so a file costs nothing; the
#: input is the mount, which go and java need to be seekable.
DECRYPT_ROUTE = sh.Route("file", "file")


class _Sink(rangeserve.SparseSink):
    """A SparseSink that remembers the store it closed into."""

    store: rangeserve.ExtentStore | None = None

    def close(self) -> rangeserve.ExtentStore:
        self.store = super().close()
        return self.store


@dataclass(frozen=True)
class SparseTdf:
    """One SDK's encrypt, as far as the store kept it."""

    store: rangeserve.ExtentStore
    #: Scratch for this SDK's runs; holds the store.
    root: Path
    plaintext: sh.Plaintext
    route: sh.Route
    segment_size: int
    payload_start: int
    payload_end: int
    ranges: dict[str, tuple[int, int]]
    plan: list[tuple[int, int]]
    run: sh.Run[sh.TdfEvidence]
    peak_disk: int

    @property
    def plan_bytes(self) -> int:
        return sum(e - s for s, e in self.plan)

    @property
    def layout(self) -> Layout:
        return Layout(
            self.payload_start,
            self.payload_end,
            self.store.length,
            self.run.result.manifest.segment_count,
        )


@contextmanager
def _mounted(source: rangeserve.Source, *, root: Path, binary: Path) -> Iterator[Path]:
    """``source`` as a local file, for a CLI that will not read a FIFO."""
    with (
        rangeserve.serve(source, "plaintext.bin") as (url, _),
        nfsmount.mounted(url, root, binary) as m,
    ):
        yield m.file


def _encrypt(
    sdk: tdfs.SDK, cfg: Settings, probe: sh.Probe, tmp_dir: Path, binary: Path
) -> SparseTdf:
    n = cfg.size
    if n > ENCRYPT_CAP and not sdk.supports("encrypt_over_64gb"):
        pytest.skip(f"{sdk} refuses to encrypt over 64 GB [encrypt_over_64gb]")
    # The plan is in ciphertext offsets, so it follows the probe's route.
    assert probe.encrypt.run is not None
    evidence = probe.encrypt.run.result
    seg = evidence.manifest.segment_size_default
    start = evidence.payload_start
    if start is None or seg <= 0:
        pytest.fail(
            f"{sdk}'s probe TDF has payload_start {start} and {seg}-byte "
            "segments; no plan fits"
        )
    if cfg.segment_size and seg != cfg.segment_size:
        pytest.skip(
            f"{sdk} writes {seg}-byte segments and its CLI cannot be told to "
            f"write {cfg.segment_size}"
        )
    ranges = plan_ranges(n, seg, cfg.seed)
    assert list(ranges) == range_names(n)
    # The segment count is not known yet; java adds one after a whole number.
    # Keeping the widening for the last data segment covers either count.
    plan = rangeserve.retention_plan(
        [read_extent(seg, -(-n // seg), *r) for r in ranges.values()],
        plaintext_length=n,
        segment_size=seg,
        payload_start=start,
        pad=nfsmount.PAD,
    )
    root = tmp_dir / "sparse" / f"{sdk.sdk}-{sdk.version.replace('/', '-')}"
    shutil.rmtree(root, ignore_errors=True)
    (root / "store").mkdir(parents=True)
    # ~110 bytes of manifest per segment; DEFAULT_TAIL_CEILING covers 100 GiB.
    tail_ceiling = max(sh.DEFAULT_TAIL_CEILING, 256 * -(-n // seg))
    sink = _Sink(
        root / "store",
        plan,
        tail_ceiling=tail_ceiling,
        payload_start=start,
        plaintext_length=n,
        segment_size=seg,
    )
    plaintext = sh.Plaintext(n)
    plan_bytes = sum(e - s for s, e in plan)
    try:
        run = sh.encrypt(
            encrypt_command(sdk),
            plaintext,
            route=probe.encrypt.route,
            scratch=root,
            # The tail lands at close, after the last sample; asserted below.
            budget=sh.Budget(
                timeout_s=cfg.timeout_s,
                max_scratch_bytes=plan_bytes + DISK_OVERHEAD,
            ),
            downstream=sink,
            tail_ceiling=tail_ceiling,
            mount=partial(_mounted, root=nfs_root(tmp_dir), binary=binary),
        )
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    assert sink.store is not None and sink.tail_start is not None
    return SparseTdf(
        store=sink.store,
        root=root,
        plaintext=plaintext,
        route=probe.encrypt.route,
        segment_size=seg,
        payload_start=start,
        payload_end=sink.tail_start,
        ranges=ranges,
        plan=plan,
        run=run,
        peak_disk=max(run.peak_scratch_bytes, sink.store.physical_size),
    )


@pytest.fixture(scope="session")
def sparse_tdfs(
    sparse_settings: Settings,
    stream_probe: Callable[[tdfs.SDK], sh.Probe],
    nfsserve_binary: Path,
    tmp_dir: Path,
) -> Iterator[Callable[[tdfs.SDK], SparseTdf]]:
    """Encrypt once per SDK; later cells get the store, or the first outcome."""
    done: dict[tdfs.SDK, SparseTdf | BaseException] = {}

    def get(sdk: tdfs.SDK) -> SparseTdf:
        if sdk not in done:
            try:
                done[sdk] = _encrypt(
                    sdk, sparse_settings, stream_probe(sdk), tmp_dir, nfsserve_binary
                )
            except (Exception, pytest.skip.Exception, pytest.fail.Exception) as e:
                done[sdk] = e
                raise
        t = done[sdk]
        if isinstance(t, pytest.skip.Exception):
            pytest.skip(t.msg or "")
        if isinstance(t, BaseException):
            pytest.fail(f"{sdk} encrypt failed: {t!r}"[:500], pytrace=False)
        return t

    yield get
    for t in done.values():
        if isinstance(t, SparseTdf):
            t.store.close()
            shutil.rmtree(t.root, ignore_errors=True)


def test_sparse_encrypt(
    encrypt_sdk: tdfs.SDK,
    sparse_settings: Settings,
    sparse_tdfs: Callable[[tdfs.SDK], SparseTdf],
    sparse_row: dict[str, Any],
) -> None:
    n = sparse_settings.size
    t = sparse_tdfs(encrypt_sdk)
    m = t.run.result.manifest
    disk_bound = t.plan_bytes + m.size + DISK_OVERHEAD
    sparse_row.update(
        route=str(t.route),
        payload_start=t.payload_start,
        segment_size=t.segment_size,
        segment_count=m.segment_count,
        manifest_bytes=m.size,
        wall_s=t.run.wall_s,
        cpu_s=t.run.cpu_s,
        throughput_bps=n / t.run.wall_s if t.run.wall_s else None,
        peak_rss_bytes=t.run.peak_rss_bytes,
        plan_bytes=t.plan_bytes,
        retained_bytes=t.store.physical_size,
        peak_disk_bytes=t.peak_disk,
        disk_bound_bytes=disk_bound,
        tdf_bytes=t.store.length,
        ranges={k: list(v) for k, v in t.ranges.items()},
    )
    assert t.run.bytes_in == n
    assert t.peak_disk <= disk_bound, (
        f"scratch peaked at {t.peak_disk} bytes; the plan ({t.plan_bytes}), "
        f"manifest ({m.size}) and overhead ({DISK_OVERHEAD}) allow {disk_bound}"
    )


def test_sparse_partial_decrypt(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    sparse_range: str,
    sparse_settings: Settings,
    sparse_tdfs: Callable[[tdfs.SDK], SparseTdf],
    nfs_mount: Mounter,
    sparse_row: dict[str, Any],
) -> None:
    decrypt_sdk.skip_if_unsupported("partial_decrypt")
    t = sparse_tdfs(encrypt_sdk)
    if t.run.result.manifest.elided_sizes and not decrypt_sdk.supports("chunky"):
        pytest.skip(
            f"{decrypt_sdk} sdk doesn't yet support [chunky]: {encrypt_sdk} omits "
            "per-segment sizes"
        )
    n = sparse_settings.size
    start, end = t.ranges[sparse_range]
    sparse_row.update(start=start, end=end)

    # A mount per cell: nothing cached by an earlier read can hide a fetch.
    path, log = nfs_mount(t.store, "sparse.tdf")

    def command(src: Path, dst: Path) -> tuple[list[str], dict[str, str]]:
        return decrypt_sdk.decrypt_command(
            src, dst, "ztdf", plaintext_range=(start, end - start)
        )

    run = sh.decrypt(
        command,
        path,
        lambda at, k: t.plaintext(start + at, k),
        end - start,
        route=DECRYPT_ROUTE,
        scratch=t.root,
        budget=sh.Budget(timeout_s=600),
    )

    # Every READ counts, including those of dropped bytes: 410s, read as filler.
    reads = [
        (r.start, r.end, r.status)
        for r in log
        if r.start is not None and r.end is not None
    ]
    fetched = sum(e - s for s, e, _ in reads)
    bound = fetch_budget(t.layout, t.segment_size, n, start, end, SOURCES["nfs"])
    disk_bound = t.store.physical_size + (end - start) + DISK_OVERHEAD
    sparse_row.update(
        wall_s=run.wall_s,
        peak_rss_bytes=run.peak_rss_bytes,
        fetched_bytes=fetched,
        served_bytes=sum(r.bytes_served for r in log),
        fetch_bound_bytes=bound,
        reads=len(reads),
        filler_reads=sum(status == 410 for *_, status in reads),
        peak_disk_bytes=run.peak_scratch_bytes,
        disk_bound_bytes=disk_bound,
    )
    assert fetched <= bound, (
        f"reader fetched {fetched} bytes of a {t.store.length}-byte TDF for "
        f"plaintext {start}-{end}; bound {bound}. READs: {reads}"
    )
    assert run.peak_scratch_bytes <= disk_bound
