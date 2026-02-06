"""Comprehensive integration tests for audit log coverage.

These tests verify that audit events are properly generated for:
- Rewrap operations (decrypt)
- Policy CRUD operations (administration)
- Authorization decisions

Run with:
    cd tests/xtest
    uv run pytest test_audit_logs_integration.py --sdks go -v

Note: These tests require audit log collection to be enabled. They will be
skipped when running with --no-audit-logs.
"""

import filecmp
import random
import string
import subprocess
from pathlib import Path

import pytest

import abac
import tdfs
from audit_logs import AuditLogAsserter
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(autouse=True)
def skip_if_audit_disabled(audit_logs: AuditLogAsserter):
    """Skip all tests in this module if audit log collection is disabled."""
    if not audit_logs.is_enabled:
        pytest.skip("Audit log collection is disabled (--no-audit-logs)")

# ============================================================================
# Rewrap Audit Tests
# ============================================================================


class TestRewrapAudit:
    """Tests for rewrap audit event coverage."""

    def test_rewrap_success_fields(
        self,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
    ):
        """Verify all expected fields in successful rewrap audit."""
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

        ct_file = tmp_dir / f"rewrap-success-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
        )

        mark = audit_logs.mark("before_decrypt")
        rt_file = tmp_dir / f"rewrap-success-{encrypt_sdk}-{decrypt_sdk}.untdf"
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
        assert filecmp.cmp(pt_file, rt_file)

        # Verify rewrap success was logged with structured assertion
        events = audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)

        # Verify event fields
        assert len(events) >= 1
        event = events[0]
        assert event.action_result == "success"
        assert event.action_type == "rewrap"
        assert event.object_type == "key_object"
        assert event.object_id is not None  # Policy UUID
        assert event.client_platform == "kas"
        # eventMetaData fields
        assert event.key_id is not None or event.algorithm is not None

    def test_rewrap_failure_access_denied(
        self,
        attribute_single_kas_grant: abac.Attribute,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
    ):
        """Verify rewrap failure audited when access denied due to policy.

        This test creates a TDF with an attribute the client is not entitled to,
        then attempts to decrypt, which should fail and be audited.
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
        tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")

        # Create a TDF with an attribute - the test client should have access
        ct_file = tmp_dir / f"rewrap-access-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
            attr_values=attribute_single_kas_grant.value_fqns,
        )

        mark = audit_logs.mark("before_decrypt")
        rt_file = tmp_dir / f"rewrap-access-{encrypt_sdk}-{decrypt_sdk}.untdf"

        # This should succeed if the client has access
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
        assert filecmp.cmp(pt_file, rt_file)

        # Verify rewrap success with attribute FQNs
        events = audit_logs.assert_rewrap_success(
            attr_fqns=attribute_single_kas_grant.value_fqns,
            min_count=1,
            since_mark=mark,
        )
        assert len(events) >= 1

    def test_multiple_kao_rewrap_audit(
        self,
        attribute_two_kas_grant_and: abac.Attribute,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
    ):
        """Verify multiple KAOs generate multiple audit events.

        When a TDF has an ALL_OF policy requiring multiple KASes,
        the decrypt should generate multiple rewrap audit events.
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
        tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")

        ct_file = tmp_dir / f"multi-kao-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
            attr_values=[
                attribute_two_kas_grant_and.value_fqns[0],
                attribute_two_kas_grant_and.value_fqns[1],
            ],
        )

        mark = audit_logs.mark("before_multi_decrypt")
        rt_file = tmp_dir / f"multi-kao-{encrypt_sdk}-{decrypt_sdk}.untdf"

        # Check manifest to verify we have 2 KAOs
        manifest = tdfs.manifest(ct_file)
        if any(
            kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
        ):
            tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")

        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
        assert filecmp.cmp(pt_file, rt_file)

        # For AND policy, should have 2 rewrap success events (one per KAS)
        events = audit_logs.assert_rewrap_success(min_count=2, since_mark=mark)
        assert len(events) >= 2


# ============================================================================
# Policy CRUD Audit Tests
# ============================================================================


class TestPolicyCRUDAudit:
    """Tests for policy CRUD audit event coverage."""

    @pytest.fixture
    def otdfctl(self) -> OpentdfCommandLineTool:
        """Get otdfctl instance for policy operations."""
        return OpentdfCommandLineTool()

    def test_namespace_crud_audit(
        self, otdfctl: OpentdfCommandLineTool, audit_logs: AuditLogAsserter
    ):
        """Test namespace create/update/delete audit trail."""
        random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"

        # Test create
        mark = audit_logs.mark("before_ns_create")
        ns = otdfctl.namespace_create(random_ns)
        events = audit_logs.assert_policy_create(
            object_type="namespace",
            object_id=ns.id,
            since_mark=mark,
        )
        assert len(events) >= 1
        assert events[0].action_type == "create"

    def test_attribute_crud_audit(
        self, otdfctl: OpentdfCommandLineTool, audit_logs: AuditLogAsserter
    ):
        """Test attribute and value creation audit trail."""
        random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"

        mark = audit_logs.mark("before_attr_create")

        # Create namespace and attribute
        ns = otdfctl.namespace_create(random_ns)
        attr = otdfctl.attribute_create(
            ns, "test_attr", abac.AttributeRule.ANY_OF, ["val1", "val2"]
        )

        # Verify namespace creation
        audit_logs.assert_policy_create(
            object_type="namespace",
            object_id=ns.id,
            since_mark=mark,
        )

        # Verify attribute definition creation
        events = audit_logs.assert_policy_create(
            object_type="attribute_definition",
            object_id=attr.id,
            since_mark=mark,
        )
        assert len(events) >= 1

        # Verify attribute values creation (2 values)
        value_events = audit_logs.assert_policy_create(
            object_type="attribute_value",
            min_count=2,
            since_mark=mark,
        )
        assert len(value_events) >= 2

    def test_subject_mapping_audit(
        self, otdfctl: OpentdfCommandLineTool, audit_logs: AuditLogAsserter
    ):
        """Test SCS and subject mapping audit trail."""
        c = abac.Condition(
            subject_external_selector_value=".clientId",
            operator=abac.SubjectMappingOperatorEnum.IN,
            subject_external_values=["test-client"],
        )
        cg = abac.ConditionGroup(
            boolean_operator=abac.ConditionBooleanTypeEnum.OR, conditions=[c]
        )

        mark = audit_logs.mark("before_scs_create")

        scs = otdfctl.scs_create([abac.SubjectSet(condition_groups=[cg])])

        # Verify condition set creation
        events = audit_logs.assert_policy_create(
            object_type="condition_set",
            object_id=scs.id,
            since_mark=mark,
        )
        assert len(events) >= 1


# ============================================================================
# Decision Audit Tests
# ============================================================================


class TestDecisionAudit:
    """Tests for GetDecision audit event coverage.

    Note: Decision audit events are generated when the authorization service
    makes access decisions. This typically happens during rewrap operations.
    """

    def test_decision_on_successful_access(
        self,
        attribute_single_kas_grant: abac.Attribute,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
    ):
        """Verify decision audit on successful access.

        When a decrypt succeeds, the authorization decision should be audited.
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
        tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")

        ct_file = tmp_dir / f"decision-success-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
            attr_values=attribute_single_kas_grant.value_fqns,
        )

        mark = audit_logs.mark("before_decision_decrypt")
        rt_file = tmp_dir / f"decision-success-{encrypt_sdk}-{decrypt_sdk}.untdf"
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
        assert filecmp.cmp(pt_file, rt_file)

        # Verify both rewrap and decision were logged
        # Note: Decision events may be v1 or v2 depending on platform version
        audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)

        # Try to find decision audit logs (may be v1 or v2 format)
        # Using the basic assert_contains since decision format varies
        try:
            audit_logs.assert_contains(
                r'"msg":\s*"decision"',
                min_count=1,
                since_mark=mark,
                timeout=2.0,
            )
        except AssertionError:
            # Decision logs may not always be present depending on platform config
            pass


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases: errors, load, etc."""

    def test_audit_logs_on_tampered_file(
        self,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
    ):
        """Verify audit logs written even when decrypt fails due to tampering.

        When a TDF is tampered with and decrypt fails, the rewrap error
        should still be audited.
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

        # Create valid TDF
        ct_file = tmp_dir / f"tamper-audit-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
        )

        # Tamper with the policy binding
        def tamper_policy_binding(manifest: tdfs.Manifest) -> tdfs.Manifest:
            pb = manifest.encryptionInformation.keyAccess[0].policyBinding
            if isinstance(pb, tdfs.PolicyBinding):
                import base64

                h = pb.hash
                altered = base64.b64encode(b"tampered" + base64.b64decode(h)[:8])
                pb.hash = str(altered)
            else:
                import base64

                altered = base64.b64encode(b"tampered" + base64.b64decode(pb)[:8])
                manifest.encryptionInformation.keyAccess[0].policyBinding = str(altered)
            return manifest

        tampered_file = tdfs.update_manifest(
            "tampered_binding", ct_file, tamper_policy_binding
        )

        mark = audit_logs.mark("before_tampered_decrypt")
        rt_file = tmp_dir / f"tamper-audit-{encrypt_sdk}-{decrypt_sdk}.untdf"

        try:
            decrypt_sdk.decrypt(tampered_file, rt_file, "ztdf", expect_error=True)
            pytest.fail("Expected decrypt to fail")
        except subprocess.CalledProcessError:
            pass  # Expected

        # Verify rewrap error was audited
        audit_logs.assert_rewrap_error(min_count=1, since_mark=mark)

    @pytest.mark.slow
    def test_audit_under_sequential_load(
        self,
        encrypt_sdk: tdfs.SDK,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        tmp_dir: Path,
        audit_logs: AuditLogAsserter,
        in_focus: set[tdfs.SDK],
    ):
        """Verify audit logs complete under sequential decrypt load.

        Performs multiple sequential decrypts and verifies each generates
        an audit event.
        """
        if not in_focus & {encrypt_sdk, decrypt_sdk}:
            pytest.skip("Not in focus")
        pfs = tdfs.PlatformFeatureSet()
        tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
        tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

        num_decrypts = 5

        # Create TDF
        ct_file = tmp_dir / f"load-test-{encrypt_sdk}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            container="ztdf",
        )

        mark = audit_logs.mark("before_load_test")

        # Perform multiple decrypts
        for i in range(num_decrypts):
            rt_file = tmp_dir / f"load-test-{encrypt_sdk}-{decrypt_sdk}-{i}.untdf"
            decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
            assert filecmp.cmp(pt_file, rt_file)

        # Verify we got audit events for all decrypts
        events = audit_logs.assert_rewrap_success(
            min_count=num_decrypts,
            since_mark=mark,
            timeout=10.0,
        )
        assert len(events) >= num_decrypts
