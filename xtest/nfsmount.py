"""Mount a range-served file as an ordinary local file over NFSv3.

DSPX-5543. SDK CLIs all read local files at random offsets; they do not all
take URLs. ``nfsserve/`` is a small Go NFS server exporting one read-only
file, each NFS READ a Range GET to :func:`rangeserve.serve`, so the retention
plan, store and request log are the range server's.

A READ touching a dropped extent reads as :data:`FILLER`, not an error: the
kernel rounds an application's read out to whole NFS READs, and EIO there
fails the read of kept bytes too. Plan with ``retention_plan(..., pad=PAD)``
so ordinary reads stay inside kept bytes; AES-GCM still rejects filler if a
decrypt uses it.

macOS mounts without sudo. Linux needs ``mount.nfs`` (nfs-common) and
passwordless sudo. Mounts are soft, so a dead server cannot hang a reader.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

logger = logging.getLogger("xtest")

SRC = Path(__file__).parent / "nfsserve"

#: Dropped bytes read as this, repeated and aligned to file offset 0. Must
#: match ``filler`` in nfsserve/main.go.
FILLER = b"DROPPED!"

#: NFS READ size, set on the mount so it does not vary by client.
RSIZE = 64 << 10

#: Padding for :func:`rangeserve.retention_plan`: a 1 MiB buffered read from
#: the last planned byte, rounded out to RSIZE, stays kept.
PAD = 2 << 20


class Unavailable(Exception):
    """This host cannot mount; the message says why."""


class Mount(NamedTuple):
    file: Path
    server: subprocess.Popen[bytes]


def filler(start: int, end: int) -> bytes:
    """What dropped bytes ``[start, end)`` read as."""
    i = start % len(FILLER)
    return (FILLER * ((end - start) // len(FILLER) + 2))[i : i + end - start]


def _sudo() -> list[str]:
    return [] if sys.platform == "darwin" or os.geteuid() == 0 else ["sudo", "-n"]


def preflight() -> None:
    """Raise :class:`Unavailable` if this host cannot mount NFS."""
    if sys.platform == "darwin":
        return
    if sys.platform != "linux":
        raise Unavailable(f"no NFS mount support on {sys.platform}")
    if not (shutil.which("mount.nfs") or Path("/sbin/mount.nfs").exists()):
        raise Unavailable("mount.nfs is missing; install nfs-common")
    if (
        _sudo()
        and subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode
    ):
        raise Unavailable("mounting NFS on Linux needs passwordless sudo")


def build(out_dir: Path) -> Path:
    """Build the server into ``out_dir``; raise :class:`Unavailable` without Go."""
    go = shutil.which("go")
    if go is None:
        raise Unavailable("no Go toolchain to build nfsserve")
    binary = out_dir.resolve() / "nfsserve"
    tmp = binary.with_name(f"nfsserve.{os.getpid()}")
    r = subprocess.run(
        [go, "build", "-o", str(tmp), "."], cwd=SRC, capture_output=True, text=True
    )
    if r.returncode:
        raise RuntimeError(f"go build nfsserve failed:\n{r.stderr}")
    tmp.replace(binary)
    return binary


def mount_table() -> set[str]:
    """Paths currently mounted on."""
    if sys.platform == "linux":
        lines = Path("/proc/self/mounts").read_text().splitlines()
        octal = re.compile(r"\\([0-7]{3})")
        return {octal.sub(lambda m: chr(int(m[1], 8)), ln.split()[1]) for ln in lines}
    out = subprocess.run(["mount"], capture_output=True, text=True, check=True).stdout
    return {m[1] for m in re.finditer(r"^.+? on (.+) \([^()]*\)$", out, re.M)}


def _unmount(point: Path, *, force: bool = False) -> None:
    """Unmount ``point``, forcing if a plain unmount fails; raise if it stays."""
    if sys.platform == "darwin":
        plain, forced = ["umount"], ["umount", "-f"]
    else:
        plain, forced = [*_sudo(), "umount"], [*_sudo(), "umount", "-f", "-l"]
    err = ""
    for cmd in [forced] if force else [plain, forced]:
        r = subprocess.run(
            [*cmd, str(point)], capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0 or str(point) not in mount_table():
            return
        err = r.stderr.strip()
    raise RuntimeError(f"could not unmount {point}: {err}")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def reap(root: Path) -> None:
    """Unmount and remove mount points whose creating process has gone.

    Mount points are named ``<pid>.<suffix>``, so concurrent workers and runs
    leave each other's live mounts alone.
    """
    if not root.is_dir():
        return
    table = mount_table()
    for point in root.resolve().iterdir():
        pid = point.name.partition(".")[0]
        if not point.is_dir() or not pid.isdigit() or _alive(int(pid)):
            continue
        if str(point) in table:
            logger.warning("unmounting stale NFS mount %s", point)
            _unmount(point, force=True)
        with suppress(FileNotFoundError):
            point.rmdir()


def _stop(server: subprocess.Popen[bytes]) -> None:
    if server.stdin:
        server.stdin.close()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()


def _mount_cmd(port: int, point: Path) -> list[str]:
    if sys.platform == "darwin":
        opts = (
            f"vers=3,tcp,port={port},mountport={port},noresvport,nolocks,rdonly,"
            f"soft,intr,timeo=10,retrans=2,rsize={RSIZE},readahead=0,nobrowse"
        )
        return ["/sbin/mount_nfs", "-o", opts, "127.0.0.1:/", str(point)]
    opts = (
        f"vers=3,proto=tcp,port={port},mountport={port},mountproto=tcp,nolock,ro,"
        f"soft,timeo=10,retrans=2,rsize={RSIZE},wsize={RSIZE},nosharecache"
    )
    return [*_sudo(), "mount", "-t", "nfs", "-o", opts, "127.0.0.1:/", str(point)]


def _no_readahead(point: Path) -> None:
    """Linux reads ahead of sequential NFS reads unless told not to."""
    dev = point.stat().st_dev
    knob = f"/sys/class/bdi/{os.major(dev)}:{os.minor(dev)}/read_ahead_kb"
    subprocess.run(
        [*_sudo(), "tee", knob], input=b"0\n", stdout=subprocess.DEVNULL, check=True
    )


@contextmanager
def mounted(url: str, root: Path, binary: Path) -> Iterator[Mount]:
    """Export ``url`` over NFS, mount it under ``root``, and yield the file.

    On exit, always unmounts (forcing if need be), stops the server and
    removes the mount point.
    """
    root.mkdir(parents=True, exist_ok=True)
    point = Path(tempfile.mkdtemp(prefix=f"{os.getpid()}.", dir=root.resolve()))
    with tempfile.TemporaryFile() as stderr:
        # Own session: a terminal's Ctrl-C must not stop the server before
        # teardown has unmounted.
        server = subprocess.Popen(
            [str(binary), "-url", url],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            start_new_session=True,
        )

        def server_log() -> str:
            stderr.seek(0)
            return stderr.read().decode(errors="replace")

        try:
            assert server.stdout
            port = server.stdout.readline().strip()
            if not port.isdigit():
                raise RuntimeError(f"nfsserve did not start:\n{server_log()}")
            r = subprocess.run(
                _mount_cmd(int(port), point), capture_output=True, text=True, timeout=60
            )
            if r.returncode:
                raise RuntimeError(f"mount failed: {r.stderr.strip()}\n{server_log()}")
            if sys.platform == "linux":
                _no_readahead(point)
            yield Mount(point / Path(urlparse(url).path).name, server)
        finally:
            try:
                if str(point) in mount_table():
                    _unmount(point)
            finally:
                _stop(server)
                if log := server_log():
                    logger.info("nfsserve %s:\n%s", url, log)
                with suppress(OSError):
                    point.rmdir()
