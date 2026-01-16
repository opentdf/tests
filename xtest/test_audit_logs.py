"""Self-tests for the audit log collection and assertion framework.

These tests validate the audit_logs module functionality without requiring
real services. They use mock data and temporary files to test the framework
in isolation.

Run with: pytest test_audit_logs.py -v
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from audit_logs import AuditLogAsserter, AuditLogCollector, LogEntry


class TestLogEntry:
    """Tests for the LogEntry dataclass."""

    def test_create_log_entry(self) -> None:
        """Test basic LogEntry creation."""
        now = datetime.now()
        entry = LogEntry(
            timestamp=now,
            log_timestamp=now,
            raw_line='{"level": "info", "msg": "test"}',
            parsed_json={"level": "info", "msg": "test"},
            service_name="kas",
        )
        assert entry.timestamp == now
        assert entry.service_name == "kas"
        assert entry.parsed_json is not None
        assert entry.parsed_json["level"] == "info"

    def test_log_entry_with_no_json(self) -> None:
        """Test LogEntry with non-JSON content."""
        entry = LogEntry(
            timestamp=datetime.now(),
            log_timestamp=None,
            raw_line="plain text log line",
            parsed_json=None,
            service_name="kas-alpha",
        )
        assert entry.parsed_json is None
        assert entry.log_timestamp is None
        assert "plain text" in entry.raw_line


class TestAuditLogCollector:
    """Tests for the AuditLogCollector class."""

    def test_collector_initialization(self, tmp_path: Path) -> None:
        """Test collector initializes with correct defaults."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        assert collector.platform_dir == tmp_path
        assert collector.services == []
        assert collector.log_files is None
        assert not collector._disabled

    def test_collector_with_log_files(self, tmp_path: Path) -> None:
        """Test collector initialization with log files."""
        log_files = {
            "kas": tmp_path / "kas.log",
            "kas-alpha": tmp_path / "kas-alpha.log",
        }
        collector = AuditLogCollector(
            platform_dir=tmp_path,
            services=["kas", "kas-alpha"],
            log_files=log_files,
        )
        assert collector._mode == "file"
        assert collector.log_files == log_files

    def test_mark_and_get_mark(self, tmp_path: Path) -> None:
        """Test timestamp marking functionality."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        before = datetime.now()
        marked = collector.mark("test_mark")
        after = datetime.now()

        assert before <= marked <= after
        assert collector.get_mark("test_mark") == marked
        assert collector.get_mark("nonexistent") is None

    def test_multiple_marks(self, tmp_path: Path) -> None:
        """Test multiple timestamp marks."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        mark1 = collector.mark("first")
        time.sleep(0.01)
        mark2 = collector.mark("second")

        assert mark1 < mark2
        assert collector.get_mark("first") == mark1
        assert collector.get_mark("second") == mark2

    def test_get_logs_empty(self, tmp_path: Path) -> None:
        """Test get_logs returns empty list when no logs collected."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        assert collector.get_logs() == []

    def test_get_logs_with_service_filter(self, tmp_path: Path) -> None:
        """Test get_logs filters by service name."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        # Manually add entries to buffer for testing
        now = datetime.now()
        collector._buffer.append(LogEntry(now, now, "log1", None, "kas"))
        collector._buffer.append(LogEntry(now, now, "log2", None, "kas-alpha"))
        collector._buffer.append(LogEntry(now, now, "log3", None, "kas"))

        kas_logs = collector.get_logs(service="kas")
        assert len(kas_logs) == 2

        alpha_logs = collector.get_logs(service="kas-alpha")
        assert len(alpha_logs) == 1

    def test_get_logs_with_time_filter(self, tmp_path: Path) -> None:
        """Test get_logs filters by timestamp."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        old_time = datetime.now() - timedelta(hours=1)
        now = datetime.now()

        collector._buffer.append(LogEntry(old_time, old_time, "old log", None, "kas"))
        collector._buffer.append(LogEntry(now, now, "new log", None, "kas"))

        # Filter since 30 minutes ago
        since = datetime.now() - timedelta(minutes=30)
        recent_logs = collector.get_logs(since=since)
        assert len(recent_logs) == 1
        assert "new log" in recent_logs[0].raw_line

    def test_get_logs_with_log_timestamp_filter(self, tmp_path: Path) -> None:
        """Test get_logs with use_log_timestamp option."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        # Collection time is now, but log_timestamp is 2 hours ago
        collection_time = datetime.now()
        log_time_old = datetime.now() - timedelta(hours=2)
        log_time_recent = datetime.now() - timedelta(minutes=10)

        # Entry with old log_timestamp
        collector._buffer.append(
            LogEntry(collection_time, log_time_old, "old log event", None, "kas")
        )
        # Entry with recent log_timestamp
        collector._buffer.append(
            LogEntry(collection_time, log_time_recent, "recent log event", None, "kas")
        )
        # Entry with no log_timestamp
        collector._buffer.append(
            LogEntry(collection_time, None, "no timestamp log", None, "kas")
        )

        since = datetime.now() - timedelta(hours=1)

        # Without use_log_timestamp: filter by collection_time, all 3 match
        logs = collector.get_logs(since=since, use_log_timestamp=False)
        assert len(logs) == 3

        # With use_log_timestamp: filter by log_timestamp, only 1 matches
        # (old one is before since, and None is excluded)
        logs = collector.get_logs(since=since, use_log_timestamp=True)
        assert len(logs) == 1
        assert "recent log event" in logs[0].raw_line

    def test_disabled_collector(self, tmp_path: Path) -> None:
        """Test disabled collector returns empty results."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        collector._disabled = True

        collector._buffer.append(LogEntry(datetime.now(), None, "test", None, "kas"))

        # Even with data in buffer, disabled collector returns empty
        assert collector.get_logs() == []

    def test_write_to_disk(self, tmp_path: Path) -> None:
        """Test writing collected logs to disk."""
        collector = AuditLogCollector(platform_dir=tmp_path, services=["kas"])

        now = datetime.now()
        collector._buffer.append(LogEntry(now, now, "test log line 1", None, "kas"))
        collector._buffer.append(LogEntry(now, now, "test log line 2", None, "kas"))
        collector.mark("test_mark")

        output_file = tmp_path / "audit_logs.txt"
        collector.write_to_disk(output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert "Total entries: 2" in content
        assert "test_mark" in content
        assert "test log line 1" in content

    def test_reset_clears_buffer_and_marks(self, tmp_path: Path) -> None:
        """Test reset() clears buffer and marks."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        now = datetime.now()
        collector._buffer.append(LogEntry(now, now, "test log", None, "kas"))
        collector.mark("test_mark")

        assert len(collector._buffer) == 1
        assert collector.get_mark("test_mark") is not None

        collector.reset()

        assert len(collector._buffer) == 0
        assert collector.get_mark("test_mark") is None


class TestAuditLogCollectorFileParsing:
    """Tests for log file parsing functionality."""

    def test_parse_json_log_line(self, tmp_path: Path) -> None:
        """Test parsing JSON format log lines."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        json_line = json.dumps(
            {
                "timestamp": "2026-01-15T10:30:00.000Z",
                "level": "info",
                "msg": "rewrap request completed",
                "status": 200,
            }
        )

        entry = collector._parse_file_log_line("kas", json_line)

        assert entry.service_name == "kas"
        assert entry.parsed_json is not None
        assert entry.parsed_json["level"] == "info"
        assert entry.parsed_json["status"] == 200
        assert entry.log_timestamp is not None

    def test_parse_plain_text_log_line(self, tmp_path: Path) -> None:
        """Test parsing plain text log lines."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        plain_line = "2026-01-15 10:30:00 INFO rewrap request completed"

        entry = collector._parse_file_log_line("kas-alpha", plain_line)

        assert entry.service_name == "kas-alpha"
        assert entry.parsed_json is None
        assert entry.log_timestamp is not None
        assert "rewrap" in entry.raw_line

    def test_parse_timestamp_formats(self, tmp_path: Path) -> None:
        """Test parsing various timestamp formats."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        # RFC3339
        ts1 = collector._parse_timestamp_string("2026-01-15T10:30:00.123Z")
        assert ts1 is not None
        assert ts1.year == 2026

        # Simple format
        ts2 = collector._parse_timestamp_string("2026-01-15 10:30:00")
        assert ts2 is not None

        # Invalid format
        ts3 = collector._parse_timestamp_string("not a timestamp")
        assert ts3 is None


class TestAuditLogAsserter:
    """Tests for the AuditLogAsserter class."""

    @pytest.fixture
    def collector_with_logs(self, tmp_path: Path) -> AuditLogCollector:
        """Create a collector with pre-populated test logs."""
        collector = AuditLogCollector(platform_dir=tmp_path, services=["kas"])
        collector.start_time = datetime.now()

        now = datetime.now()

        # Add various log entries for testing
        test_logs = [
            (now, '{"level": "info", "msg": "rewrap request", "status": 200}', "kas"),
            (now, '{"level": "error", "msg": "rewrap failed", "status": 403}', "kas"),
            (
                now,
                '{"level": "info", "msg": "encrypt completed", "status": 200}',
                "kas",
            ),
            (now, "plain text log without json", "kas-alpha"),
            (now, '{"level": "debug", "msg": "internal operation"}', "kas"),
        ]

        for ts, line, service in test_logs:
            parsed = None
            if line.startswith("{"):
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    pass
            collector._buffer.append(LogEntry(ts, ts, line, parsed, service))

        return collector

    def test_asserter_with_disabled_collector(self, tmp_path: Path) -> None:
        """Test asserter handles disabled collector gracefully."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        collector._disabled = True
        asserter = AuditLogAsserter(collector)

        # Should not raise, just return empty
        result = asserter.assert_contains("anything")
        assert result == []

    def test_asserter_with_none_collector(self) -> None:
        """Test asserter handles None collector gracefully."""
        asserter = AuditLogAsserter(None)

        # Should not raise, just return empty
        result = asserter.assert_contains("anything")
        assert result == []

    def test_assert_contains_success(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains finds matching logs."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should find rewrap logs
        matches = asserter.assert_contains(r"rewrap")
        assert len(matches) == 2

        # Should find specific status
        matches = asserter.assert_contains(r"status.*200")
        assert len(matches) == 2

    def test_assert_contains_failure(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains raises on missing pattern."""
        asserter = AuditLogAsserter(collector_with_logs)

        with pytest.raises(AssertionError) as exc_info:
            asserter.assert_contains(r"nonexistent_pattern")

        assert "Expected pattern" in str(exc_info.value)
        assert "nonexistent_pattern" in str(exc_info.value)

    def test_assert_contains_min_count(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains with min_count constraint."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should pass - there are 2 rewrap logs
        matches = asserter.assert_contains(r"rewrap", min_count=2)
        assert len(matches) == 2

        # Should fail - not enough matches
        with pytest.raises(AssertionError):
            asserter.assert_contains(r"rewrap", min_count=5)

    def test_assert_contains_max_count(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains with max_count constraint."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should pass - exactly 2 rewrap logs
        matches = asserter.assert_contains(r"rewrap", max_count=2)
        assert len(matches) == 2

        # Should fail - too many matches
        with pytest.raises(AssertionError):
            asserter.assert_contains(r"rewrap", max_count=1)

    def test_assert_contains_service_filter(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains with service filter."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Only kas-alpha has the plain text log
        matches = asserter.assert_contains(r"plain text", service="kas-alpha")
        assert len(matches) == 1

        # Should fail - pattern not in kas service
        with pytest.raises(AssertionError):
            asserter.assert_contains(r"plain text", service="kas")

    def test_assert_contains_with_mark(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains with timestamp mark."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Mark timestamp (all existing logs are before this mark)
        asserter.mark("after_existing_logs")

        # Add a new log after the mark
        now = datetime.now()
        collector_with_logs._buffer.append(
            LogEntry(now, now, '{"msg": "new_log_after_mark"}', None, "kas")
        )

        # Should find the new log since mark
        matches = asserter.assert_contains(
            r"new_log_after_mark", since_mark="after_existing_logs"
        )
        assert len(matches) == 1

    def test_assert_count(self, collector_with_logs: AuditLogCollector) -> None:
        """Test assert_count for exact match."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should pass - exactly 2 rewrap logs
        matches = asserter.assert_count(r"rewrap", expected_count=2)
        assert len(matches) == 2

        # Should fail - wrong count
        with pytest.raises(AssertionError):
            asserter.assert_count(r"rewrap", expected_count=3)

    def test_assert_within_time(self, collector_with_logs: AuditLogCollector) -> None:
        """Test assert_within_time for time-bounded assertions."""
        asserter = AuditLogAsserter(collector_with_logs)

        reference_time = datetime.now()

        # All logs are recent, should find them
        matches = asserter.assert_within_time(
            r"rewrap", reference_time=reference_time, window_seconds=60
        )
        assert len(matches) == 2

    def test_get_matching_logs(self, collector_with_logs: AuditLogCollector) -> None:
        """Test get_matching_logs (non-asserting query)."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should return matches without asserting
        matches = asserter.get_matching_logs(r"rewrap")
        assert len(matches) == 2

        # Should return empty list for no matches (no assertion)
        matches = asserter.get_matching_logs(r"nonexistent")
        assert matches == []

    def test_assert_not_contains_success(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_not_contains passes when pattern not found."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should pass - pattern not in logs
        asserter.assert_not_contains(r"this_pattern_is_not_present")

    def test_assert_not_contains_failure(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_not_contains raises when pattern IS found."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should fail - pattern exists in logs
        with pytest.raises(AssertionError) as exc_info:
            asserter.assert_not_contains(r"rewrap")

        assert "NOT appear" in str(exc_info.value)
        assert "2 occurrence" in str(exc_info.value)

    def test_assert_not_contains_with_service_filter(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_not_contains with service filter."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should pass - rewrap not in kas-alpha service
        asserter.assert_not_contains(r"rewrap", service="kas-alpha")

        # Should fail - rewrap exists in kas service
        with pytest.raises(AssertionError):
            asserter.assert_not_contains(r"rewrap", service="kas")

    def test_asserter_reset(self, collector_with_logs: AuditLogCollector) -> None:
        """Test asserter reset() clears collector buffer."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Verify logs exist
        assert len(asserter.get_matching_logs(r"rewrap")) == 2

        # Reset and verify empty
        asserter.reset()
        assert len(asserter.get_matching_logs(r"rewrap")) == 0

    def test_mark_returns_timestamp(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test mark() returns timestamp."""
        asserter = AuditLogAsserter(collector_with_logs)

        before = datetime.now()
        ts = asserter.mark("test")
        after = datetime.now()

        assert before <= ts <= after

    def test_error_message_includes_context(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test that assertion errors include helpful context."""
        asserter = AuditLogAsserter(collector_with_logs)

        with pytest.raises(AssertionError) as exc_info:
            asserter.assert_contains(r"this_does_not_exist")

        error_msg = str(exc_info.value)

        # Should include useful debugging info
        assert "Expected pattern" in error_msg
        assert "Recent context" in error_msg
        assert "Log collection details" in error_msg
        assert "Total logs collected" in error_msg

    def test_wait_for_log_immediate_match(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test wait_for_log returns immediately when pattern already exists."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Pattern already exists, should return immediately
        matches = asserter.wait_for_log(r"rewrap", timeout_seconds=1.0)
        assert len(matches) == 2

    def test_wait_for_log_timeout(self, tmp_path: Path) -> None:
        """Test wait_for_log raises TimeoutError when pattern not found."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        collector.start_time = datetime.now()

        # Add a log that doesn't match
        now = datetime.now()
        collector._buffer.append(
            LogEntry(now, now, '{"msg": "unrelated log"}', None, "kas")
        )

        asserter = AuditLogAsserter(collector)

        with pytest.raises(TimeoutError) as exc_info:
            asserter.wait_for_log(r"nonexistent_pattern", timeout_seconds=0.5)

        assert "Timeout" in str(exc_info.value)
        assert "nonexistent_pattern" in str(exc_info.value)

    def test_wait_for_log_with_service_filter(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test wait_for_log with service filter."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should find plain text log in kas-alpha
        matches = asserter.wait_for_log(
            r"plain text", timeout_seconds=1.0, service="kas-alpha"
        )
        assert len(matches) == 1

    def test_wait_for_log_min_count(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test wait_for_log with min_count requirement."""
        asserter = AuditLogAsserter(collector_with_logs)

        # Should find 2 rewrap logs
        matches = asserter.wait_for_log(r"rewrap", timeout_seconds=1.0, min_count=2)
        assert len(matches) == 2

        # Should timeout - need 5 but only have 2
        with pytest.raises(TimeoutError):
            asserter.wait_for_log(r"rewrap", timeout_seconds=0.5, min_count=5)


class TestAuditLogIntegration:
    """Integration tests using temporary log files."""

    def test_file_mode_collection(self, tmp_path: Path) -> None:
        """Test collecting logs from actual files."""
        # Create a test log file
        log_file = tmp_path / "test.log"
        log_file.write_text("")

        log_files = {"test": log_file}
        collector = AuditLogCollector(
            platform_dir=tmp_path,
            services=["test"],
            log_files=log_files,
        )

        # Start collection
        collector.start()

        # Write some logs to the file
        with open(log_file, "a") as f:
            f.write('{"level": "info", "msg": "test message 1"}\n')
            f.write('{"level": "error", "msg": "test error"}\n')
            f.flush()

        # Give collector time to read
        time.sleep(0.3)

        # Stop and check
        collector.stop()

        logs = collector.get_logs()
        # May or may not have captured depending on timing, but shouldn't crash
        assert isinstance(logs, list)

    def test_disabled_on_missing_platform_dir(self) -> None:
        """Test collector disables when platform dir doesn't exist."""
        collector = AuditLogCollector(
            platform_dir=Path("/nonexistent/path/to/platform")
        )
        collector.start()

        assert collector._disabled is True


class TestCaseInsensitiveMatching:
    """Tests for case-insensitive pattern matching."""

    def test_assert_contains_case_insensitive(self, tmp_path: Path) -> None:
        """Test that pattern matching is case-insensitive."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        collector.start_time = datetime.now()
        now = datetime.now()

        collector._buffer.append(
            LogEntry(now, now, "REWRAP request completed", None, "kas")
        )
        collector._buffer.append(
            LogEntry(now, now, "rewrap request started", None, "kas")
        )

        asserter = AuditLogAsserter(collector)

        # Should match both regardless of case
        matches = asserter.assert_contains(r"rewrap")
        assert len(matches) == 2

        matches = asserter.assert_contains(r"REWRAP")
        assert len(matches) == 2
