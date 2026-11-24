"""The DSPX-5543 NFS front end as a fixture: a range server source as a local file.

Skips where a local host cannot mount. In CI, missing mount support fails
instead, so a job cannot pass by skipping the NFS tests.
"""

import os
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Protocol

import pytest

import nfsmount
import rangeserve


class Mounter(Protocol):
    def __call__(
        self, source: rangeserve.Source, name: str = ...
    ) -> tuple[Path, list[rangeserve.Request]]: ...


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
        if os.environ.get("CI", "").lower() in ("1", "true", "yes"):
            pytest.fail(f"CI requires NFS mount support, but {e}")
        pytest.skip(str(e))
    nfsmount.reap(nfs_root(tmp_dir))
    return binary


@pytest.fixture
def nfs_mount(nfsserve_binary: Path, tmp_dir: Path) -> Iterator[Mounter]:
    """Call with a source; returns ``(path, request_log)``. Any number per test.

    ``path`` is a mounted read-only file backed by the source, named ``name``;
    the log is the range server's: a HEAD, then a GET per NFS READ. Each
    mount is torn down before its range server, which joins its handlers.
    """
    with ExitStack() as stack:

        def mount(
            source: rangeserve.Source, name: str = "payload.tdf"
        ) -> tuple[Path, list[rangeserve.Request]]:
            url, log = stack.enter_context(rangeserve.serve(source, name))
            m = nfsmount.mounted(url, nfs_root(tmp_dir), nfsserve_binary)
            return stack.enter_context(m).file, log

        yield mount
