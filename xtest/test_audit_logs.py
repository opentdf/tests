"""Minimal self-tests for the audit log collection and assertion framework.

These tests validate the core audit_logs module functionality without requiring
real services. They use mock data and temporary files to test the framework
in isolation.

Run with: pytest test_audit_logs.py -v
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from audit_logs import (
    ACTION_RESULTS,
    ACTION_TYPES,
    OBJECT_TYPES,
    VERB_DECISION,
    VERB_POLICY_CRUD,
    VERB_REWRAP,
    AuditLogAsserter,
    AuditLogCollector,
    LogEntry,
    ParsedAuditEvent,  # noqa: F401 - Used in TestParsedAuditEvent class
)


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


class TestAuditConstants:
    """Tests for audit log constants."""

    def test_object_types_not_empty(self) -> None:
        """Test that OBJECT_TYPES contains expected values."""
        assert len(OBJECT_TYPES) > 0
        assert "namespace" in OBJECT_TYPES
        assert "attribute_definition" in OBJECT_TYPES
        assert "attribute_value" in OBJECT_TYPES
        assert "key_object" in OBJECT_TYPES

    def test_action_types_not_empty(self) -> None:
        """Test that ACTION_TYPES contains expected values."""
        assert len(ACTION_TYPES) > 0
        assert "create" in ACTION_TYPES
        assert "read" in ACTION_TYPES
        assert "update" in ACTION_TYPES
        assert "delete" in ACTION_TYPES
        assert "rewrap" in ACTION_TYPES

    def test_action_results_not_empty(self) -> None:
        """Test that ACTION_RESULTS contains expected values."""
        assert len(ACTION_RESULTS) > 0
        assert "success" in ACTION_RESULTS
        assert "failure" in ACTION_RESULTS
        assert "error" in ACTION_RESULTS
        assert "cancel" in ACTION_RESULTS

    def test_verbs_defined(self) -> None:
        """Test that verb constants are defined."""
        assert VERB_DECISION == "decision"
        assert VERB_POLICY_CRUD == "policy crud"
        assert VERB_REWRAP == "rewrap"


class TestParsedAuditEvent:
    """Tests for ParsedAuditEvent parsing and matching."""

    def _make_rewrap_audit_log(
        self,
        result: str = "success",
        policy_uuid: str = "test-uuid-123",
        key_id: str = "test-key",
        algorithm: str = "AES-256-GCM",
        attr_fqns: list[str] | None = None,
    ) -> str:
        """Create a mock rewrap audit log JSON string."""
        return json.dumps(
            {
                "time": "2024-01-15T10:30:00Z",
                "level": "AUDIT",
                "msg": "rewrap",
                "audit": {
                    "object": {
                        "type": "key_object",
                        "id": policy_uuid,
                        "attributes": {
                            "attrs": attr_fqns or [],
                            "assertions": [],
                            "permissions": [],
                        },
                    },
                    "action": {"type": "rewrap", "result": result},
                    "actor": {"id": "test-actor", "attributes": []},
                    "eventMetaData": {
                        "keyID": key_id,
                        "algorithm": algorithm,
                        "tdfFormat": "ztdf",
                        "policyBinding": "test-binding",
                    },
                    "clientInfo": {
                        "platform": "kas",
                        "userAgent": "test-agent",
                        "requestIP": "127.0.0.1",
                    },
                    "requestId": "req-123",
                    "timestamp": "2024-01-15T10:30:00Z",
                },
            }
        )

    def _make_policy_crud_log(
        self,
        action_type: str = "create",
        result: str = "success",
        object_type: str = "namespace",
        object_id: str = "ns-uuid-123",
    ) -> str:
        """Create a mock policy CRUD audit log JSON string."""
        return json.dumps(
            {
                "time": "2024-01-15T10:30:00Z",
                "level": "AUDIT",
                "msg": "policy crud",
                "audit": {
                    "object": {
                        "type": object_type,
                        "id": object_id,
                    },
                    "action": {"type": action_type, "result": result},
                    "actor": {"id": "admin-user", "attributes": []},
                    "clientInfo": {
                        "platform": "policy",
                        "userAgent": "otdfctl",
                        "requestIP": "127.0.0.1",
                    },
                    "requestId": "req-456",
                    "timestamp": "2024-01-15T10:30:00Z",
                },
            }
        )

    def _make_decision_v2_log(
        self,
        result: str = "success",
        entity_id: str = "client-123",
        action_name: str = "DECRYPT",
    ) -> str:
        """Create a mock decision v2 audit log JSON string."""
        return json.dumps(
            {
                "time": "2024-01-15T10:30:00Z",
                "level": "AUDIT",
                "msg": "decision",
                "audit": {
                    "object": {
                        "type": "entity_object",
                        "id": f"{entity_id}-{action_name}",
                        "name": f"decisionRequest-{action_name}",
                    },
                    "action": {"type": "read", "result": result},
                    "actor": {"id": entity_id, "attributes": []},
                    "eventMetaData": {
                        "resource_decisions": [],
                        "fulfillable_obligation_value_fqns": [],
                        "obligations_satisfied": True,
                    },
                    "clientInfo": {
                        "platform": "authorization.v2",
                        "userAgent": "sdk-client",
                        "requestIP": "127.0.0.1",
                    },
                    "requestId": "req-789",
                    "timestamp": "2024-01-15T10:30:00Z",
                },
            }
        )

    def test_parse_rewrap_log(self) -> None:
        """Test parsing a rewrap audit log."""
        raw_line = self._make_rewrap_audit_log(
            result="success",
            key_id="my-key",
            attr_fqns=["https://example.com/attr/foo/value/bar"],
        )
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="kas"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)

        assert event is not None
        assert event.msg == "rewrap"
        assert event.action_result == "success"
        assert event.action_type == "rewrap"
        assert event.object_type == "key_object"
        assert event.key_id == "my-key"
        assert "https://example.com/attr/foo/value/bar" in event.object_attrs

    def test_parse_policy_crud_log(self) -> None:
        """Test parsing a policy CRUD audit log."""
        raw_line = self._make_policy_crud_log(
            action_type="create", object_type="namespace", object_id="ns-123"
        )
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="platform"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)

        assert event is not None
        assert event.msg == "policy crud"
        assert event.action_result == "success"
        assert event.action_type == "create"
        assert event.object_type == "namespace"
        assert event.object_id == "ns-123"

    def test_parse_decision_v2_log(self) -> None:
        """Test parsing a decision v2 audit log."""
        raw_line = self._make_decision_v2_log(
            result="success", entity_id="client-abc", action_name="DECRYPT"
        )
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="platform"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)

        assert event is not None
        assert event.msg == "decision"
        assert event.action_result == "success"
        assert event.actor_id == "client-abc"
        assert event.client_platform == "authorization.v2"
        assert "DECRYPT" in (event.object_id or "")

    def test_parse_non_audit_log_returns_none(self) -> None:
        """Test parsing a non-audit log returns None."""
        raw_line = json.dumps({"level": "INFO", "msg": "server started"})
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="platform"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)

        assert event is None

    def test_parse_invalid_json_returns_none(self) -> None:
        """Test parsing invalid JSON returns None."""
        entry = LogEntry(
            timestamp=datetime.now(),
            raw_line="not valid json",
            service_name="platform",
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)

        assert event is None

    def test_matches_rewrap_basic(self) -> None:
        """Test ParsedAuditEvent.matches_rewrap with basic criteria."""
        raw_line = self._make_rewrap_audit_log(result="success", key_id="key-1")
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="kas"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)
        assert event is not None

        # Should match with correct result
        assert event.matches_rewrap(result="success")
        # Should not match with wrong result
        assert not event.matches_rewrap(result="failure")
        # Should match with correct key_id
        assert event.matches_rewrap(result="success", key_id="key-1")
        # Should not match with wrong key_id
        assert not event.matches_rewrap(result="success", key_id="wrong-key")

    def test_matches_rewrap_with_attrs(self) -> None:
        """Test ParsedAuditEvent.matches_rewrap with attribute filtering."""
        raw_line = self._make_rewrap_audit_log(
            result="success",
            attr_fqns=[
                "https://example.com/attr/foo/value/bar",
                "https://example.com/attr/baz/value/qux",
            ],
        )
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="kas"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)
        assert event is not None

        # Should match when all requested attrs are present
        assert event.matches_rewrap(
            result="success",
            attr_fqns=["https://example.com/attr/foo/value/bar"],
        )
        # Should match when all requested attrs are present (multiple)
        assert event.matches_rewrap(
            result="success",
            attr_fqns=[
                "https://example.com/attr/foo/value/bar",
                "https://example.com/attr/baz/value/qux",
            ],
        )
        # Should not match when a requested attr is missing
        assert not event.matches_rewrap(
            result="success",
            attr_fqns=["https://example.com/attr/missing/value/attr"],
        )

    def test_matches_policy_crud(self) -> None:
        """Test ParsedAuditEvent.matches_policy_crud."""
        raw_line = self._make_policy_crud_log(
            action_type="create", object_type="namespace", object_id="ns-abc"
        )
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="platform"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)
        assert event is not None

        # Should match with correct criteria
        assert event.matches_policy_crud(result="success", action_type="create")
        assert event.matches_policy_crud(result="success", object_type="namespace")
        assert event.matches_policy_crud(result="success", object_id="ns-abc")
        # Should not match with wrong criteria
        assert not event.matches_policy_crud(result="failure")
        assert not event.matches_policy_crud(result="success", action_type="delete")

    def test_matches_decision(self) -> None:
        """Test ParsedAuditEvent.matches_decision."""
        raw_line = self._make_decision_v2_log(
            result="success", entity_id="client-xyz", action_name="DECRYPT"
        )
        entry = LogEntry(
            timestamp=datetime.now(), raw_line=raw_line, service_name="platform"
        )

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry)
        assert event is not None

        # Should match with correct criteria
        assert event.matches_decision(result="success")
        assert event.matches_decision(result="success", entity_id="client-xyz")
        assert event.matches_decision(result="success", action_name="DECRYPT")
        # Should not match with wrong criteria
        assert not event.matches_decision(result="failure")
        assert not event.matches_decision(result="success", entity_id="wrong-client")


class TestAuditLogAsserterEnhanced:
    """Tests for enhanced AuditLogAsserter methods."""

    @pytest.fixture
    def collector_with_audit_logs(self, tmp_path: Path) -> AuditLogCollector:
        """Create a collector with pre-populated audit logs."""
        collector = AuditLogCollector(platform_dir=tmp_path, services=["kas"])
        collector.start_time = datetime.now()

        # Add mock audit log entries
        now = datetime.now()
        test_logs = [
            # Rewrap success
            (
                now,
                json.dumps(
                    {
                        "time": "2024-01-15T10:30:00Z",
                        "level": "AUDIT",
                        "msg": "rewrap",
                        "audit": {
                            "object": {
                                "type": "key_object",
                                "id": "policy-uuid-1",
                                "attributes": {"attrs": [], "assertions": []},
                            },
                            "action": {"type": "rewrap", "result": "success"},
                            "actor": {"id": "actor-1", "attributes": []},
                            "eventMetaData": {
                                "keyID": "key-1",
                                "algorithm": "AES-256-GCM",
                            },
                            "clientInfo": {"platform": "kas"},
                            "requestId": "req-1",
                        },
                    }
                ),
                "kas",
            ),
            # Rewrap error
            (
                now,
                json.dumps(
                    {
                        "time": "2024-01-15T10:31:00Z",
                        "level": "AUDIT",
                        "msg": "rewrap",
                        "audit": {
                            "object": {
                                "type": "key_object",
                                "id": "policy-uuid-2",
                                "attributes": {"attrs": [], "assertions": []},
                            },
                            "action": {"type": "rewrap", "result": "error"},
                            "actor": {"id": "actor-2", "attributes": []},
                            "eventMetaData": {"keyID": "key-2"},
                            "clientInfo": {"platform": "kas"},
                            "requestId": "req-2",
                        },
                    }
                ),
                "kas",
            ),
            # Policy CRUD create
            (
                now,
                json.dumps(
                    {
                        "time": "2024-01-15T10:32:00Z",
                        "level": "AUDIT",
                        "msg": "policy crud",
                        "audit": {
                            "object": {"type": "namespace", "id": "ns-uuid-1"},
                            "action": {"type": "create", "result": "success"},
                            "actor": {"id": "admin", "attributes": []},
                            "clientInfo": {"platform": "policy"},
                            "requestId": "req-3",
                        },
                    }
                ),
                "platform",
            ),
        ]

        for ts, line, service in test_logs:
            collector._buffer.append(LogEntry(ts, line, service))

        return collector

    def test_assert_rewrap_success_finds_match(
        self, collector_with_audit_logs: AuditLogCollector
    ) -> None:
        """Test assert_rewrap finds matching success events."""
        asserter = AuditLogAsserter(collector_with_audit_logs)

        events = asserter.assert_rewrap_success(min_count=1, timeout=0.1)
        assert len(events) == 1
        assert events[0].action_result == "success"
        assert events[0].key_id == "key-1"

    def test_assert_rewrap_error_finds_match(
        self, collector_with_audit_logs: AuditLogCollector
    ) -> None:
        """Test assert_rewrap_error finds matching error events."""
        asserter = AuditLogAsserter(collector_with_audit_logs)

        events = asserter.assert_rewrap_error(min_count=1, timeout=0.1)
        assert len(events) == 1
        assert events[0].action_result == "error"
        assert events[0].key_id == "key-2"

    def test_assert_policy_create_finds_match(
        self, collector_with_audit_logs: AuditLogCollector
    ) -> None:
        """Test assert_policy_create finds matching create events."""
        asserter = AuditLogAsserter(collector_with_audit_logs)

        events = asserter.assert_policy_create(
            object_type="namespace", min_count=1, timeout=0.1
        )
        assert len(events) == 1
        assert events[0].action_type == "create"
        assert events[0].object_type == "namespace"

    def test_assert_rewrap_with_disabled_collector(self) -> None:
        """Test assert_rewrap returns empty list when collector disabled."""
        asserter = AuditLogAsserter(None)

        events = asserter.assert_rewrap_success(min_count=1, timeout=0.1)
        assert events == []

    def test_assert_policy_crud_with_object_id(
        self, collector_with_audit_logs: AuditLogCollector
    ) -> None:
        """Test assert_policy_crud can filter by object_id."""
        asserter = AuditLogAsserter(collector_with_audit_logs)

        events = asserter.assert_policy_create(
            object_type="namespace",
            object_id="ns-uuid-1",
            min_count=1,
            timeout=0.1,
        )
        assert len(events) == 1
        assert events[0].object_id == "ns-uuid-1"


class TestClockSkewEstimation:
    """Tests for clock skew estimation between test machine and services."""

    def test_parse_rfc3339_basic(self) -> None:
        """Test RFC3339 timestamp parsing."""
        from audit_logs import parse_rfc3339

        # Test Z suffix (UTC)
        dt = parse_rfc3339("2024-01-15T10:30:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30

        # Test with microseconds
        dt = parse_rfc3339("2024-01-15T10:30:00.123456Z")
        assert dt is not None
        assert dt.microsecond == 123456

        # Test with explicit timezone
        dt = parse_rfc3339("2024-01-15T10:30:00+00:00")
        assert dt is not None

        # Test invalid returns None
        dt = parse_rfc3339("not a timestamp")
        assert dt is None

        dt = parse_rfc3339("")
        assert dt is None

    def test_clock_skew_estimate_properties(self) -> None:
        """Test ClockSkewEstimate calculations."""
        from audit_logs import ClockSkewEstimate

        # Empty estimate
        est = ClockSkewEstimate("test-service")
        assert est.sample_count == 0
        assert est.min_skew is None
        assert est.max_skew is None
        assert est.mean_skew is None
        assert est.safe_skew_adjustment() == 0.1  # Default margin

        # Add samples
        est.samples = [0.5, 1.0, 1.5, 2.0]
        assert est.sample_count == 4
        assert est.min_skew == 0.5
        assert est.max_skew == 2.0
        assert est.mean_skew == 1.25
        assert est.median_skew == 1.25

        # Safe adjustment when test machine is ahead (positive skew)
        # Should return just the confidence margin
        assert est.safe_skew_adjustment() == 0.1

    def test_clock_skew_estimate_negative_skew(self) -> None:
        """Test ClockSkewEstimate with negative skew (service ahead)."""
        from audit_logs import ClockSkewEstimate

        est = ClockSkewEstimate("test-service")
        # Negative skew means service clock is ahead
        est.samples = [-0.3, -0.1, 0.1, 0.2]
        assert est.min_skew == -0.3

        # Safe adjustment should account for negative skew
        adj = est.safe_skew_adjustment()
        assert adj >= 0.3 + 0.1  # abs(min_skew) + margin

    def test_clock_skew_estimator_record_and_retrieve(self) -> None:
        """Test ClockSkewEstimator recording and retrieval."""

        from audit_logs import ClockSkewEstimator

        estimator = ClockSkewEstimator()

        # Record some samples
        collection_time = datetime(2024, 1, 15, 10, 30, 1, tzinfo=UTC)
        event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        estimator.record_sample("kas-alpha", collection_time, event_time)

        # Check service-specific estimate
        est = estimator.get_estimate("kas-alpha")
        assert est is not None
        assert est.sample_count == 1
        assert est.min_skew == 1.0  # 1 second difference

        # Check global estimate
        global_est = estimator.get_global_estimate()
        assert global_est.sample_count == 1

        # Add sample from different service
        estimator.record_sample(
            "platform",
            datetime(2024, 1, 15, 10, 30, 2, tzinfo=UTC),
            datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        global_est = estimator.get_global_estimate()
        assert global_est.sample_count == 2
        assert global_est.min_skew == 1.0
        assert global_est.max_skew == 2.0

    def test_parsed_audit_event_skew_properties(self) -> None:
        """Test ParsedAuditEvent skew-related properties."""
        from audit_logs import AuditLogAsserter, LogEntry

        # Create a log entry with known timestamps
        now = datetime.now()
        raw_line = json.dumps(
            {
                "time": "2024-01-15T10:30:00Z",
                "level": "AUDIT",
                "msg": "rewrap",
                "audit": {
                    "object": {"type": "key_object", "id": "test-id"},
                    "action": {"type": "rewrap", "result": "success"},
                    "actor": {"id": "test-actor"},
                    "clientInfo": {"platform": "kas"},
                    "requestId": "req-1",
                },
            }
        )
        entry = LogEntry(timestamp=now, raw_line=raw_line, service_name="kas")

        asserter = AuditLogAsserter(None)
        event = asserter.parse_audit_log(entry, record_skew=False)

        assert event is not None
        assert event.event_time is not None
        assert event.event_time.year == 2024
        assert event.collection_time == now
        assert event.observed_skew is not None

    def test_asserter_skew_methods(self, tmp_path: Path) -> None:
        """Test AuditLogAsserter skew accessor methods."""
        from audit_logs import AuditLogAsserter, AuditLogCollector

        collector = AuditLogCollector(platform_dir=tmp_path)
        collector.start_time = datetime.now()
        asserter = AuditLogAsserter(collector)

        # Initially no samples
        summary = asserter.get_skew_summary()
        assert summary == {}

        # Default adjustment
        adj = asserter.get_skew_adjustment()
        assert adj == 0.1  # Default margin

        # Skew estimator should be accessible
        assert asserter.skew_estimator is not None

    def test_asserter_skew_methods_disabled(self) -> None:
        """Test AuditLogAsserter skew methods with disabled collector."""
        from audit_logs import AuditLogAsserter

        asserter = AuditLogAsserter(None)

        assert asserter.skew_estimator is None
        assert asserter.get_skew_summary() == {}
        assert asserter.get_skew_adjustment() == 0.1

    def test_skew_recorded_on_parse(self, tmp_path: Path) -> None:
        """Test that parsing audit logs records skew samples."""
        from audit_logs import AuditLogAsserter, AuditLogCollector, LogEntry

        collector = AuditLogCollector(platform_dir=tmp_path)
        collector.start_time = datetime.now()
        asserter = AuditLogAsserter(collector)

        # Create and parse a log entry
        now = datetime.now()
        raw_line = json.dumps(
            {
                "time": "2024-01-15T10:30:00Z",
                "level": "AUDIT",
                "msg": "rewrap",
                "audit": {
                    "object": {"type": "key_object", "id": "test-id"},
                    "action": {"type": "rewrap", "result": "success"},
                    "actor": {"id": "test-actor"},
                    "clientInfo": {"platform": "kas"},
                    "requestId": "req-1",
                },
            }
        )
        entry = LogEntry(timestamp=now, raw_line=raw_line, service_name="kas-alpha")

        # Parse with skew recording enabled (default)
        event = asserter.parse_audit_log(entry)
        assert event is not None

        # Verify skew was recorded
        est = collector.skew_estimator.get_estimate("kas-alpha")
        assert est is not None
        assert est.sample_count == 1

    def test_resolve_since_applies_skew_adjustment(self, tmp_path: Path) -> None:
        """Test that _resolve_since applies clock skew adjustment."""

        from audit_logs import AuditLogAsserter, AuditLogCollector

        collector = AuditLogCollector(platform_dir=tmp_path)
        collector.start_time = datetime.now()
        asserter = AuditLogAsserter(collector)

        # Record a sample with negative skew (service clock ahead)

        collection_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        event_time = datetime(2024, 1, 15, 10, 30, 1, tzinfo=UTC)  # 1s ahead
        collector.skew_estimator.record_sample("kas", collection_time, event_time)

        # The skew is -1.0 (service ahead), so adjustment should be ~1.1s
        adj = asserter.get_skew_adjustment()
        assert adj >= 1.0

        # Create a mark
        mark = collector.mark("test")
        mark_time = collector.get_mark(mark)
        assert mark_time is not None

        # Resolve with adjustment
        resolved = asserter._resolve_since(mark, apply_skew_adjustment=True)
        assert resolved is not None
        assert resolved < mark_time  # Should be earlier due to adjustment

        # Resolve without adjustment
        resolved_no_adj = asserter._resolve_since(mark, apply_skew_adjustment=False)
        assert resolved_no_adj is not None
        assert resolved_no_adj == mark_time
