"""KAS audit log collection and assertion framework for pytest tests.

This module provides infrastructure to capture logs from KAS services during
test execution and assert on their contents. Logs are collected via background
threads tailing log files and buffered in memory for fast access.

Usage:
    def test_rewrap_logged(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, audit_logs):
        ct_file = encrypt_sdk.encrypt(pt_file, ...)
        audit_logs.mark("before_decrypt")
        decrypt_sdk.decrypt(ct_file, ...)
        audit_logs.assert_contains(r"rewrap.*200", min_count=1, since_mark="before_decrypt")
"""

import logging
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("xtest")


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

    def mark(self, label: str) -> datetime:
        """Mark a timestamp for later correlation with log entries.

        Args:
            label: Name for this timestamp (e.g., 'before_decrypt')

        Returns:
            The marked timestamp
        """
        now = datetime.now()
        self._marks[label] = now
        logger.debug(f"Marked timestamp '{label}' at {now}")
        return now

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

    def mark(self, label: str) -> datetime:
        """Mark a timestamp for later correlation.

        Args:
            label: Name for this timestamp

        Returns:
            The marked timestamp
        """
        if not self._collector or self._collector._disabled:
            return datetime.now()
        return self._collector.mark(label)

    def assert_contains(
        self,
        pattern: str | re.Pattern,
        min_count: int = 1,
        since_mark: str | None = None,
    ) -> list[LogEntry]:
        """Assert pattern appears in logs with optional constraints.

        Args:
            pattern: Regex pattern or substring to search for
            min_count: Minimum number of occurrences (default: 1)
            since_mark: Only check logs since marked timestamp

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
        logs = self._collector.get_logs(since=since)

        if isinstance(pattern, str):
            regex = re.compile(pattern, re.IGNORECASE)
        else:
            regex = pattern

        matching = [log for log in logs if regex.search(log.raw_line)]

        count = len(matching)
        if count < min_count:
            self._raise_assertion_error(
                f"Expected pattern '{pattern}' to appear at least {min_count} time(s), "
                f"but found {count} occurrence(s).",
                matching,
                logs,
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

    def _raise_assertion_error(
        self,
        message: str,
        matching: list[LogEntry],
        all_logs: list[LogEntry],
    ) -> None:
        """Raise AssertionError with rich context.

        Args:
            message: Main error message
            matching: Logs that matched the pattern
            all_logs: All logs that were searched
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

        recent_logs = all_logs[-10:] if len(all_logs) > 10 else all_logs
        if recent_logs:
            context.append(f"Recent context (last {len(recent_logs)} lines):")
            for log in recent_logs:
                context.append(
                    f"  [{log.timestamp}] {log.service_name}: {log.raw_line}"
                )
            context.append("")

        if self._collector:
            context.append("Log collection details:")
            context.append(f"  - Total logs collected: {len(all_logs)}")

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
