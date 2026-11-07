"""The DSPX-5543 NFS front end as a fixture: a range server source as a local file.

Skips where this host cannot mount. ``XT_NFS_REQUIRED=1`` makes that a
failure instead, so CI cannot pass by skipping.
"""

import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest

import nfsmount
import rangeserve


def nfs_root(tmp_dir: Path) -> Path:
    """Where every worker's mount points live, so a later run can reap them."""
    return tmp_dir.parent / "nfs"


@pytest.fixture(scope="session")
def nfsserve_binary(tmp_dir: Path) -> Path:
    """The built server, once stale mounts from killed runs are gone."""
    try:
        nfsmount.preflight()
        binary = nfsmount.build(tmp_dir)
    except nfsmount.Unavailable as e:
        if os.environ.get("XT_NFS_REQUIRED", "").lower() in ("1", "true", "yes"):
            pytest.fail(f"XT_NFS_REQUIRED is set, but {e}")
        pytest.skip(str(e))
    nfsmount.reap(nfs_root(tmp_dir))
    return binary


@pytest.fixture
def nfs_mount(
    nfsserve_binary: Path, tmp_dir: Path
) -> Iterator[Callable[[rangeserve.Source], tuple[Path, list[rangeserve.Request]]]]:
    """Call with a source; returns ``(path, request_log)``. Any number per test.

    ``path`` is a mounted read-only file backed by the source; the log is the
    range server's, one entry per NFS READ that reached it.
    """
    with ExitStack() as stack:

        def mount(source: rangeserve.Source) -> tuple[Path, list[rangeserve.Request]]:
            url, log = stack.enter_context(rangeserve.serve(source))
            m = nfsmount.mounted(url, nfs_root(tmp_dir), nfsserve_binary)
            return stack.enter_context(m).file, log

        yield mount
