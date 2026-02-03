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
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("xtest")


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
        self._disabled = False
        self._error: Exception | None = None
        self.log_file_path: Path | None = None
        self.log_file_written = False
        self.start_time: datetime | None = None

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
                    line = f.readline()
                    if line:
                        entry = LogEntry(
                            timestamp=datetime.now(),
                            raw_line=line.rstrip(),
                            service_name=service,
                        )
                        self._buffer.append(entry)
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

        while time.time() - start_time < timeout:
            logs = self._collector.get_logs(since=since)
            matching = [log for log in logs if regex.search(log.raw_line)]

            count = len(matching)
            if count >= min_count:
                logger.debug(
                    f"Found {count} matches for pattern '{pattern}' "
                    f"after {time.time() - start_time:.3f}s"
                )
                return matching

            # Sleep briefly before checking again
            time.sleep(0.1)

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

    def _resolve_since(self, since_mark: str | None) -> datetime | None:
        """Resolve time filter from mark name.

        Args:
            since_mark: Name of timestamp mark to filter from

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

    def parse_audit_log(self, entry: LogEntry) -> ParsedAuditEvent | None:
        """Parse a log entry into a structured audit event.

        Attempts to parse JSON log entries that contain audit events.
        Returns None if the entry is not a valid audit log.

        Args:
            entry: The log entry to parse

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

        return ParsedAuditEvent(
            timestamp=data.get("time", ""),
            level=data.get("level", ""),
            msg=msg,
            audit=data.get("audit", {}),
            raw_entry=entry,
        )

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
        while time.time() - start_time < timeout:
            logs = self._collector.get_logs(since=since)
            parsed = []
            for entry in logs:
                event = self.parse_audit_log(entry)
                if event:
                    parsed.append(event)
            if parsed:
                return parsed
            time.sleep(0.1)

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

        while time.time() - start_time < timeout:
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

            time.sleep(0.1)

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

        while time.time() - start_time < timeout:
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

            time.sleep(0.1)

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

        while time.time() - start_time < timeout:
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

            time.sleep(0.1)

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
            late_logs = [
                log for log in current_logs if log.timestamp > timeout_time
            ]

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

        raise AssertionError("\n".join(context))
