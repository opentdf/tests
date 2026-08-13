"""Resource measurement for a single SDK CLI invocation.

Measures wall-clock time, CPU time, and peak resident memory for one child
process and everything it spawns. The SDK CLIs are bash shims that exec a Go
binary, a JVM, or node, so "everything it spawns" is the interesting part.

Why ``os.wait4`` rather than ``resource.getrusage``
---------------------------------------------------
``resource.getrusage(RUSAGE_CHILDREN)`` reports a *process-lifetime* high-water
mark for ``ru_maxrss``. Subtracting successive readings does not give the peak
of the most recent child -- once one big child has run, every later delta reads
zero. ``os.wait4`` returns rusage for the specific child being reaped, which is
what we actually want.

The kernel folds a child's reaped descendants into its rusage, so the shim's
``java``/``node``/``otdfctl`` grandchild is included: CPU times sum and
``ru_maxrss`` takes the maximum. Both are the right aggregation here.

Why the command is not spawned from this process
------------------------------------------------
A forked child inherits the parent's resident-set accounting on Linux, and
exec does not clear it, so ``ru_maxrss`` would report the *measuring* process's
memory whenever the measured command uses less. Everything therefore goes
through :mod:`perf._launcher`, which holds nothing and forks the real command
itself. That module's docstring has the measurements behind this.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from typing import IO

#: ``ru_maxrss`` is kilobytes on Linux and bytes on macOS. There is no portable
#: way to ask, so branch on the platform.
_RSS_SCALE = 1 if sys.platform == "darwin" else 1024

#: How much of a failing child's stderr to keep for the error message.
_STDERR_TAIL_BYTES = 4000

_LAUNCHER = Path(__file__).with_name("_launcher.py")

#: Grace period on top of the launcher's own timeout, before this process
#: gives up on it. Only reachable if the launcher itself wedges.
_LAUNCHER_GRACE_S = 30.0


class MeasurementError(RuntimeError):
    """A measured invocation failed, timed out, or could not be measured.

    Benchmarking an operation that does not succeed is worse than not
    benchmarking it: a build that errors out early looks fast.
    """


@dataclass(frozen=True, slots=True)
class Sample:
    """Resource usage of one CLI invocation."""

    #: Wall-clock duration including fork/exec, which is part of the real cost.
    wall_ns: int
    #: User + system CPU seconds, summed over the process tree.
    cpu_s: float
    #: Peak resident set size in bytes, maximum over the process tree.
    max_rss_bytes: int
    exit_code: int
    #: RSS of the launcher at fork time. A child cannot be measured below the
    #: memory of whatever forked it, so a reading at this value is censored
    #: rather than small. Reported so that fact is visible.
    rss_floor_bytes: int = 0

    @property
    def rss_is_floored(self) -> bool:
        """Whether peak RSS is indistinguishable from the measurement floor."""
        return self.rss_floor_bytes > 0 and self.max_rss_bytes <= self.rss_floor_bytes

    @property
    def wall_s(self) -> float:
        return self.wall_ns / 1e9

    def metric(self, name: str) -> float:
        """Return a metric by name, for generic iteration over metric sets."""
        match name:
            case "wall":
                return float(self.wall_ns)
            case "cpu":
                return self.cpu_s
            case "rss":
                return float(self.max_rss_bytes)
            case _:
                raise KeyError(f"unknown metric {name!r}")


#: Metrics a :class:`Sample` can report, in display order.
METRICS: tuple[str, ...] = ("wall", "cpu", "rss")

#: Human-facing labels and units, keyed by metric name.
METRIC_LABELS: dict[str, tuple[str, str]] = {
    "wall": ("wall clock", "ms"),
    "cpu": ("cpu time", "s"),
    "rss": ("peak rss", "MiB"),
}


def format_metric(name: str, value: float) -> str:
    """Render a raw metric value in its display unit."""
    match name:
        case "wall":
            return f"{value / 1e6:.1f} ms"
        case "cpu":
            return f"{value:.3f} s"
        case "rss":
            return f"{value / 2**20:.1f} MiB"
        case _:
            raise KeyError(f"unknown metric {name!r}")


def measure(
    argv: list[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    *,
    timeout_s: float | None = 600.0,
    check: bool = True,
) -> Sample:
    """Run ``argv`` once and return its resource usage.

    Args:
        argv: command to run, already fully constructed.
        env: complete environment for the child (not merged with the parent's).
        cwd: working directory for the child.
        timeout_s: kill the child after this long. ``None`` waits forever,
            which will hang a CI job on a wedged CLI.
        check: raise :class:`MeasurementError` on a non-zero exit.

    Raises:
        MeasurementError: on non-zero exit (when ``check``), on timeout, or if
            the process could not be started.
    """
    if not hasattr(os, "wait4"):  # pragma: no cover - Unix-only test suite
        raise MeasurementError(
            "per-process rusage requires os.wait4, which this platform lacks"
        )

    # Redirect to real files rather than pipes: nothing here drains a pipe, so
    # a child that fills its stdout buffer would deadlock against us.
    with (
        tempfile.TemporaryFile() as out,
        tempfile.TemporaryFile() as err,
        tempfile.TemporaryDirectory() as scratch,
    ):
        result_path = Path(scratch) / "rusage"
        launcher_argv = [
            sys.executable,
            "-I",
            "-S",
            str(_LAUNCHER),
            str(result_path),
            "-" if timeout_s is None else repr(float(timeout_s)),
            *argv,
        ]
        try:
            proc = subprocess.Popen(
                launcher_argv, stdout=out, stderr=err, env=env, cwd=cwd
            )
        except OSError as e:  # pragma: no cover - our own interpreter is missing
            raise MeasurementError(
                f"could not start the measurement launcher: {e}"
            ) from e

        # The launcher enforces the real timeout and kills the measured process
        # group. This only covers the launcher itself wedging.
        backstop: threading.Timer | None = None
        if timeout_s is not None:
            backstop = threading.Timer(timeout_s + _LAUNCHER_GRACE_S, proc.kill)
            backstop.daemon = True
            backstop.start()
        try:
            proc.wait()
        finally:
            if backstop is not None:
                backstop.cancel()

        reading = _read_result(result_path, argv)
        if reading.exec_errno:
            raise MeasurementError(
                f"could not start {argv[0]!r}: {os.strerror(reading.exec_errno)}"
            )
        if reading.timed_out:
            raise MeasurementError(
                f"{argv[0]!r} exceeded the {timeout_s:g}s measurement timeout"
            )

        sample = Sample(
            wall_ns=reading.wall_ns,
            cpu_s=(reading.utime_us + reading.stime_us) / 1e6,
            max_rss_bytes=reading.maxrss_raw * _RSS_SCALE,
            exit_code=os.waitstatus_to_exitcode(reading.status),
            rss_floor_bytes=reading.floor_bytes,
        )
        if check and sample.exit_code != 0:
            raise MeasurementError(
                f"{' '.join(argv)} exited {sample.exit_code}\nstderr: {_tail(err)}"
            )
        return sample


@dataclass(frozen=True, slots=True)
class _Reading:
    """The launcher's raw report, before it is turned into a :class:`Sample`."""

    status: int
    wall_ns: int
    utime_us: int
    stime_us: int
    maxrss_raw: int
    floor_bytes: int
    timed_out: int
    exec_errno: int


#: Integers the launcher writes, one per :class:`_Reading` field.
_RESULT_FIELD_COUNT = len(fields(_Reading))


def _read_result(path: Path, argv: list[str]) -> _Reading:
    """Parse the launcher's report, or say clearly that it never made one."""
    try:
        fields = [int(v) for v in path.read_text().split()]
    except (OSError, ValueError) as e:
        raise MeasurementError(
            f"the measurement launcher did not report on {argv[0]!r}: {e}"
        ) from e
    if len(fields) != _RESULT_FIELD_COUNT:
        raise MeasurementError(
            f"the measurement launcher reported {len(fields)} fields for "
            f"{argv[0]!r}, expected {_RESULT_FIELD_COUNT}"
        )
    return _Reading(*fields)


def _tail(fh: IO[bytes]) -> str:
    """Read the last few KiB of a temp file, for error messages."""
    try:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - _STDERR_TAIL_BYTES))
        return fh.read().decode(errors="replace").strip()
    except OSError:  # pragma: no cover - defensive
        return "<unreadable>"
