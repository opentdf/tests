"""Run one command and report its resource usage, isolated from the caller.

Why this extra process exists
-----------------------------
On Linux a forked child inherits the parent's resident-set accounting, and
``execve`` does not clear it. ``ru_maxrss`` from ``wait4`` therefore comes back
as ``max(the child's true peak, the parent's RSS at fork time)``.

Measured straight from a pytest process holding numpy, scipy and a session's
worth of samples, every SDK invocation reports *pytest's* footprint -- about
165 MiB on a CI runner -- instead of its own. Every cell cheaper than that
reports the same number, so a peak-RSS comparison between two builds becomes a
comparison between two readings of the harness. It does not look broken: it
looks like a stable ratio of 1.000, which reads as "no regression".

``posix_spawn`` and ``sh -c 'exec ...'`` do not help. Both were measured on
Linux and both inherit the same floor; an exec is too late, the accounting is
already latched. The only fix is to fork the measured command from a process
that is holding nothing, which is what this one is for.

Its own RSS is the floor under every reading it produces, so it reports that
alongside them: a measurement sitting at the floor is censored, not small.

Private protocol -- :mod:`perf.measure` is the only caller::

    <python> -I -S _launcher.py <result-file> <timeout|-> <cmd> [args...]

One line of space-separated integers is written to ``<result-file>``::

    <status> <wall_ns> <utime_us> <stime_us> <maxrss_raw> <floor_bytes>
    <timed_out> <exec_errno>

``maxrss_raw`` is passed through in whatever unit the platform uses; the caller
normalizes it. ``floor_bytes`` is already bytes.
"""

import os
import signal
import sys
import time


class _Timeout(Exception):
    """Raised in the alarm handler to interrupt a blocking wait."""


def _on_alarm(_signum: int, _frame: object) -> None:
    raise _Timeout


def _current_rss_bytes() -> int:
    """This process's resident size right now -- the floor for its children."""
    try:
        with open("/proc/self/statm", "rb") as f:
            pages = int(f.read().split()[1])
    except OSError, IndexError, ValueError:
        # macOS has no /proc. Its ru_maxrss is already bytes, and it does not
        # show the inheritance above, so a high-water reading is close enough.
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return pages * os.sysconf("SC_PAGE_SIZE")


def _spawn(command: list[str], err_w: int) -> int:
    """Fork and exec ``command``, reporting a failed exec down ``err_w``."""
    pid = os.fork()
    if pid != 0:
        return pid
    try:
        # Its own process group, so a timeout kills the whole tree instead of
        # just the shim -- leaving a wedged JVM behind would hold the runner
        # until the job timeout.
        os.setpgid(0, 0)
        os.execvp(command[0], command)
    # BaseException, not Exception: this is a forked child, and letting a
    # SystemExit or a KeyboardInterrupt unwind past here would run the
    # *parent's* cleanup -- atexit handlers, buffered output -- a second time,
    # from a process that only exists to exec.
    except BaseException as e:  # noqa: BLE001  # NOSONAR - nothing escapes a fork
        try:
            os.write(err_w, str(getattr(e, "errno", 0) or 0).encode())
        except OSError:
            pass
    os._exit(127)


def _kill_tree(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        # setpgid may not have run yet; the bare process is all there is.
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def main(argv: list[str]) -> int:
    result_path, timeout_arg = argv[1], argv[2]
    command = argv[3:]
    timeout = None if timeout_arg == "-" else float(timeout_arg)

    # Closed by a successful exec; carries an errno if the exec never happened.
    err_r, err_w = os.pipe()

    floor = _current_rss_bytes()
    started = time.perf_counter_ns()
    pid = _spawn(command, err_w)
    os.close(err_w)

    timed_out = False
    if timeout is not None:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        _, status, ru = os.wait4(pid, 0)
    except _Timeout:
        timed_out = True
        _kill_tree(pid)
        _, status, ru = os.wait4(pid, 0)
    finally:
        if timeout is not None:
            # The alarm can fire between wait4 returning and the disarm below.
            # That is not a timeout -- the child already exited on its own --
            # but an escaping _Timeout would skip the result file entirely, and
            # measure() reads a missing file as "the launcher did not report".
            # A run that finished just under the limit would be reported as a
            # measurement failure. Swallow the late alarm and silence any
            # further one before the report is written.
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            except _Timeout:
                pass
            signal.signal(signal.SIGALRM, signal.SIG_IGN)
    elapsed = time.perf_counter_ns() - started

    exec_errno = os.read(err_r, 32) or b"0"
    os.close(err_r)

    fields = (
        status,
        elapsed,
        int(ru.ru_utime * 1e6),
        int(ru.ru_stime * 1e6),
        int(ru.ru_maxrss),
        floor,
        int(timed_out),
        int(exec_errno),
    )
    with open(result_path, "w") as f:
        f.write(" ".join(str(v) for v in fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
