"""KAS audit log collection and assertion framework for pytest tests.

This module provides infrastructure to capture docker compose logs from KAS
services during test execution and assert on their contents. Logs are collected
via background subprocess and buffered in memory for fast access.

Usage:
    def test_rewrap_logged(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, audit_logs):
        ct_file = encrypt_sdk.encrypt(pt_file, ...)
        audit_logs.mark("before_decrypt")
        decrypt_sdk.decrypt(ct_file, ...)
        audit_logs.assert_contains(r"rewrap.*200", min_count=1, since_mark="before_decrypt")
"""

import json
import logging
import re
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("xtest")


@dataclass
class LogEntry:
    """Represents a single parsed log entry from docker compose logs."""

    timestamp: datetime
    """When the log was collected by this framework."""

    log_timestamp: datetime | None
    """Timestamp parsed from the log line itself (if available)."""

    raw_line: str
    """The original log line as received from docker compose."""

    parsed_json: dict | None
    """Parsed JSON content if the log is in JSON format, otherwise None."""

    service_name: str
    """Docker compose service name (e.g., 'kas', 'kas-alpha')."""


class AuditLogCollector:
    """Collects logs from docker compose services in the background.

    Starts a subprocess running `docker compose logs --follow` and reads
    logs into a thread-safe buffer. Provides methods to query logs and
    mark timestamps for correlation with test actions.
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
            platform_dir: Path to platform directory containing docker-compose.yaml
            services: List of service names to monitor (e.g., ['kas', 'kas-alpha']).
                     If None or empty, monitors all services.
            log_files: Optional dict mapping service names to log file paths.
                      If provided, reads from files instead of docker compose.
                      Example: {'kas': Path('logs/kas-main.log'), 'kas-alpha': Path('logs/kas-alpha.log')}
        """
        self.platform_dir = platform_dir
        self.services = services or []
        self.log_files = log_files
        self._buffer: deque[LogEntry] = deque(maxlen=self.MAX_BUFFER_SIZE)
        self._marks: dict[str, datetime] = {}
        self._process: subprocess.Popen | None = None
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._disabled = False
        self._error: Exception | None = None
        self.log_file_path: Path | None = None
        self.log_file_written = False
        self._mode: str = "file" if log_files else "docker"

    def start(self) -> None:
        """Start background log collection.

        Supports two modes:
        - File mode: Tails log files directly (preferred for CI)
        - Docker mode: Uses docker compose logs (fallback for local dev)

        Gracefully handles errors by disabling collection if resources unavailable.
        """
        if self._disabled:
            return

        # Check if platform directory exists
        if not self.platform_dir.exists():
            logger.warning(
                f"Platform directory not found: {self.platform_dir}. "
                f"Audit log collection disabled."
            )
            self._disabled = True
            return

        if self._mode == "file":
            self._start_file_mode()
        else:
            self._start_docker_mode()

    def _start_file_mode(self) -> None:
        """Start log collection from files (tailing)."""
        if not self.log_files:
            logger.warning("No log files provided for file mode. Disabling collection.")
            self._disabled = True
            return

        # Filter to existing files
        existing_files = {
            service: path
            for service, path in self.log_files.items()
            if path.exists()
        }

        if not existing_files:
            logger.warning(
                f"None of the log files exist yet: {list(self.log_files.values())}. "
                f"Will wait for them to be created..."
            )
            # Don't disable - files may be created soon by the platform startup
            existing_files = self.log_files

        logger.debug(f"Starting file-based log collection for: {list(existing_files.keys())}")

        # Start a thread for each log file to tail
        for service, log_path in existing_files.items():
            thread = threading.Thread(
                target=self._tail_file,
                args=(service, log_path),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

        logger.info(
            f"Audit log collection started (file mode) for: {', '.join(existing_files.keys())}"
        )

    def _start_docker_mode(self) -> None:
        """Start log collection from docker compose."""
        # Check if docker compose is available
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                timeout=2,
                check=True,
            )
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ) as e:
            logger.warning(
                f"Docker compose not available: {e}. "
                f"Audit log collection disabled. Tests will continue without log assertions."
            )
            self._disabled = True
            return

        # Get running services to filter
        running_services = self._get_running_services()
        if not running_services:
            logger.warning(
                "No docker compose services found running. "
                "Audit log collection disabled."
            )
            self._disabled = True
            return

        # Filter to requested services that are actually running
        if self.services:
            filtered_services = [s for s in self.services if s in running_services]
            if not filtered_services:
                logger.warning(
                    f"None of the requested services {self.services} are running. "
                    f"Available services: {running_services}. "
                    f"Audit log collection disabled."
                )
                self._disabled = True
                return
        else:
            filtered_services = running_services

        # Build docker compose logs command
        cmd = [
            "docker",
            "compose",
            "-f",
            str(self.platform_dir / "docker-compose.yaml"),
            "logs",
            "--follow",
            "--no-color",
            "--timestamps",
        ]
        cmd.extend(filtered_services)

        logger.debug(f"Starting docker compose log collection: {' '.join(cmd)}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=1,
            )
        except Exception as e:
            logger.error(f"Failed to start docker compose logs subprocess: {e}")
            self._disabled = True
            return

        # Start background thread to read logs
        thread = threading.Thread(target=self._read_docker_logs, daemon=True)
        thread.start()
        self._threads.append(thread)

        logger.info(
            f"Audit log collection started (docker mode) for: {', '.join(filtered_services)}"
        )

    def stop(self) -> None:
        """Stop log collection and cleanup resources."""
        if self._disabled:
            return

        logger.debug("Stopping audit log collection")

        self._stop_event.set()

        # Stop docker compose process if running
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        # Wait for all threads to finish
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
            since: Only return logs collected after this timestamp
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

    def _get_running_services(self) -> list[str]:
        """Query docker compose for running services.

        Returns:
            List of service names currently running
        """
        try:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(self.platform_dir / "docker-compose.yaml"),
                    "ps",
                    "--services",
                    "--filter",
                    "status=running",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            return [s.strip() for s in result.stdout.splitlines() if s.strip()]
        except Exception as e:
            logger.warning(f"Failed to query running services: {e}")
            return []

    def _tail_file(self, service: str, log_path: Path) -> None:
        """Background thread target that tails a log file.

        Args:
            service: Service name (e.g., 'kas', 'kas-alpha')
            log_path: Path to log file to tail
        """
        logger.debug(f"Starting to tail {log_path} for service {service}")

        # Wait for file to exist (with timeout)
        wait_start = datetime.now()
        while not log_path.exists():
            if self._stop_event.is_set():
                return
            if (datetime.now() - wait_start).total_seconds() > 30:
                logger.warning(f"Timeout waiting for log file: {log_path}")
                return
            self._stop_event.wait(0.5)

        try:
            with open(log_path, "r") as f:
                # Seek to end for new logs only
                f.seek(0, 2)

                while not self._stop_event.is_set():
                    line = f.readline()
                    if line:
                        try:
                            entry = self._parse_file_log_line(service, line.rstrip())
                            self._buffer.append(entry)
                        except Exception as e:
                            logger.debug(f"Error parsing log line from {service}: {e}")
                    else:
                        # No new data, wait a bit
                        self._stop_event.wait(0.1)
        except Exception as e:
            logger.error(f"Error tailing log file {log_path}: {e}")
            self._error = e

    def _read_docker_logs(self) -> None:
        """Background thread target that reads logs from docker compose subprocess."""
        if not self._process or not self._process.stdout:
            return

        try:
            for line in iter(self._process.stdout.readline, b""):
                if self._stop_event.is_set():
                    break

                try:
                    decoded_line = line.decode("utf-8", errors="replace").rstrip()
                    if decoded_line:
                        entry = self._parse_docker_log_line(decoded_line)
                        self._buffer.append(entry)
                except Exception as e:
                    logger.debug(f"Error parsing docker log line: {e}")
                    continue
        except Exception as e:
            logger.error(f"Docker log collection subprocess error: {e}")
            self._error = e
        finally:
            if self._process and self._process.stdout:
                self._process.stdout.close()

    def _parse_file_log_line(self, service: str, raw_line: str) -> LogEntry:
        """Parse log line from file with format auto-detection.

        Args:
            service: Service name (e.g., 'kas', 'kas-alpha')
            raw_line: Raw log line from file

        Returns:
            Parsed LogEntry
        """
        collection_time = datetime.now()

        # Try JSON parsing
        parsed_json = None
        log_timestamp = None
        try:
            parsed_json = json.loads(raw_line)
            log_timestamp = self._parse_timestamp_from_json(parsed_json)
        except (json.JSONDecodeError, ValueError):
            # Not JSON, try syslog timestamp parsing
            log_timestamp = self._parse_syslog_timestamp(raw_line)

        return LogEntry(
            timestamp=collection_time,
            log_timestamp=log_timestamp,
            raw_line=raw_line,
            parsed_json=parsed_json,
            service_name=service,
        )

    def _parse_docker_log_line(self, raw_line: str) -> LogEntry:
        """Parse docker compose log line with format auto-detection.

        Docker compose log format: "service_name_1 | 2026-01-06T10:15:23.456789Z <log content>"

        Args:
            raw_line: Raw log line from docker compose

        Returns:
            Parsed LogEntry
        """
        collection_time = datetime.now()

        # Extract docker compose metadata
        # Format: "service_name_1 | <log content>"
        parts = raw_line.split("|", 1)
        if len(parts) == 2:
            service_name = parts[0].strip().rsplit("_", 1)[0]
            log_content = parts[1].strip()
        else:
            service_name = "unknown"
            log_content = raw_line

        # Try JSON parsing
        parsed_json = None
        log_timestamp = None
        try:
            parsed_json = json.loads(log_content)
            log_timestamp = self._parse_timestamp_from_json(parsed_json)
        except (json.JSONDecodeError, ValueError):
            # Not JSON, try syslog timestamp parsing
            log_timestamp = self._parse_syslog_timestamp(log_content)

        return LogEntry(
            timestamp=collection_time,
            log_timestamp=log_timestamp,
            raw_line=raw_line,
            parsed_json=parsed_json,
            service_name=service_name,
        )

    def _parse_timestamp_from_json(self, data: dict) -> datetime | None:
        """Extract timestamp from common JSON log fields.

        Args:
            data: Parsed JSON log object

        Returns:
            Parsed datetime or None if not found
        """
        for field in ["timestamp", "time", "@timestamp", "ts"]:
            if field in data:
                return self._parse_timestamp_string(str(data[field]))
        return None

    def _parse_syslog_timestamp(self, line: str) -> datetime | None:
        """Parse timestamp from syslog-format line.

        Args:
            line: Log line content

        Returns:
            Parsed datetime or None if not found
        """
        patterns = [
            # RFC3339: 2026-01-06T10:15:23.456Z
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)",
            # RFC5424: 2026-01-06T10:15:23.456+00:00
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2})",
            # Simple format: 2026-01-06 10:15:23
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return self._parse_timestamp_string(match.group(1))

        return None

    def _parse_timestamp_string(self, ts_str: str) -> datetime | None:
        """Parse timestamp string in various formats.

        Args:
            ts_str: Timestamp string

        Returns:
            Parsed datetime or None on error
        """
        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue

        return None


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
        max_count: int | None = None,
        within_seconds: float | None = None,
        since_mark: str | None = None,
        service: str | None = None,
    ) -> list[LogEntry]:
        """Assert pattern appears in logs with optional constraints.

        Args:
            pattern: Regex pattern or substring to search for
            min_count: Minimum number of occurrences (default: 1)
            max_count: Maximum number of occurrences (optional)
            within_seconds: Only check logs from last N seconds
            since_mark: Only check logs since marked timestamp
            service: Only check logs from specific service

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

        # Determine time filter
        since = None
        if since_mark:
            since = self._collector.get_mark(since_mark)
            if not since:
                raise ValueError(f"Unknown timestamp mark: {since_mark}")
        elif within_seconds:
            since = datetime.now() - timedelta(seconds=within_seconds)

        # Get filtered logs
        logs = self._collector.get_logs(since=since, service=service)

        # Find matching logs
        if isinstance(pattern, str):
            regex = re.compile(pattern, re.IGNORECASE)
        else:
            regex = pattern

        matching = [log for log in logs if regex.search(log.raw_line)]

        # Check constraints
        count = len(matching)
        if count < min_count:
            self._raise_assertion_error(
                f"Expected pattern '{pattern}' to appear at least {min_count} time(s), "
                f"but found {count} occurrence(s).",
                matching,
                logs,
                pattern,
            )

        if max_count is not None and count > max_count:
            self._raise_assertion_error(
                f"Expected pattern '{pattern}' to appear at most {max_count} time(s), "
                f"but found {count} occurrence(s).",
                matching,
                logs,
                pattern,
            )

        return matching

    def assert_count(
        self,
        pattern: str | re.Pattern,
        expected_count: int,
        within_seconds: float | None = None,
        since_mark: str | None = None,
        service: str | None = None,
    ) -> list[LogEntry]:
        """Assert exact count of pattern occurrences.

        Args:
            pattern: Regex pattern to search for
            expected_count: Expected number of occurrences
            within_seconds: Only check logs from last N seconds
            since_mark: Only check logs since marked timestamp
            service: Only check logs from specific service

        Returns:
            Matching log entries

        Raises:
            AssertionError: If count doesn't match
        """
        return self.assert_contains(
            pattern=pattern,
            min_count=expected_count,
            max_count=expected_count,
            within_seconds=within_seconds,
            since_mark=since_mark,
            service=service,
        )

    def assert_within_time(
        self,
        pattern: str | re.Pattern,
        reference_time: datetime,
        window_seconds: float = 5.0,
    ) -> list[LogEntry]:
        """Assert pattern appears within time window of reference.

        Args:
            pattern: Regex pattern to search for
            reference_time: Reference timestamp
            window_seconds: Time window in seconds (default: 5.0)

        Returns:
            Matching log entries within time window

        Raises:
            AssertionError: If no matches within time window
        """
        if not self._collector or self._collector._disabled:
            logger.warning("Audit log assertion skipped (collection disabled)")
            return []

        # Get all logs
        logs = self._collector.get_logs()

        # Find matching logs within time window
        if isinstance(pattern, str):
            regex = re.compile(pattern, re.IGNORECASE)
        else:
            regex = pattern

        start_time = reference_time - timedelta(seconds=window_seconds)
        end_time = reference_time + timedelta(seconds=window_seconds)

        matching = [
            log
            for log in logs
            if regex.search(log.raw_line) and start_time <= log.timestamp <= end_time
        ]

        if not matching:
            self._raise_assertion_error(
                f"Expected pattern '{pattern}' to appear within {window_seconds}s of {reference_time}, "
                f"but no matches found in time window.",
                matching,
                logs,
                pattern,
            )

        return matching

    def get_matching_logs(
        self,
        pattern: str | re.Pattern,
        since: datetime | None = None,
        service: str | None = None,
    ) -> list[LogEntry]:
        """Get all logs matching pattern (non-asserting query).

        Args:
            pattern: Regex pattern to search for
            since: Only return logs after this timestamp
            service: Only return logs from this service

        Returns:
            List of matching log entries
        """
        if not self._collector or self._collector._disabled:
            return []

        logs = self._collector.get_logs(since=since, service=service)

        if isinstance(pattern, str):
            regex = re.compile(pattern, re.IGNORECASE)
        else:
            regex = pattern

        return [log for log in logs if regex.search(log.raw_line)]

    def _raise_assertion_error(
        self,
        message: str,
        matching: list[LogEntry],
        all_logs: list[LogEntry],
        pattern: str | re.Pattern,
    ) -> None:
        """Raise AssertionError with rich context.

        Args:
            message: Main error message
            matching: Logs that matched the pattern
            all_logs: All logs that were searched
            pattern: Pattern that was searched for
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

        # Show recent context
        recent_logs = all_logs[-10:] if len(all_logs) > 10 else all_logs
        if recent_logs:
            context.append(f"Recent context (last {len(recent_logs)} lines):")
            for log in recent_logs:
                context.append(
                    f"  [{log.timestamp}] {log.service_name}: {log.raw_line}"
                )
            context.append("")

        # Collection summary
        if self._collector:
            context.append("Log collection details:")
            context.append(f"  - Total logs collected: {len(all_logs)}")
            if self._collector.services:
                context.append(
                    f"  - Services monitored: {', '.join(self._collector.services)}"
                )
            if self._collector._marks:
                context.append(
                    f"  - Timestamp marks: {', '.join(self._collector._marks.keys())}"
                )

        raise AssertionError("\n".join(context))
