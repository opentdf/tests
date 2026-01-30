"""Minimal self-tests for the audit log collection and assertion framework.

These tests validate the core audit_logs module functionality without requiring
real services. They use mock data and temporary files to test the framework
in isolation.

Run with: pytest test_audit_logs.py -v
"""

from datetime import datetime
from pathlib import Path

import pytest

from audit_logs import AuditLogAsserter, AuditLogCollector, LogEntry


class TestLogEntry:
    """Tests for the LogEntry class."""

    def test_create_log_entry(self) -> None:
        """Test basic LogEntry creation."""
        now = datetime.now()
        entry = LogEntry(
            timestamp=now,
            raw_line='{"level": "info", "msg": "test"}',
            service_name="kas",
        )
        assert entry.timestamp == now
        assert entry.service_name == "kas"
        assert "level" in entry.raw_line


class TestAuditLogCollector:
    """Tests for the AuditLogCollector class."""

    def test_collector_initialization(self, tmp_path: Path) -> None:
        """Test collector initializes with correct defaults."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        assert collector.platform_dir == tmp_path
        assert collector.services == []
        assert collector.log_files is None
        assert not collector._disabled

    def test_mark_and_get_mark(self, tmp_path: Path) -> None:
        """Test timestamp marking functionality."""
        collector = AuditLogCollector(platform_dir=tmp_path)

        before = datetime.now()
        unique_mark = collector.mark("test_mark")
        after = datetime.now()

        # Mark should return a unique name with counter suffix
        assert unique_mark == "test_mark_1"

        # Get the timestamp for the unique mark
        marked_time = collector.get_mark(unique_mark)
        assert marked_time is not None
        assert before <= marked_time <= after

        # Original label without counter should not exist
        assert collector.get_mark("test_mark") is None
        assert collector.get_mark("nonexistent") is None


class TestAuditLogAsserter:
    """Tests for the AuditLogAsserter class."""

    @pytest.fixture
    def collector_with_logs(self, tmp_path: Path) -> AuditLogCollector:
        """Create a collector with pre-populated test logs."""
        collector = AuditLogCollector(platform_dir=tmp_path, services=["kas"])
        collector.start_time = datetime.now()

        now = datetime.now()
        test_logs = [
            (now, '{"level": "info", "msg": "rewrap request", "status": 200}', "kas"),
            (now, '{"level": "error", "msg": "rewrap failed", "status": 403}', "kas"),
            (now, "plain text log without json", "kas-alpha"),
        ]

        for ts, line, service in test_logs:
            collector._buffer.append(LogEntry(ts, line, service))

        return collector

    def test_assert_contains_success(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains finds matching logs."""
        asserter = AuditLogAsserter(collector_with_logs)

        matches = asserter.assert_contains(r"rewrap")
        assert len(matches) == 2

    def test_assert_contains_with_mark(
        self, collector_with_logs: AuditLogCollector
    ) -> None:
        """Test assert_contains with timestamp mark."""
        asserter = AuditLogAsserter(collector_with_logs)

        mark = asserter.mark("after_existing_logs")

        now = datetime.now()
        collector_with_logs._buffer.append(
            LogEntry(now, '{"msg": "new_log_after_mark"}', "kas")
        )

        matches = asserter.assert_contains(r"new_log_after_mark", since_mark=mark)
        assert len(matches) == 1

    def test_asserter_with_disabled_collector(self, tmp_path: Path) -> None:
        """Test asserter handles disabled collector gracefully."""
        collector = AuditLogCollector(platform_dir=tmp_path)
        collector._disabled = True
        asserter = AuditLogAsserter(collector)

        result = asserter.assert_contains("anything")
        assert result == []

    def test_asserter_with_none_collector(self) -> None:
        """Test asserter handles None collector gracefully."""
        asserter = AuditLogAsserter(None)

        result = asserter.assert_contains("anything")
        assert result == []
