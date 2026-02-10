import random
import string

import abac
from audit_logs import AuditLogAsserter
from otdfctl import OpentdfCommandLineTool

otdfctl = OpentdfCommandLineTool()


def test_namespaces_list() -> None:
    ns = otdfctl.namespace_list()
    assert len(ns) >= 4


def test_namespace_create(audit_logs: AuditLogAsserter) -> None:
    """Test namespace creation and verify audit log."""
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"

    # Mark timestamp before create for audit log correlation
    mark = audit_logs.mark("before_ns_create")

    ns = otdfctl.namespace_create(random_ns)
    assert ns.id is not None

    # Verify namespace creation was logged
    audit_logs.assert_policy_create(
        object_type="namespace",
        object_id=ns.id,
        since_mark=mark,
    )


def test_attribute_create(audit_logs: AuditLogAsserter) -> None:
    """Test attribute creation and verify audit logs for namespace and attributes."""
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"

    # Mark timestamp before creates
    mark = audit_logs.mark("before_attr_create")

    ns = otdfctl.namespace_create(random_ns)
    anyof = otdfctl.attribute_create(
        ns, "free", abac.AttributeRule.ANY_OF, ["1", "2", "3"]
    )
    allof = otdfctl.attribute_create(
        ns, "strict", abac.AttributeRule.ALL_OF, ["1", "2", "3"]
    )
    assert anyof != allof

    # Verify audit logs for policy operations
    # Namespace creation
    audit_logs.assert_policy_create(
        object_type="namespace",
        object_id=ns.id,
        since_mark=mark,
    )
    # Attribute definition creations (2 attributes, values embedded in each event)
    attr_events = audit_logs.assert_policy_create(
        object_type="attribute_definition",
        min_count=2,
        since_mark=mark,
    )
    # Platform embeds created values in the attribute_definition event.
    # With xdist, other workers may create attributes concurrently, so use >=.
    total_values = sum(
        len(e.original.get("values", [])) for e in attr_events if e.original
    )
    assert total_values >= 6, (
        f"Expected at least 6 values in attribute_definition events. Got {total_values}"
    )


def test_scs_create(audit_logs: AuditLogAsserter) -> None:
    """Test subject condition set creation and verify audit log."""
    c = abac.Condition(
        subject_external_selector_value=".clientId",
        operator=abac.SubjectMappingOperatorEnum.IN,
        subject_external_values=["opentdf-sdk"],
    )
    cg = abac.ConditionGroup(
        boolean_operator=abac.ConditionBooleanTypeEnum.OR, conditions=[c]
    )

    # Mark timestamp before create
    mark = audit_logs.mark("before_scs_create")

    sc = otdfctl.scs_create(
        [abac.SubjectSet(condition_groups=[cg])],
    )
    assert len(sc.subject_sets) == 1

    # Verify condition set creation was logged
    audit_logs.assert_policy_create(
        object_type="condition_set",
        object_id=sc.id,
        since_mark=mark,
    )
