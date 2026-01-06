"""Obligation and subject condition set fixtures.

This module contains fixtures for testing TDF obligations:
- Subject condition sets (SCS) for client authorization
- Obligation definitions and values
- Obligation triggers (scoped and unscoped)
"""

import pytest
import abac
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(scope="module")
def otdf_client_scs(otdfctl: OpentdfCommandLineTool) -> abac.SubjectConditionSet:
    """
    Creates a standard subject condition set for OpenTDF clients.
    This condition set matches client IDs 'opentdf' or 'opentdf-sdk'.

    Returns:
        abac.SubjectConditionSet: The created subject condition set
    """
    sc: abac.SubjectConditionSet = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    return sc


def _obligation_setup_helper(
    otdfctl: OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
    attr_name: str,
    attr_rule: abac.AttributeRule,
    attr_values: list[str],
    obligation_def_name: str,
    obligation_value_name: str,
    scs: abac.SubjectConditionSet | None,
    trigger_client_id: str | None,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """Shared helper for obligation test setup.

    Creates attribute and optional SCS mapping, obligation definition with a single value,
    and an obligation trigger (optionally scoped to a client id).
    """
    # Attribute
    attr = otdfctl.attribute_create(
        name=attr_name,
        namespace=temporary_namespace,
        t=attr_rule,
        values=attr_values,
    )
    assert attr is not None
    assert attr.fqn == f"{temporary_namespace.fqn}/attr/{attr.name}"
    assert attr.values is not None and len(attr.values) == 1
    attr_value = attr.values[0]
    assert (
        attr_value.fqn
        == f"{temporary_namespace.fqn}/attr/{attr.name}/value/{attr_value.value}"
    )

    # Optional SCS mapping
    if scs is not None:
        sm = otdfctl.scs_map(scs, attr_value)
        assert sm is not None

    # Obligation and value
    obligation = otdfctl.obligation_def_create(
        name=obligation_def_name,
        namespace=temporary_namespace,
        value=[obligation_value_name],
    )
    assert obligation is not None
    if obligation.fqn is None:
        assert obligation.name is not None
        assert obligation.name == obligation_def_name
        obligation.fqn = f"{temporary_namespace.fqn}/obl/{obligation.name}"
    else:
        assert obligation.fqn == f"{temporary_namespace.fqn}/obl/{obligation_def_name}"

    assert obligation.values is not None and len(obligation.values) == 1

    oval = obligation.values[0]
    if oval.fqn is None:
        assert oval.value is not None
        assert oval.value == obligation_value_name
        oval.fqn = f"{obligation.fqn}/value/{oval.value}"
    else:
        assert (
            oval.fqn
            == f"{temporary_namespace.fqn}/obl/{obligation_def_name}/value/{obligation_value_name}"
        )

    # Trigger
    _ = otdfctl.obligation_triggers_create(oval, "read", attr_value, trigger_client_id)
    assert _ is not None

    return attr, oval


@pytest.fixture(scope="module")
def obligation_setup_no_scs_unscoped_trigger(
    otdfctl: OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute and obligation value.

    Creates:
    - A namespace for obligations testing
    - An attribute with a "alpha" value
    - An obligation definition with a required value
    - An obligation value instance

    Note: Subject mapping is intentionally omitted for testing scenarios
    where obligations should prevent access.

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """
    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test",
        attr_rule=abac.AttributeRule.ALL_OF,
        attr_values=["alpha"],
        obligation_def_name="test_obligation",
        obligation_value_name="watermark",
        scs=None,
        trigger_client_id=None,
    )


@pytest.fixture(scope="module")
def obligation_setup_scs_unscoped_trigger(
    otdfctl: OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute, obligation value, and subject condition set.

    Creates:
    - A namespace for obligations testing
    - An attribute with a "beta" value
    - An obligation definition with a required value
    - An obligation value instance
    - Maps the attribute value to the provided subject condition set

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """

    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test-scs",
        attr_rule=abac.AttributeRule.ANY_OF,
        attr_values=["beta"],
        obligation_def_name="test_obligation_scs",
        obligation_value_name="geofence",
        scs=otdf_client_scs,
        trigger_client_id=None,
    )


@pytest.fixture(scope="module")
def obligation_setup_scs_scoped_trigger(
    otdfctl: OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute, obligation value, and subject condition set.
    The obligation trigger will be scoped to the specified client ID.

    Args:
        client_id: The client ID to scope the obligation trigger to (defaults to "opentdf")

    Creates:
    - A namespace for obligations testing
    - An attribute with a "gamma" value
    - An obligation definition with a required value
    - An obligation value instance
    - Maps the attribute value to the provided subject condition set
    - Scopes a trigger to the specified client ID

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """
    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test-scs-scoped-otdf-client",
        attr_rule=abac.AttributeRule.ANY_OF,
        attr_values=["gamma"],
        obligation_def_name="obligation-test-scs-scoped-otdf-client",
        obligation_value_name="prevent-download",
        scs=otdf_client_scs,
        trigger_client_id="opentdf",
    )


@pytest.fixture(scope="module")
def obligation_setup_scs_scoped_trigger_different_client(
    otdfctl: OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute, obligation value, and subject condition set.
    The obligation trigger will be scoped to a different client ID than the one in the subject condition set.

    Args:
        client_id: The client ID to scope the obligation trigger to (defaults to "different-client")

    Creates:
    - A namespace for obligations testing
    - An attribute with a "delta" value
    - An obligation definition with a required value
    - An obligation value instance
    - Maps the attribute value to the provided subject condition set
    - Scopes a trigger to the specified different client ID

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """
    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test-scs-scoped-different-client",
        attr_rule=abac.AttributeRule.ANY_OF,
        attr_values=["delta"],
        obligation_def_name="obligation-test-scs-scoped-different-client",
        obligation_value_name="prevent-download",
        scs=otdf_client_scs,
        trigger_client_id="different-client",
    )
