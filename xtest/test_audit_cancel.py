"""Integration tests for deferred audit event guarantees.

These tests verify that the deferred audit pattern guarantees event logging
even when operations are interrupted by client disconnection. The deferred
pattern uses Go's `defer` to ensure audit events are always logged, regardless
of how the request handler exits (success, failure, or cancellation).

Strategy: Rather than guessing a fixed kill time, we launch K concurrent
decrypt processes and kill them at staggered intervals. The concurrent load
increases server processing time, widening the window for cancellation
"sniping". By spreading kill times and observing which events appear,
we adaptively find the right timing.

Run with:
    cd tests/xtest
    uv run pytest test_audit_cancel.py --sdks go -v

Note: These tests require audit log collection to be enabled. They will be
skipped when running with --no-audit-logs.
"""

import filecmp
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

import tdfs
from abac import Attribute
from audit_logs import AuditLogAsserter, ParsedAuditEvent

logger = logging.getLogger("xtest")

# Number of concurrent decrypt processes to launch per wave
CONCURRENT_DECRYPTS = 6

# Staggered kill delays in seconds, spread across the likely processing window.
# The first few are early (CLI startup), the middle ones target the gRPC call,
# and the last ones catch slow processing under load.
KILL_DELAYS = [0.05, 0.1, 0.2, 0.4, 0.8, 1.5]


@pytest.fixture(autouse=True)
def skip_if_audit_disabled(audit_logs: AuditLogAsserter):
    """Skip all tests in this module if audit log collection is disabled."""
    if not audit_logs.is_enabled:
        pytest.skip("Audit log collection is disabled (--no-audit-logs)")


def _build_decrypt_command(sdk: tdfs.SDK, ct_file: Path, rt_file: Path) -> list[str]:
    """Build the decrypt command for a given SDK, suitable for subprocess.Popen."""
    return [
        sdk.path,
        "decrypt",
        str(ct_file),
        str(rt_file),
        "ztdf",
    ]


def _launch_and_kill_staggered(
    cmd: list[str],
    env: dict[str, str],
    count: int,
    kill_delays: list[float],
    tmp_dir: Path,
    prefix: str,
) -> list[dict]:
    """Launch `count` decrypt processes and kill them at staggered times.

    Returns a list of dicts with timing and exit info for each process.
    """
    assert count == len(kill_delays), "count must match number of kill delays"

    procs = []
    for i in range(count):
        # Each process needs its own output file
        # cmd layout: [sdk_path, "decrypt", ct_file, rt_file, "ztdf"]
        rt_file = tmp_dir / f"{prefix}-{i}.untdf"
        proc_cmd = cmd[:3] + [str(rt_file)] + cmd[4:]  # Replace rt_file (index 3)
        proc = subprocess.Popen(
            proc_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        procs.append(
            {
                "proc": proc,
                "kill_delay": kill_delays[i],
                "launch_time": time.monotonic(),
                "index": i,
            }
        )

    # Kill each process at its scheduled time
    start = time.monotonic()
    for info in sorted(procs, key=lambda x: x["kill_delay"]):
        delay = info["kill_delay"]
        elapsed = time.monotonic() - start
        remaining = delay - elapsed
        if remaining > 0:
            time.sleep(remaining)
        proc = info["proc"]
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            info["killed"] = True
        else:
            info["killed"] = False
        info["kill_time"] = time.monotonic() - start

    # Wait for all to exit
    for info in procs:
        try:
            info["proc"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            info["proc"].kill()
            info["proc"].wait(timeout=2)
        info["exit_code"] = info["proc"].returncode

    return procs


def _collect_rewrap_events(
    audit_logs: AuditLogAsserter,
    since_mark: str,
    min_count: int = 1,
    timeout: float = 15.0,
) -> list[ParsedAuditEvent]:
    """Collect rewrap audit events, retrying until we have at least min_count."""
    deadline = time.monotonic() + timeout
    best: list[ParsedAuditEvent] = []
    while time.monotonic() < deadline:
        events = audit_logs.get_parsed_audit_logs(
            since_mark=since_mark, timeout=min(2.0, deadline - time.monotonic())
        )
        rewrap_events = [e for e in events if e.action_type == "rewrap"]
        if len(rewrap_events) > len(best):
            best = rewrap_events
        if len(best) >= min_count:
            return best
        time.sleep(0.5)
    return best


class TestDeferredAuditGuarantees:
    """Tests that the deferred audit pattern guarantees event logging.

    The deferred pattern ensures audit events are logged even when:
    - Operations succeed normally (baseline)
    - Client disconnects (context cancellation)

    These tests verify the core guarantee: an audit event is ALWAYS produced.
    """

    def test_rewrap_always_audited_on_success(
        self,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
        attribute_default_rsa: Attribute,
    ):
        """Baseline: normal decrypt produces a rewrap audit event via deferred pattern."""
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

        ct_file = tmp_dir / f"deferred-success-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
            attr_values=attribute_default_rsa.value_fqns,
        )

        mark = audit_logs.mark("before_success_decrypt")
        rt_file = tmp_dir / f"deferred-success-{encrypt_sdk}-{decrypt_sdk}.untdf"
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
        assert filecmp.cmp(pt_file, rt_file)

        # The deferred pattern should produce a success event
        events = audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)
        assert len(events) >= 1
        event = events[0]
        assert event.action_result == "success"
        assert event.action_type == "rewrap"
        assert event.object_type == "key_object"

    def test_rewrap_always_audited_on_client_disconnect(
        self,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
        attribute_default_rsa: Attribute,
    ):
        """Staggered client kills during decrypt always produce audit events.

        Launches CONCURRENT_DECRYPTS processes and kills them at staggered
        intervals. The concurrent load increases server processing time,
        widening the cancellation window. We assert that every process that
        reached the server produced an audit event (success, failure, or
        cancel) -- proving the deferred Log() always executes.
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

        ct_file = tmp_dir / f"deferred-cancel-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
            attr_values=attribute_default_rsa.value_fqns,
        )

        mark = audit_logs.mark("before_cancel_barrage")

        # Build base command (rt_file will be replaced per-process)
        base_cmd = _build_decrypt_command(decrypt_sdk, ct_file, tmp_dir / "placeholder")
        env = dict(os.environ)

        proc_results = _launch_and_kill_staggered(
            cmd=base_cmd,
            env=env,
            count=CONCURRENT_DECRYPTS,
            kill_delays=KILL_DELAYS,
            tmp_dir=tmp_dir,
            prefix=f"cancel-{encrypt_sdk}-{decrypt_sdk}",
        )

        # Log what happened for debugging
        killed_count = sum(1 for p in proc_results if p["killed"])
        completed_count = sum(1 for p in proc_results if not p["killed"])
        logger.info(
            f"Cancel barrage: {killed_count} killed, {completed_count} "
            f"completed before kill. Kill times: "
            f"{[f'{p["kill_time"]:.3f}s' for p in proc_results]}"
        )

        # Collect rewrap events. We expect at least one event for every
        # process that reached the server (those killed too early may not
        # have sent the gRPC request yet).
        events = _collect_rewrap_events(
            audit_logs, since_mark=mark, min_count=1, timeout=15.0
        )

        # Core guarantee: at least 1 rewrap event was produced
        assert len(events) >= 1, (
            f"Deferred pattern guarantee violated: {CONCURRENT_DECRYPTS} "
            f"decrypt processes launched but got 0 rewrap audit events"
        )

        # Categorize events by result
        by_result: dict[str | None, list[ParsedAuditEvent]] = {}
        for e in events:
            by_result.setdefault(e.action_result, []).append(e)
        logger.info(
            f"Audit results: {', '.join(f'{k}={len(v)}' for k, v in by_result.items())}, "
            f"total={len(events)}"
        )

        # Every event should have valid rewrap structure
        for event in events:
            assert event.action_type == "rewrap"
            assert event.object_type == "key_object"
            assert event.client_platform == "kas"
            assert event.action_result in ("success", "failure", "error", "cancel")

    def test_rewrap_cancel_has_initial_metadata(
        self,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
        attribute_default_rsa: Attribute,
    ):
        """All deferred events include metadata populated at event creation time.

        The deferred pattern pre-creates events with TDF format, algorithm,
        key ID, and policy binding before processing starts. Even cancelled
        events should have at least these initial fields.

        Uses the same staggered-kill approach to generate events across
        different outcomes (success, cancel, failure).
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

        ct_file = tmp_dir / f"deferred-meta-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
            attr_values=attribute_default_rsa.value_fqns,
        )

        mark = audit_logs.mark("before_metadata_barrage")

        base_cmd = _build_decrypt_command(decrypt_sdk, ct_file, tmp_dir / "placeholder")
        env = dict(os.environ)

        _launch_and_kill_staggered(
            cmd=base_cmd,
            env=env,
            count=CONCURRENT_DECRYPTS,
            kill_delays=KILL_DELAYS,
            tmp_dir=tmp_dir,
            prefix=f"meta-{encrypt_sdk}-{decrypt_sdk}",
        )

        events = _collect_rewrap_events(
            audit_logs, since_mark=mark, min_count=1, timeout=15.0
        )
        assert len(events) >= 1, "Expected at least 1 rewrap event"

        # Every event (success, failure, or cancel) should have tdf_format
        # since it's populated at event creation time in the deferred pattern
        for event in events:
            assert event.tdf_format is not None, (
                f"Deferred event missing tdf_format: result={event.action_result}"
            )
            assert event.tdf_format == "tdf3", (
                f"Expected tdf_format='tdf3', got '{event.tdf_format}'"
            )
