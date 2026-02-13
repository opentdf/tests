"""KAS audit log collection and assertion framework for pytest tests.

This module provides infrastructure to capture logs from KAS services during
test execution and assert on their contents. Logs are collected via background
threads tailing log files and buffered in memory for fast access.

Usage:
    def test_rewrap_logged(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, audit_logs):
        ct_file = encrypt_sdk.encrypt(pt_file, ...)
        mark = audit_logs.mark("before_decrypt")
        decrypt_sdk.decrypt(ct_file, ...)
        audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)

    def test_policy_crud(otdfctl, audit_logs):
        mark = audit_logs.mark("before_create")
        ns = otdfctl.namespace_create(name)
        audit_logs.assert_policy_create(
            object_type="namespace",
            object_id=ns.id,
            since_mark=mark,
        )
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("xtest")


def parse_rfc3339(timestamp_str: str) -> datetime | None:
    """Parse an RFC3339 timestamp string into a timezone-aware datetime.

    Handles common variations:
    - 2024-01-15T10:30:00Z
    - 2024-01-15T10:30:00.123Z
    - 2024-01-15T10:30:00+00:00
    - 2024-01-15T10:30:00.123456+00:00

    Args:
        timestamp_str: RFC3339 formatted timestamp string

    Returns:
        Timezone-aware datetime in UTC, or None if parsing fails
    """
    if not timestamp_str:
        return None

    # Normalize 'Z' suffix to '+00:00' for consistent parsing
    ts = timestamp_str.replace("Z", "+00:00")

    # Try parsing with fractional seconds
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",  # With microseconds
        "%Y-%m-%dT%H:%M:%S%z",  # Without microseconds
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue

    # Fallback: try fromisoformat (Python 3.11+)
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        return None


@dataclass
class ClockSkewEstimate:
    """Estimated clock skew between test machine and a service.

    The skew is calculated as: collection_time - event_time
    - Positive skew: test machine clock is ahead OR there's I/O delay
    - Negative skew: service clock is ahead of test machine

    The minimum observed delta approximates true clock skew (removing I/O delay).
    """

    service_name: str
    """Name of the service this estimate is for."""

    samples: list[float] = field(default_factory=list)
    """Individual skew samples in seconds (collection_time - event_time)."""

    @property
    def sample_count(self) -> int:
        """Number of samples collected."""
        return len(self.samples)

    @property
    def min_skew(self) -> float | None:
        """Minimum observed skew (best estimate of true clock skew).

        The minimum delta removes I/O delay, leaving only clock difference.
        Returns None if no samples.
        """
        return min(self.samples) if self.samples else None

    @property
    def max_skew(self) -> float | None:
        """Maximum observed skew (includes worst-case I/O delay)."""
        return max(self.samples) if self.samples else None

    @property
    def mean_skew(self) -> float | None:
        """Mean skew across all samples."""
        return statistics.mean(self.samples) if self.samples else None

    @property
    def median_skew(self) -> float | None:
        """Median skew (robust to outliers)."""
        return statistics.median(self.samples) if self.samples else None

    @property
    def stdev(self) -> float | None:
        """Standard deviation of skew samples."""
        return statistics.stdev(self.samples) if len(self.samples) >= 2 else None

    def safe_skew_adjustment(self, confidence_margin: float = 0.1) -> float:
        """Get a safe adjustment value for filtering.

        Returns a value that can be subtracted from marks to account for
        clock skew, with a confidence margin for safety.

        Args:
            confidence_margin: Extra seconds to add for safety (default 0.1s)

        Returns:
            Adjustment in seconds. Subtract this from mark timestamps.
            Returns confidence_margin if no samples available.
        """
        if not self.samples:
            return confidence_margin

        # Use minimum skew (best estimate of true clock difference)
        # If negative (service ahead), we need to look further back in time
        # Add margin for safety
        min_s = self.min_skew
        if min_s is None:
            return confidence_margin

        # If service clock is ahead (negative skew), return abs value + margin
        # If test clock is ahead (positive skew), small margin is enough
        if min_s < 0:
            return abs(min_s) + confidence_margin
        return confidence_margin

    def __repr__(self) -> str:
        if not self.samples:
            return f"ClockSkewEstimate({self.service_name!r}, no samples)"
        return (
            f"ClockSkewEstimate({self.service_name!r}, "
            f"n={self.sample_count}, "
            f"min={self.min_skew:.3f}s, "
            f"max={self.max_skew:.3f}s, "
            f"median={self.median_skew:.3f}s)"
        )


class ClockSkewEstimator:
    """Tracks and estimates clock skew between test machine and services.

    Collects samples by comparing LogEntry.timestamp (collection time on test
    machine) with ParsedAuditEvent.timestamp (event time from service clock).
    """

    def __init__(self) -> None:
        self._estimates: dict[str, ClockSkewEstimate] = {}
        self._lock = threading.Lock()

    def record_sample(
        self,
        service_name: str,
        collection_time: datetime,
        event_time: datetime,
    ) -> None:
        """Record a skew sample from a parsed audit event.

        Args:
            service_name: Name of the service that generated the event
            collection_time: When the log was read (test machine clock)
            event_time: When the event occurred (service clock, from JSON)
        """
        # Convert both to UTC for comparison
        if collection_time.tzinfo is None:
            # Assume local time, convert to UTC
            collection_utc = collection_time.astimezone(UTC)
        else:
            collection_utc = collection_time.astimezone(UTC)

        if event_time.tzinfo is None:
            # Assume UTC if no timezone (common for service logs)
            event_utc = event_time.replace(tzinfo=UTC)
        else:
            event_utc = event_time.astimezone(UTC)

        skew_seconds = (collection_utc - event_utc).total_seconds()

        with self._lock:
            if service_name not in self._estimates:
                self._estimates[service_name] = ClockSkewEstimate(service_name)
            self._estimates[service_name].samples.append(skew_seconds)

    def get_estimate(self, service_name: str) -> ClockSkewEstimate | None:
        """Get the skew estimate for a specific service."""
        with self._lock:
            return self._estimates.get(service_name)

    def get_global_estimate(self) -> ClockSkewEstimate:
        """Get a combined estimate across all services.

        Useful when you don't know which service will generate an event.
        """
        with self._lock:
            combined = ClockSkewEstimate("_global")
            for estimate in self._estimates.values():
                combined.samples.extend(estimate.samples)
            return combined

    def get_safe_adjustment(self, service_name: str | None = None) -> float:
        """Get a safe time adjustment for mark-based filtering.

        Args:
            service_name: Specific service, or None for global estimate

        Returns:
            Seconds to subtract from mark timestamps for safe filtering
        """
        if service_name:
            estimate = self.get_estimate(service_name)
            if estimate:
                return estimate.safe_skew_adjustment()

        return self.get_global_estimate().safe_skew_adjustment()

    def summary(self) -> dict[str, Any]:
        """Get a summary of all skew estimates."""
        with self._lock:
            result = {}
            for name, est in self._estimates.items():
                result[name] = {
                    "samples": est.sample_count,
                    "min_skew": est.min_skew,
                    "max_skew": est.max_skew,
                    "median_skew": est.median_skew,
                    "safe_adjustment": est.safe_skew_adjustment(),
                }
            return result

    def __repr__(self) -> str:
        with self._lock:
            services = list(self._estimates.keys())
            total = sum(e.sample_count for e in self._estimates.values())
            return f"ClockSkewEstimator(services={services}, total_samples={total})"


# Audit event constants from platform/service/logger/audit/constants.go
OBJECT_TYPES = frozenset(
    {
        "subject_mapping",
        "resource_mapping",
        "attribute_definition",
        "attribute_value",
        "obligation_definition",
        "obligation_value",
        "obligation_trigger",
        "namespace",
        "condition_set",
        "kas_registry",
        "kas_attribute_namespace_assignment",
        "kas_attribute_definition_assignment",
        "kas_attribute_value_assignment",
        "key_object",
        "entity_object",
        "resource_mapping_group",
        "public_key",
        "action",
        "registered_resource",
        "registered_resource_value",
        "key_management_provider_config",
        "kas_registry_keys",
        "kas_attribute_definition_key_assignment",
        "kas_attribute_value_key_assignment",
        "kas_attribute_namespace_key_assignment",
        "namespace_certificate",
    }
)

ACTION_TYPES = frozenset({"create", "read", "update", "delete", "rewrap", "rotate"})

ACTION_RESULTS = frozenset(
    {"success", "failure", "error", "encrypt", "block", "ignore", "override", "cancel"}
)

# Audit log message verbs
VERB_DECISION = "decision"
VERB_POLICY_CRUD = "policy crud"
VERB_REWRAP = "rewrap"


@dataclass
class ParsedAuditEvent:
    """Structured representation of a parsed audit log event.

    This class extracts and provides typed access to audit event fields
    from the JSON log structure.
    """

    timestamp: str
    """RFC3339 timestamp from the audit event."""

    level: str
    """Log level (typically 'AUDIT')."""

    msg: str
    """Audit verb: 'rewrap', 'policy crud', or 'decision'."""

    audit: dict[str, Any]
    """The full audit payload from the log entry."""

    raw_entry: LogEntry
    """The original LogEntry this was parsed from."""

    @property
    def event_time(self) -> datetime | None:
        """Parse and return the event timestamp as a timezone-aware datetime.

        Returns:
            Parsed datetime in UTC, or None if parsing fails
        """
        return parse_rfc3339(self.timestamp)

    @property
    def collection_time(self) -> datetime:
        """Get when this log entry was collected (test machine time)."""
        return self.raw_entry.timestamp

    @property
    def observed_skew(self) -> float | None:
        """Get the observed skew for this specific event (collection - event time).

        Returns:
            Skew in seconds, or None if event time cannot be parsed.
            Positive means test machine collected later than event occurred.
        """
        event_t = self.event_time
        if not event_t:
            return None

        # Convert collection time to UTC for comparison
        collection_t = self.collection_time
        if collection_t.tzinfo is None:
            collection_utc = collection_t.astimezone(UTC)
        else:
            collection_utc = collection_t.astimezone(UTC)

        if event_t.tzinfo is None:
            event_utc = event_t.replace(tzinfo=UTC)
        else:
            event_utc = event_t.astimezone(UTC)

        return (collection_utc - event_utc).total_seconds()

    @property
    def action_type(self) -> str | None:
        """Get the action type (create, read, update, delete, rewrap, rotate)."""
        action = self.audit.get("action", {})
        return action.get("type")

    @property
    def action_result(self) -> str | None:
        """Get the action result (success, failure, error, cancel, etc.)."""
        action = self.audit.get("action", {})
        return action.get("result")

    @property
    def object_type(self) -> str | None:
        """Get the object type (namespace, attribute_definition, key_object, etc.)."""
        obj = self.audit.get("object", {})
        return obj.get("type")

    @property
    def object_id(self) -> str | None:
        """Get the object ID (UUID or composite ID)."""
        obj = self.audit.get("object", {})
        return obj.get("id")

    @property
    def object_name(self) -> str | None:
        """Get the object name if present."""
        obj = self.audit.get("object", {})
        return obj.get("name")

    @property
    def object_attrs(self) -> list[str]:
        """Get the attribute FQNs from the object attributes."""
        obj = self.audit.get("object", {})
        attrs = obj.get("attributes", {})
        return attrs.get("attrs", [])

    @property
    def actor_id(self) -> str | None:
        """Get the actor ID."""
        actor = self.audit.get("actor", {})
        return actor.get("id")

    @property
    def request_id(self) -> str | None:
        """Get the request ID."""
        return self.audit.get("requestId")

    @property
    def event_metadata(self) -> dict[str, Any]:
        """Get the event metadata dictionary."""
        return self.audit.get("eventMetaData", {})

    @property
    def client_platform(self) -> str | None:
        """Get the client platform (kas, policy, authorization, authorization.v2)."""
        client = self.audit.get("clientInfo", {})
        return client.get("platform")

    @property
    def key_id(self) -> str | None:
        """Get the key ID from rewrap event metadata."""
        return self.event_metadata.get("keyID")

    @property
    def algorithm(self) -> str | None:
        """Get the algorithm from rewrap event metadata."""
        return self.event_metadata.get("algorithm")

    @property
    def tdf_format(self) -> str | None:
        """Get the TDF format from rewrap event metadata."""
        return self.event_metadata.get("tdfFormat")

    @property
    def policy_binding(self) -> str | None:
        """Get the policy binding from rewrap event metadata."""
        return self.event_metadata.get("policyBinding")

    @property
    def cancellation_error(self) -> str | None:
        """Get the cancellation error if event was cancelled."""
        return self.event_metadata.get("cancellation_error")

    @property
    def original(self) -> dict[str, Any] | None:
        """Get the original state for policy CRUD events."""
        return self.audit.get("original")

    @property
    def updated(self) -> dict[str, Any] | None:
        """Get the updated state for policy CRUD events."""
        return self.audit.get("updated")

    def matches_rewrap(
        self,
        result: str | None = None,
        policy_uuid: str | None = None,
        key_id: str | None = None,
        algorithm: str | None = None,
        attr_fqns: list[str] | None = None,
    ) -> bool:
        """Check if this event matches rewrap criteria.

        Args:
            result: Expected action result (success, failure, error, cancel)
            policy_uuid: Expected policy UUID (object ID)
            key_id: Expected key ID from metadata
            algorithm: Expected algorithm from metadata
            attr_fqns: Expected attribute FQNs (all must be present)

        Returns:
            True if event matches all specified criteria
        """
        if self.msg != VERB_REWRAP:
            return False
        if result is not None and self.action_result != result:
            return False
        if policy_uuid is not None and self.object_id != policy_uuid:
            return False
        if key_id is not None and self.key_id != key_id:
            return False
        if algorithm is not None and self.algorithm != algorithm:
            return False
        if attr_fqns is not None:
            event_attrs = set(self.object_attrs)
            if not all(fqn in event_attrs for fqn in attr_fqns):
                return False
        return True

    def matches_policy_crud(
        self,
        result: str | None = None,
        action_type: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
    ) -> bool:
        """Check if this event matches policy CRUD criteria.

        Args:
            result: Expected action result (success, failure, error, cancel)
            action_type: Expected action type (create, read, update, delete)
            object_type: Expected object type (namespace, attribute_definition, etc.)
            object_id: Expected object ID

        Returns:
            True if event matches all specified criteria
        """
        if self.msg != VERB_POLICY_CRUD:
            return False
        if result is not None and self.action_result != result:
            return False
        if action_type is not None and self.action_type != action_type:
            return False
        if object_type is not None and self.object_type != object_type:
            return False
        if object_id is not None and self.object_id != object_id:
            return False
        return True

    def matches_decision(
        self,
        result: str | None = None,
        entity_id: str | None = None,
        action_name: str | None = None,
    ) -> bool:
        """Check if this event matches decision criteria.

        Args:
            result: Expected action result (success, failure)
            entity_id: Expected entity/actor ID
            action_name: Expected action name (from object name or ID)

        Returns:
            True if event matches all specified criteria
        """
        if self.msg != VERB_DECISION:
            return False
        if result is not None and self.action_result != result:
            return False
        if entity_id is not None and self.actor_id != entity_id:
            return False
        if action_name is not None:
            # Action name appears in object ID as "entityId-actionName"
            # or in object name as "decisionRequest-actionName"
            obj_id = self.object_id or ""
            obj_name = self.object_name or ""
            if action_name not in obj_id and action_name not in obj_name:
                return False
        return True


class LogEntry:
    """Represents a single log entry from a KAS service log file."""

    def __init__(
        self,
        timestamp: datetime,
        raw_line: str,
        service_name: str,
    ):
        """Initialize a log entry.

        Args:
            timestamp: When the log was collected by this framework
            raw_line: The original log line as received
            service_name: Service name (e.g., 'kas', 'kas-alpha')
        """
        self.timestamp = timestamp
        self.raw_line = raw_line
        self.service_name = service_name

    def __repr__(self) -> str:
        return (
            f"LogEntry(timestamp={self.timestamp!r}, "
            f"raw_line={self.raw_line[:50]!r}..., "
            f"service_name={self.service_name!r})"
        )


class AuditLogCollector:
    """Collects logs from KAS service log files in the background.

    Starts background threads that tail log files and read logs into a
    thread-safe buffer. Provides methods to query logs and mark timestamps
    for correlation with test actions.
    """

    MAX_BUFFER_SIZE = 10000
    """Maximum number of log entries to keep in memory."""

    def __init__(
        self,
        platform_dir: Path,
        services: list[str] | None = None,
        log_files: dict[str, Path] | None = None,
    ):
        """Initialize collector for log collection.

        Args:
            platform_dir: Path to platform directory
            services: List of service names to monitor (e.g., ['kas', 'kas-alpha']).
                     If None or empty, monitors all services.
            log_files: Dict mapping service names to log file paths.
                      Example: {'kas': Path('logs/kas-main.log')}
        """
        self.platform_dir = platform_dir
        self.services = services or []
        self.log_files = log_files
        self._buffer: deque[LogEntry] = deque(maxlen=self.MAX_BUFFER_SIZE)
        self._marks: dict[str, datetime] = {}
        self._mark_counter = 0
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._new_data = threading.Condition()
        self._disabled = False
        self._error: Exception | None = None
        self.log_file_path: Path | None = None
        self.log_file_written = False
        self.start_time: datetime | None = None
        self.skew_estimator = ClockSkewEstimator()

    def start(self) -> None:
        """Start background log collection.

        Tails log files directly. Gracefully handles errors by disabling
        collection if resources are unavailable.
        """
        if self._disabled:
            return

        self.start_time = datetime.now()

        if not self.platform_dir.exists():
            logger.warning(
                f"Platform directory not found: {self.platform_dir}. "
                f"Audit log collection disabled."
            )
            self._disabled = True
            return

        if not self.log_files:
            logger.warning("No log files provided. Disabling collection.")
            self._disabled = True
            return

        existing_files = {
            service: path for service, path in self.log_files.items() if path.exists()
        }

        if not existing_files:
            logger.warning(
                f"None of the log files exist yet: {list(self.log_files.values())}. "
                f"Will wait for them to be created..."
            )
            existing_files = self.log_files

        logger.debug(
            f"Starting file-based log collection for: {list(existing_files.keys())}"
        )

        for service, log_path in existing_files.items():
            thread = threading.Thread(
                target=self._tail_file,
                args=(service, log_path),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

        logger.info(
            f"Audit log collection started for: {', '.join(existing_files.keys())}"
        )

    def stop(self) -> None:
        """Stop log collection and cleanup resources."""
        if self._disabled:
            return

        logger.debug("Stopping audit log collection")
        self._stop_event.set()
        # Wake any threads waiting on new data so they can exit promptly
        with self._new_data:
            self._new_data.notify_all()

        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2)

        logger.debug(
            f"Audit log collection stopped. Collected {len(self._buffer)} log entries."
        )

    def get_logs(
        self,
        since: datetime | None = None,
        service: str | None = None,
    ) -> list[LogEntry]:
        """Get collected logs, optionally filtered by time and service.

        Args:
            since: Only return logs after this timestamp
            service: Only return logs from this service

        Returns:
            List of matching log entries (may be empty)
        """
        if self._disabled:
            return []

        logs = list(self._buffer)

        if since:
            logs = [log for log in logs if log.timestamp >= since]

        if service:
            logs = [log for log in logs if log.service_name == service]

        return logs

    def mark(self, label: str) -> str:
        """Mark a timestamp for later correlation with log entries.

        Automatically generates a unique mark name by appending a counter suffix.

        Args:
            label: Base name for this timestamp (e.g., 'before_decrypt')

        Returns:
            The unique mark name that was created
        """
        self._mark_counter += 1
        unique_label = f"{label}_{self._mark_counter}"
        now = datetime.now()
        self._marks[unique_label] = now
        logger.debug(f"Marked timestamp '{unique_label}' at {now}")
        return unique_label

    def get_mark(self, label: str) -> datetime | None:
        """Retrieve a previously marked timestamp.

        Args:
            label: Name of the timestamp mark

        Returns:
            The marked timestamp, or None if not found
        """
        return self._marks.get(label)

    def write_to_disk(self, path: Path) -> None:
        """Write collected logs to file for debugging.

        Args:
            path: File path to write logs to
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(
                """
Audit Log Collection Summary
============================
"""
            )
            f.write(f"Total entries: {len(self._buffer)}\n")
            f.write(
                f"Services monitored: {', '.join(self.services) if self.services else 'all'}\n"
            )
            if self._marks:
                f.write(
                    """
Timestamp marks:
"""
                )
                for label, ts in self._marks.items():
                    f.write(f"  {label}: {ts}\n")
            f.write(
                """
Log Entries:
============
"""
            )
            for entry in self._buffer:
                f.write(f"[{entry.timestamp}] {entry.service_name}: {entry.raw_line}\n")

        self.log_file_path = path
        self.log_file_written = True
        logger.info(f"Wrote {len(self._buffer)} audit log entries to {path}")

    def wait_for_new_data(self, timeout: float = 0.1) -> bool:
        """Wait for new log data to arrive.

        Blocks until new data is appended by a tail thread, or until timeout.
        More efficient than polling with time.sleep() since it wakes up
        immediately when data arrives.

        Args:
            timeout: Maximum time to wait in seconds (default: 0.1)

        Returns:
            True if woken by new data, False if timed out
        """
        with self._new_data:
            return self._new_data.wait(timeout=timeout)

    def _tail_file(self, service: str, log_path: Path) -> None:
        """Background thread target that tails a log file.

        Args:
            service: Service name (e.g., 'kas', 'kas-alpha')
            log_path: Path to log file to tail
        """
        logger.debug(f"Starting to tail {log_path} for service {service}")

        wait_start = datetime.now()
        while not log_path.exists():
            if self._stop_event.is_set():
                return
            if (datetime.now() - wait_start).total_seconds() > 30:
                logger.warning(f"Timeout waiting for log file: {log_path}")
                return
            self._stop_event.wait(0.5)

        try:
            with open(log_path) as f:
                f.seek(0, 2)

                while not self._stop_event.is_set():
                    # Batch-read all available lines before notifying
                    got_data = False
                    while True:
                        line = f.readline()
                        if not line:
                            break
                        entry = LogEntry(
                            timestamp=datetime.now(),
                            raw_line=line.rstrip(),
                            service_name=service,
                        )
                        self._buffer.append(entry)
                        got_data = True

                    if got_data:
                        with self._new_data:
                            self._new_data.notify_all()
                    else:
                        self._stop_event.wait(0.1)
        except Exception as e:
            logger.error(f"Error tailing log file {log_path}: {e}")
            self._error = e


class AuditLogAsserter:
    """Provides assertion methods for validating audit log contents.

    This class wraps an AuditLogCollector and provides test-friendly assertion
    methods with rich error messages.
    """

    def __init__(self, collector: AuditLogCollector | None):
        """Initialize asserter with log collector.

        Args:
            collector: AuditLogCollector instance, or None for no-op mode
        """
        self._collector = collector

    @property
    def is_enabled(self) -> bool:
        """Check if audit log collection is enabled.

        Returns:
            True if collection is active, False if disabled or no collector
        """
        return self._collector is not None and not self._collector._disabled

    def mark(self, label: str) -> str:
        """Mark a timestamp for later correlation.

        Automatically generates a unique mark name by appending a counter suffix.

        Args:
            label: Base name for this timestamp

        Returns:
            The unique mark name that was created
        """
        if not self._collector or self._collector._disabled:
            # Generate a fake unique mark for disabled collectors
            return f"{label}_noop"
        return self._collector.mark(label)

    @property
    def skew_estimator(self) -> ClockSkewEstimator | None:
        """Get the clock skew estimator, or None if collection is disabled."""
        if not self._collector or self._collector._disabled:
            return None
        return self._collector.skew_estimator

    def get_skew_summary(self) -> dict[str, Any]:
        """Get a summary of clock skew estimates across all services.

        Returns:
            Dict with per-service skew statistics, or empty dict if disabled
        """
        if not self._collector or self._collector._disabled:
            return {}
        return self._collector.skew_estimator.summary()

    def get_skew_adjustment(self, service_name: str | None = None) -> float:
        """Get the recommended time adjustment for a service.

        This is the amount of time (in seconds) that should be subtracted
        from mark timestamps to account for clock skew.

        Args:
            service_name: Specific service, or None for global estimate

        Returns:
            Adjustment in seconds (always >= 0.1 for safety margin)
        """
        if not self._collector or self._collector._disabled:
            return 0.1  # Default safety margin
        return self._collector.skew_estimator.get_safe_adjustment(service_name)

    def assert_contains(
        self,
        pattern: str | re.Pattern,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[LogEntry]:
        """Assert pattern appears in logs with optional constraints.

        Args:
            pattern: Regex pattern or substring to search for
            min_count: Minimum number of occurrences (default: 1)
            since_mark: Only check logs since marked timestamp
            timeout: Maximum time to wait for pattern in seconds (default: 20.0)

        Returns:
            Matching log entries

        Raises:
            AssertionError: If constraints not met, with detailed context
        """
        if not self._collector or self._collector._disabled:
            logger.warning(
                f"Audit log assertion skipped (collection disabled). "
                f"Would have asserted pattern: {pattern}"
            )
            return []

        since = self._resolve_since(since_mark)

        if isinstance(pattern, str):
            regex = re.compile(pattern, re.IGNORECASE)
        else:
            regex = pattern

        # Wait up to timeout for pattern to appear
        start_time = time.time()
        matching: list[LogEntry] = []
        logs: list[LogEntry] = []

        while True:
            logs = self._collector.get_logs(since=since)
            matching = [log for log in logs if regex.search(log.raw_line)]

            count = len(matching)
            if count >= min_count:
                logger.debug(
                    f"Found {count} matches for pattern '{pattern}' "
                    f"after {time.time() - start_time:.3f}s"
                )
                return matching

            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            # Wait for new data or timeout
            self._collector.wait_for_new_data(timeout=min(remaining, 1.0))

        # Timeout expired, raise error if we don't have enough matches
        timeout_time = datetime.now()
        count = len(matching)
        if count < min_count:
            self._raise_assertion_error(
                f"Expected pattern '{pattern}' to appear at least {min_count} time(s), "
                f"but found {count} occurrence(s) after waiting {timeout}s.",
                matching,
                logs,
                timeout_time=timeout_time,
                since=since,
            )

        return matching

    def _resolve_since(
        self, since_mark: str | None, apply_skew_adjustment: bool = True
    ) -> datetime | None:
        """Resolve time filter from mark name, optionally adjusting for clock skew.

        When apply_skew_adjustment is True (default), the returned timestamp
        is adjusted backwards by the estimated clock skew to avoid missing
        events due to clock differences between test machine and services.

        Args:
            since_mark: Name of timestamp mark to filter from
            apply_skew_adjustment: Whether to apply clock skew adjustment

        Returns:
            Resolved datetime to filter from, or None for no filter

        Raises:
            ValueError: If since_mark is provided but not found
        """
        if since_mark:
            if not self._collector:
                return None
            since = self._collector.get_mark(since_mark)
            if not since:
                raise ValueError(f"Unknown timestamp mark: {since_mark}")

            # Apply clock skew adjustment to avoid missing events
            if apply_skew_adjustment:
                adjustment = self._collector.skew_estimator.get_safe_adjustment()
                since = since - timedelta(seconds=adjustment)
                logger.debug(
                    f"Adjusted since time by -{adjustment:.3f}s for clock skew"
                )

            return since
        return None

    def assert_decision(
        self,
        result: str,
        attr_fqn: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
    ) -> list[LogEntry]:
        """Assert on authorization decision audit log entries.

        Looks for audit log entries with:
        - level=AUDIT
        - msg=decision
        - audit.action.result=<result>
        - Optionally, the presence of an attribute FQN

        Args:
            result: Expected decision result ('failure' or 'success')
            attr_fqn: Optional attribute FQN that should appear in the log
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp

        Returns:
            Matching log entries

        Raises:
            AssertionError: If constraints not met
        """
        # Build pattern to match decision audit logs
        # Pattern: level=AUDIT ... msg=decision ... audit.action.result=<result>
        pattern_parts = [
            r"level=AUDIT",
            r"msg=decision",
            rf"audit\.action\.result={result}",
        ]

        # Combine into a pattern that matches all parts (in any order on the line)
        # Use lookahead assertions to match all parts regardless of order
        pattern = "".join(f"(?=.*{part})" for part in pattern_parts)

        matches = self.assert_contains(
            pattern, min_count=min_count, since_mark=since_mark
        )

        # If attr_fqn is specified, verify it appears in the matching logs
        if attr_fqn and matches:
            attr_matches = [m for m in matches if attr_fqn in m.raw_line]
            if len(attr_matches) < min_count:
                since = self._resolve_since(since_mark)
                self._raise_assertion_error(
                    f"Expected attribute FQN '{attr_fqn}' in decision audit logs, "
                    f"but found only {len(attr_matches)} matching entries (need {min_count}).",
                    attr_matches,
                    matches,
                    timeout_time=datetime.now(),
                    since=since,
                )
            return attr_matches

        return matches

    def assert_decision_failure(
        self,
        attr_fqn: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
    ) -> list[LogEntry]:
        """Assert a failed authorization decision was logged.

        Convenience method for assert_decision(result='failure', ...).

        Args:
            attr_fqn: Optional attribute FQN that should appear in the log
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp

        Returns:
            Matching log entries
        """
        return self.assert_decision(
            result="failure",
            attr_fqn=attr_fqn,
            min_count=min_count,
            since_mark=since_mark,
        )

    def assert_decision_success(
        self,
        attr_fqn: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
    ) -> list[LogEntry]:
        """Assert a successful authorization decision was logged.

        Convenience method for assert_decision(result='success', ...).

        Args:
            attr_fqn: Optional attribute FQN that should appear in the log
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp

        Returns:
            Matching log entries
        """
        return self.assert_decision(
            result="success",
            attr_fqn=attr_fqn,
            min_count=min_count,
            since_mark=since_mark,
        )

    # ========================================================================
    # Structured audit event assertion methods
    # ========================================================================

    def parse_audit_log(
        self, entry: LogEntry, record_skew: bool = True
    ) -> ParsedAuditEvent | None:
        """Parse a log entry into a structured audit event.

        Attempts to parse JSON log entries that contain audit events.
        Returns None if the entry is not a valid audit log.

        Also records clock skew samples when parsing succeeds, comparing
        the log entry's collection timestamp with the event's internal timestamp.

        Args:
            entry: The log entry to parse
            record_skew: Whether to record a skew sample (default True)

        Returns:
            ParsedAuditEvent if successfully parsed, None otherwise
        """
        try:
            data = json.loads(entry.raw_line)
        except json.JSONDecodeError:
            return None

        # Check for required audit log fields
        if "level" not in data or "msg" not in data or "audit" not in data:
            return None

        # Verify it's an AUDIT level log
        if data.get("level") != "AUDIT":
            return None

        # Verify msg is one of the known audit verbs
        msg = data.get("msg", "")
        if msg not in (VERB_DECISION, VERB_POLICY_CRUD, VERB_REWRAP):
            return None

        event = ParsedAuditEvent(
            timestamp=data.get("time", ""),
            level=data.get("level", ""),
            msg=msg,
            audit=data.get("audit", {}),
            raw_entry=entry,
        )

        # Record skew sample for clock synchronization estimation
        if record_skew and self._collector and event.timestamp:
            event_time = parse_rfc3339(event.timestamp)
            if event_time:
                self._collector.skew_estimator.record_sample(
                    service_name=entry.service_name,
                    collection_time=entry.timestamp,
                    event_time=event_time,
                )

        return event

    def get_parsed_audit_logs(
        self,
        since_mark: str | None = None,
        timeout: float = 5.0,
    ) -> list[ParsedAuditEvent]:
        """Get all parsed audit events from collected logs.

        Args:
            since_mark: Only return logs since this mark
            timeout: Maximum time to wait for logs

        Returns:
            List of parsed audit events
        """
        if not self._collector or self._collector._disabled:
            return []

        since = self._resolve_since(since_mark)

        # Wait a bit for logs to arrive
        start_time = time.time()
        while True:
            logs = self._collector.get_logs(since=since)
            parsed = []
            for entry in logs:
                event = self.parse_audit_log(entry)
                if event:
                    parsed.append(event)
            if parsed:
                return parsed

            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            self._collector.wait_for_new_data(timeout=min(remaining, 1.0))

        return []

    def assert_rewrap(
        self,
        result: Literal["success", "failure", "error", "cancel"],
        policy_uuid: str | None = None,
        key_id: str | None = None,
        algorithm: str | None = None,
        attr_fqns: list[str] | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert on rewrap audit log entries with structured field validation.

        Looks for audit log entries with:
        - msg='rewrap'
        - action.result=<result>
        - Optionally matching policy_uuid, key_id, algorithm, attr_fqns

        Args:
            result: Expected action result ('success', 'failure', 'error', 'cancel')
            policy_uuid: Expected policy UUID (object.id)
            key_id: Expected key ID from eventMetaData.keyID
            algorithm: Expected algorithm from eventMetaData.algorithm
            attr_fqns: Expected attribute FQNs (all must be present)
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp
            timeout: Maximum time to wait in seconds (default: 20.0)

        Returns:
            List of matching ParsedAuditEvent objects

        Raises:
            AssertionError: If constraints not met
        """
        if not self._collector or self._collector._disabled:
            logger.warning(
                f"Audit log assertion skipped (collection disabled). "
                f"Would have asserted rewrap result={result}"
            )
            return []

        since = self._resolve_since(since_mark)

        start_time = time.time()
        matching: list[ParsedAuditEvent] = []
        all_logs: list[LogEntry] = []

        while True:
            all_logs = self._collector.get_logs(since=since)
            matching = []

            for entry in all_logs:
                event = self.parse_audit_log(entry)
                if event and event.matches_rewrap(
                    result=result,
                    policy_uuid=policy_uuid,
                    key_id=key_id,
                    algorithm=algorithm,
                    attr_fqns=attr_fqns,
                ):
                    matching.append(event)

            if len(matching) >= min_count:
                logger.debug(
                    f"Found {len(matching)} rewrap events with result={result} "
                    f"after {time.time() - start_time:.3f}s"
                )
                return matching

            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            self._collector.wait_for_new_data(timeout=min(remaining, 1.0))

        # Build detailed error message
        timeout_time = datetime.now()
        criteria = [f"result={result}"]
        if policy_uuid:
            criteria.append(f"policy_uuid={policy_uuid}")
        if key_id:
            criteria.append(f"key_id={key_id}")
        if algorithm:
            criteria.append(f"algorithm={algorithm}")
        if attr_fqns:
            criteria.append(f"attr_fqns={attr_fqns}")

        self._raise_assertion_error(
            f"Expected at least {min_count} rewrap audit event(s) matching "
            f"{', '.join(criteria)}, but found {len(matching)} after {timeout}s.",
            [m.raw_entry for m in matching],
            all_logs,
            timeout_time=timeout_time,
            since=since,
        )
        return []  # Never reached, but satisfies type checker

    def assert_rewrap_success(
        self,
        policy_uuid: str | None = None,
        key_id: str | None = None,
        algorithm: str | None = None,
        attr_fqns: list[str] | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a successful rewrap was logged.

        Convenience method for assert_rewrap(result='success', ...).
        """
        return self.assert_rewrap(
            result="success",
            policy_uuid=policy_uuid,
            key_id=key_id,
            algorithm=algorithm,
            attr_fqns=attr_fqns,
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_rewrap_failure(
        self,
        policy_uuid: str | None = None,
        key_id: str | None = None,
        algorithm: str | None = None,
        attr_fqns: list[str] | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a failed rewrap was logged.

        Convenience method for assert_rewrap(result='failure', ...).
        Note: Use 'error' result for errors during rewrap processing.
        """
        return self.assert_rewrap(
            result="failure",
            policy_uuid=policy_uuid,
            key_id=key_id,
            algorithm=algorithm,
            attr_fqns=attr_fqns,
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_rewrap_error(
        self,
        policy_uuid: str | None = None,
        key_id: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a rewrap error was logged.

        Convenience method for assert_rewrap(result='error', ...).
        """
        return self.assert_rewrap(
            result="error",
            policy_uuid=policy_uuid,
            key_id=key_id,
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_rewrap_cancelled(
        self,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a cancelled rewrap was logged.

        Convenience method for assert_rewrap(result='cancel', ...).
        Cancelled events occur when the request context is cancelled.
        """
        return self.assert_rewrap(
            result="cancel",
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_policy_crud(
        self,
        result: Literal["success", "failure", "error", "cancel"],
        action_type: Literal["create", "read", "update", "delete"] | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert on policy CRUD audit log entries with structured field validation.

        Looks for audit log entries with:
        - msg='policy crud'
        - action.result=<result>
        - Optionally matching action_type, object_type, object_id

        Args:
            result: Expected action result ('success', 'failure', 'error', 'cancel')
            action_type: Expected action type ('create', 'read', 'update', 'delete')
            object_type: Expected object type (e.g., 'namespace', 'attribute_definition')
            object_id: Expected object ID (UUID)
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp
            timeout: Maximum time to wait in seconds (default: 20.0)

        Returns:
            List of matching ParsedAuditEvent objects

        Raises:
            AssertionError: If constraints not met
        """
        if not self._collector or self._collector._disabled:
            logger.warning(
                f"Audit log assertion skipped (collection disabled). "
                f"Would have asserted policy crud result={result}"
            )
            return []

        since = self._resolve_since(since_mark)

        start_time = time.time()
        matching: list[ParsedAuditEvent] = []
        all_logs: list[LogEntry] = []

        while True:
            all_logs = self._collector.get_logs(since=since)
            matching = []

            for entry in all_logs:
                event = self.parse_audit_log(entry)
                if event and event.matches_policy_crud(
                    result=result,
                    action_type=action_type,
                    object_type=object_type,
                    object_id=object_id,
                ):
                    matching.append(event)

            if len(matching) >= min_count:
                logger.debug(
                    f"Found {len(matching)} policy crud events with result={result} "
                    f"after {time.time() - start_time:.3f}s"
                )
                return matching

            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            self._collector.wait_for_new_data(timeout=min(remaining, 1.0))

        # Build detailed error message
        timeout_time = datetime.now()
        criteria = [f"result={result}"]
        if action_type:
            criteria.append(f"action_type={action_type}")
        if object_type:
            criteria.append(f"object_type={object_type}")
        if object_id:
            criteria.append(f"object_id={object_id}")

        self._raise_assertion_error(
            f"Expected at least {min_count} policy crud audit event(s) matching "
            f"{', '.join(criteria)}, but found {len(matching)} after {timeout}s.",
            [m.raw_entry for m in matching],
            all_logs,
            timeout_time=timeout_time,
            since=since,
        )
        return []  # Never reached, but satisfies type checker

    def assert_policy_create(
        self,
        object_type: str,
        object_id: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a successful policy create operation was logged.

        Convenience method for assert_policy_crud with action_type='create'.

        Args:
            object_type: Expected object type (e.g., 'namespace', 'attribute_definition')
            object_id: Expected object ID (UUID)
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp
            timeout: Maximum time to wait in seconds (default: 20.0)
        """
        return self.assert_policy_crud(
            result="success",
            action_type="create",
            object_type=object_type,
            object_id=object_id,
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_policy_update(
        self,
        object_type: str,
        object_id: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a successful policy update operation was logged.

        Convenience method for assert_policy_crud with action_type='update'.
        """
        return self.assert_policy_crud(
            result="success",
            action_type="update",
            object_type=object_type,
            object_id=object_id,
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_policy_delete(
        self,
        object_type: str,
        object_id: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert a successful policy delete operation was logged.

        Convenience method for assert_policy_crud with action_type='delete'.
        """
        return self.assert_policy_crud(
            result="success",
            action_type="delete",
            object_type=object_type,
            object_id=object_id,
            min_count=min_count,
            since_mark=since_mark,
            timeout=timeout,
        )

    def assert_decision_v2(
        self,
        result: Literal["success", "failure"],
        entity_id: str | None = None,
        action_name: str | None = None,
        min_count: int = 1,
        since_mark: str | None = None,
        timeout: float = 20.0,
    ) -> list[ParsedAuditEvent]:
        """Assert on GetDecision v2 audit log entries.

        Looks for audit log entries with:
        - msg='decision'
        - clientInfo.platform='authorization.v2'
        - action.result=<result>
        - Optionally matching entity_id, action_name

        Args:
            result: Expected action result ('success' for permit, 'failure' for deny)
            entity_id: Expected entity/actor ID
            action_name: Expected action name
            min_count: Minimum number of matching entries (default: 1)
            since_mark: Only check logs since marked timestamp
            timeout: Maximum time to wait in seconds (default: 20.0)

        Returns:
            List of matching ParsedAuditEvent objects

        Raises:
            AssertionError: If constraints not met
        """
        if not self._collector or self._collector._disabled:
            logger.warning(
                f"Audit log assertion skipped (collection disabled). "
                f"Would have asserted decision v2 result={result}"
            )
            return []

        since = self._resolve_since(since_mark)

        start_time = time.time()
        matching: list[ParsedAuditEvent] = []
        all_logs: list[LogEntry] = []

        while True:
            all_logs = self._collector.get_logs(since=since)
            matching = []

            for entry in all_logs:
                event = self.parse_audit_log(entry)
                if event and event.matches_decision(
                    result=result,
                    entity_id=entity_id,
                    action_name=action_name,
                ):
                    # Additional check for v2 platform
                    if event.client_platform == "authorization.v2":
                        matching.append(event)

            if len(matching) >= min_count:
                logger.debug(
                    f"Found {len(matching)} decision v2 events with result={result} "
                    f"after {time.time() - start_time:.3f}s"
                )
                return matching

            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            self._collector.wait_for_new_data(timeout=min(remaining, 1.0))

        # Build detailed error message
        timeout_time = datetime.now()
        criteria = [f"result={result}", "platform=authorization.v2"]
        if entity_id:
            criteria.append(f"entity_id={entity_id}")
        if action_name:
            criteria.append(f"action_name={action_name}")

        self._raise_assertion_error(
            f"Expected at least {min_count} decision v2 audit event(s) matching "
            f"{', '.join(criteria)}, but found {len(matching)} after {timeout}s.",
            [m.raw_entry for m in matching],
            all_logs,
            timeout_time=timeout_time,
            since=since,
        )
        return []  # Never reached, but satisfies type checker

    def _raise_assertion_error(
        self,
        message: str,
        matching: list[LogEntry],
        all_logs: list[LogEntry],
        timeout_time: datetime | None = None,
        since: datetime | None = None,
    ) -> None:
        """Raise AssertionError with rich context.

        Shows logs before and after the timeout to help diagnose race conditions
        where the expected log appears just after the timeout expires.

        Args:
            message: Main error message
            matching: Logs that matched the pattern
            all_logs: All logs that were searched (at timeout)
            timeout_time: When the timeout expired (for splitting before/after)
            since: The since_mark timestamp filter that was used
        """
        context = [message, ""]

        if matching:
            context.append("Matching logs:")
            for log in matching[:10]:
                context.append(
                    f"  [{log.timestamp}] {log.service_name}: {log.raw_line}"
                )
            if len(matching) > 10:
                context.append(f"  ... and {len(matching) - 10} more")
            context.append("")

        # Capture any logs that arrived after the timeout
        late_logs: list[LogEntry] = []
        if self._collector and timeout_time:
            # Brief wait to catch late-arriving logs
            time.sleep(0.5)
            current_logs = self._collector.get_logs(since=since)
            # Find logs that arrived after the timeout
            late_logs = [log for log in current_logs if log.timestamp > timeout_time]

        # Show logs before the timeout (last 10)
        recent_logs = all_logs[-10:] if len(all_logs) > 10 else all_logs
        if recent_logs:
            context.append(
                f"Logs before timeout (last {len(recent_logs)} of {len(all_logs)}):"
            )
            for log in recent_logs:
                context.append(
                    f"  [{log.timestamp}] {log.service_name}: {log.raw_line}"
                )

        # Show timeout marker
        if timeout_time:
            context.append("")
            context.append(f"  ─── TIMEOUT at {timeout_time.isoformat()} ───")

        # Show logs that arrived after the timeout
        if late_logs:
            context.append("")
            late_to_show = late_logs[:10]
            context.append(
                f"Logs AFTER timeout ({len(late_to_show)} of {len(late_logs)} late arrivals):"
            )
            for log in late_to_show:
                context.append(
                    f"  [{log.timestamp}] {log.service_name}: {log.raw_line}"
                )
            if len(late_logs) > 10:
                context.append(f"  ... and {len(late_logs) - 10} more late arrivals")
            context.append("")
            context.append(
                "  ⚠ Late arrivals suggest a race condition - consider increasing timeout"
            )
        elif timeout_time:
            context.append("")
            context.append("  (no logs arrived after timeout)")

        context.append("")

        if self._collector:
            context.append("Log collection details:")
            context.append(f"  - Total logs collected at timeout: {len(all_logs)}")
            if late_logs:
                context.append(f"  - Late arrivals after timeout: {len(late_logs)}")

            if self._collector.start_time:
                test_duration = datetime.now() - self._collector.start_time
                context.append(
                    f"  - Test started: {self._collector.start_time.isoformat()}"
                )
                context.append(
                    f"  - Test duration: {test_duration.total_seconds():.2f}s"
                )

            if self._collector.services:
                context.append(
                    f"  - Services monitored: {', '.join(self._collector.services)}"
                )

            if self._collector.log_files:
                context.append("  - Log file locations:")
                for service, log_path in sorted(self._collector.log_files.items()):
                    context.append(f"      {service}: {log_path}")

            if self._collector._marks:
                context.append(
                    f"  - Timestamp marks: {', '.join(self._collector._marks.keys())}"
                )

            # Add clock skew information
            skew_summary = self._collector.skew_estimator.summary()
            if skew_summary:
                context.append("  - Clock skew estimates:")
                for svc, stats in skew_summary.items():
                    if stats["samples"] > 0:
                        context.append(
                            f"      {svc}: min={stats['min_skew']:.3f}s, "
                            f"max={stats['max_skew']:.3f}s, "
                            f"median={stats['median_skew']:.3f}s "
                            f"(n={stats['samples']}, adj={stats['safe_adjustment']:.3f}s)"
                        )
                global_est = self._collector.skew_estimator.get_global_estimate()
                if global_est.sample_count > 0:
                    context.append(
                        f"      (global adjustment: {global_est.safe_skew_adjustment():.3f}s)"
                    )
            else:
                context.append(
                    "  - Clock skew: no samples collected (no audit events parsed yet)"
                )

        raise AssertionError("\n".join(context))
