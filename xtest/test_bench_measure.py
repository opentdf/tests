"""Unit tests for ``perf/measure.py``.

No platform and no SDK: these drive small Python and shell children with known
resource profiles, so they run in ``check.yml`` next to the stats tests.

Tolerances are deliberately loose. The point is to catch a primitive that is
plain wrong -- reporting kilobytes as bytes, missing a grandchild's CPU,
returning the parent's memory instead of the child's -- not to assert precise
timings on a shared runner.
"""

import os
import subprocess
import sys
import textwrap

import pytest

from perf import measure
from perf.measure import MeasurementError, Sample

pytestmark = pytest.mark.skipif(
    not hasattr(os, "wait4"),
    reason="per-process rusage requires os.wait4",
)


def python_child(body: str) -> list[str]:
    """Build an argv running a short Python snippet as a child process."""
    return [sys.executable, "-c", textwrap.dedent(body)]


class TestWallClock:
    def test_tracks_sleep_duration(self):
        s = measure.measure(python_child("import time; time.sleep(0.25)"))
        assert 0.2 < s.wall_s < 1.5

    def test_wall_s_matches_wall_ns(self):
        s = measure.measure(python_child("pass"))
        assert s.wall_s == pytest.approx(s.wall_ns / 1e9)


class TestCpuTime:
    def test_sleeping_child_burns_almost_no_cpu(self):
        s = measure.measure(python_child("import time; time.sleep(0.5)"))
        # Interpreter startup costs some CPU, but far less than the wall time.
        assert s.cpu_s < s.wall_s

    def test_busy_child_burns_cpu_close_to_wall_time(self):
        s = measure.measure(
            python_child(
                """
                import time
                end = time.perf_counter() + 0.5
                while time.perf_counter() < end:
                    pass
                """
            )
        )
        assert s.cpu_s > 0.3

    def test_includes_grandchild_cpu(self):
        # The SDK shims are bash wrappers around a real binary, so a
        # measurement that misses grandchildren would report near-zero CPU for
        # every SDK operation.
        busy = (
            "import time\n"
            "end = time.perf_counter() + 0.5\n"
            "while time.perf_counter() < end: pass\n"
        )
        s = measure.measure(
            [
                "/bin/sh",
                "-c",
                f"{sys.executable} -c {subprocess.list2cmdline([busy])}",
            ]
        )
        assert s.cpu_s > 0.3, "grandchild CPU was not folded into the parent's rusage"


def ballast_child(mb: int) -> list[str]:
    """A child that allocates ``mb`` MiB and touches every page of it."""
    return python_child(
        f"""
        ballast = bytearray({mb} * 1024 * 1024)
        ballast[::4096] = b'x' * len(ballast[::4096])
        """
    )


class TestPeakRss:
    def test_reports_ballast_in_bytes(self):
        # Allocate ~200 MB and confirm the figure is in bytes, not kilobytes.
        # Getting the unit wrong is a 1024x error that a loose bound catches.
        s = measure.measure(
            python_child(
                """
                ballast = bytearray(200 * 1024 * 1024)
                ballast[::4096] = b'x' * len(ballast[::4096])
                """
            )
        )
        assert 150 * 2**20 < s.max_rss_bytes < 1200 * 2**20

    def test_larger_allocation_reports_larger_peak(self):
        def peak(mb: int) -> int:
            return measure.measure(ballast_child(mb)).max_rss_bytes

        assert peak(200) > peak(20) + 100 * 2**20

    def test_a_fat_measuring_process_does_not_inflate_a_small_child(self):
        # The failure this guards against does not look like a failure. On
        # Linux a forked child inherits the parent's resident-set accounting
        # and exec does not clear it, so every command cheaper than the pytest
        # process reported the pytest process's memory instead of its own --
        # a stable, plausible number that reads as "no regression" forever.
        #
        # Holding real ballast here is the only way to reproduce it: with a
        # slim parent the bug is invisible, which is exactly why it reached CI.
        lean = measure.measure(ballast_child(20)).max_rss_bytes
        ballast = bytearray(400 * 2**20)
        try:
            ballast[::4096] = b"x" * len(ballast[::4096])
            fat = measure.measure(ballast_child(20)).max_rss_bytes
        finally:
            del ballast
        assert fat < lean + 100 * 2**20, (
            f"measuring from a 400 MiB process reported {fat / 2**20:.0f} MiB "
            f"for a child that reads {lean / 2**20:.0f} MiB from a lean one"
        )

    def test_reports_the_floor_under_the_reading(self):
        # A peak RSS cannot be measured below the memory of whatever forked
        # the process, so the floor travels with the sample and callers can
        # tell a censored reading from a genuinely small one.
        s = measure.measure(ballast_child(200))
        assert 0 < s.rss_floor_bytes < 100 * 2**20
        assert not s.rss_is_floored

    def test_a_reading_at_the_floor_is_marked_censored(self):
        floored = Sample(
            wall_ns=1,
            cpu_s=0.0,
            max_rss_bytes=12 * 2**20,
            exit_code=0,
            rss_floor_bytes=12 * 2**20,
        )
        assert floored.rss_is_floored
        assert not Sample(
            wall_ns=1,
            cpu_s=0.0,
            max_rss_bytes=80 * 2**20,
            exit_code=0,
            rss_floor_bytes=12 * 2**20,
        ).rss_is_floored

    def test_includes_grandchild_memory(self):
        alloc = ballast_child(200)[2]
        s = measure.measure(
            [
                "/bin/sh",
                "-c",
                f"{sys.executable} -c {subprocess.list2cmdline([alloc])}",
            ]
        )
        assert s.max_rss_bytes > 150 * 2**20


class TestFailureHandling:
    def test_non_zero_exit_raises_by_default(self):
        with pytest.raises(MeasurementError, match="exited 3"):
            measure.measure(python_child("raise SystemExit(3)"))

    def test_error_includes_child_stderr(self):
        with pytest.raises(MeasurementError, match="disaster strikes"):
            measure.measure(
                python_child(
                    "import sys; sys.stderr.write('disaster strikes'); sys.exit(1)"
                )
            )

    def test_check_false_returns_the_failing_sample(self):
        s = measure.measure(python_child("raise SystemExit(7)"), check=False)
        assert s.exit_code == 7

    def test_missing_executable_raises(self):
        with pytest.raises(MeasurementError, match="could not start"):
            measure.measure(["/nonexistent/definitely-not-a-real-binary"])

    def test_timeout_kills_and_raises(self):
        with pytest.raises(MeasurementError, match="measurement timeout"):
            measure.measure(python_child("import time; time.sleep(30)"), timeout_s=0.5)

    def test_large_output_does_not_deadlock(self):
        # os.wait4 does not drain pipes. If stdout were a pipe, a child writing
        # more than the pipe buffer would block forever and hang the job.
        s = measure.measure(
            python_child("import sys; sys.stdout.write('x' * 5_000_000)")
        )
        assert s.exit_code == 0


class TestMetricAccess:
    def test_metric_lookup_matches_fields(self):
        s = Sample(wall_ns=1_500_000, cpu_s=0.25, max_rss_bytes=2**20, exit_code=0)
        assert s.metric("wall") == 1_500_000
        assert s.metric("cpu") == 0.25
        assert s.metric("rss") == 2**20

    def test_unknown_metric_raises(self):
        s = Sample(wall_ns=1, cpu_s=1.0, max_rss_bytes=1, exit_code=0)
        with pytest.raises(KeyError):
            s.metric("bogus")

    def test_every_declared_metric_is_retrievable(self):
        s = Sample(wall_ns=1, cpu_s=1.0, max_rss_bytes=1, exit_code=0)
        for name in measure.METRICS:
            assert isinstance(s.metric(name), float)
            assert name in measure.METRIC_LABELS

    def test_formatting(self):
        cases = [
            ("wall", 1_500_000.0, "1.5 ms"),
            ("cpu", 0.25, "0.250 s"),
            ("rss", float(2**21), "2.0 MiB"),
        ]
        assert [measure.format_metric(n, v) for n, v, _ in cases] == [
            e for _, _, e in cases
        ]

    def test_formatting_rejects_unknown_metric(self):
        with pytest.raises(KeyError):
            measure.format_metric("bogus", 1.0)
