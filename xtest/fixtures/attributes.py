"""Attribute and attribute value fixtures for ABAC testing.

This module contains fixtures for setting up various attribute configurations:
- Single/multi-KAS grants
- OR (ANY_OF) and AND (ALL_OF) rule types
- HIERARCHY rule types
- Attribute-level, value-level, and namespace-level grants
- Mixed grant scenarios (attr + value, ns + value)
"""

import random
import string

import pytest

import abac
import tdfs
from otdfctl import OpentdfCommandLineTool


def create_temp_namesapce(otdfctl: OpentdfCommandLineTool):
    """Create a temporary namespace with a random name."""
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    return ns


@pytest.fixture(scope="module")
def temporary_namespace(otdfctl: OpentdfCommandLineTool):
    """Create a temporary namespace for test attributes."""
    try:
        return create_temp_namesapce(otdfctl)
    except AssertionError as e:
        pytest.skip(f"Failed to create temporary namespace: {e}")


# Single KAS grant fixtures
@pytest.fixture(scope="module")
def attribute_single_kas_grant(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_alpha: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    """Attribute with single KAS grant on value 'a'."""
    pfs = tdfs.PlatformFeatureSet()
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letter", abac.AttributeRule.ANY_OF, ["a"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "a"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "a"
    # Now assign it to the current KAS
    if "key_management" not in pfs.features:
        otdfctl.grant_assign_value(kas_entry_alpha, alpha)
    else:
        kas_key = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key, alpha)
    return anyof


# Two KAS grant fixtures (OR/AND)
@pytest.fixture(scope="module")
def attribute_two_kas_grant_or(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_alpha: abac.KasEntry,
    kas_entry_beta: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    """Attribute with ANY_OF rule and two KAS grants (alpha on kas1, beta on kas2)."""
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letra", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    alpha, beta = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_alpha, alpha)
        otdfctl.grant_assign_value(kas_entry_beta, beta)
    else:
        kas_key_alph = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_alph, alpha)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_beta, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_and(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_alpha: abac.KasEntry,
    kas_entry_beta: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    """Attribute with ALL_OF rule and two KAS grants (alef on kas1, bet on kas2)."""
    allof = otdfctl.attribute_create(
        temporary_namespace, "ot", abac.AttributeRule.ALL_OF, ["alef", "bet", "gimmel"]
    )
    assert allof.values
    alef, bet, gimmel = allof.values
    assert alef.value == "alef"
    assert bet.value == "bet"
    assert gimmel.value == "gimmel"

    # Then assign it to all clientIds = opentdf-sdk
    sm1 = otdfctl.scs_map(otdf_client_scs, alef)
    assert sm1.attribute_value.value == "alef"
    sm2 = otdfctl.scs_map(otdf_client_scs, bet)
    assert sm2.attribute_value.value == "bet"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_alpha, alef)
        otdfctl.grant_assign_value(kas_entry_beta, bet)
    else:
        kas_key_alpha = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_alpha, alef)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_beta, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, bet)

    return allof


# Attribute-level KAS grant
@pytest.fixture(scope="module")
def one_attribute_attr_kas_grant(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_gamma: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Attribute with attribute-level KAS grant."""
    anyof = otdfctl.attribute_create(
        temporary_namespace, "attrgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_gamma, anyof)
    else:
        kas_key_alpha = otdfctl.kas_registry_create_public_key_only(
            kas_entry_gamma, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_alpha, anyof)
    return anyof


# Attribute rule type fixtures
@pytest.fixture(scope="module")
def attribute_with_or_type(
    otdfctl: OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with OR type and assign it to a KAS entry.

    The attribute will have a rule of ANY_OF with values "alpha" and "beta".
    The user only has permission to access the attribute if they have the "alpha" value.
    Files with both will be accessible to the user, but files with only "beta" will not.
    """
    anyof = otdfctl.attribute_create(
        temporary_namespace, "or", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Assign or:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    return anyof


@pytest.fixture(scope="module")
def attribute_with_and_type(
    otdfctl: OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with AND type and assign it to a KAS entry.

    The attribute will have a rule of ALL_OF with values "alpha" and "beta".
    The user only has alpha assigned, so will be able to access files that do not have beta applied.
    """
    allof = otdfctl.attribute_create(
        temporary_namespace, "and", abac.AttributeRule.ALL_OF, ["alpha", "beta"]
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Assign and:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    return allof


@pytest.fixture(scope="module")
def attribute_with_hierarchy_type(
    otdfctl: OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with HIERARCHY type and assign it to a KAS entry.

    The attribute will have a rule of HIERARCHY with values "alpha", "beta" and "gamma".
    The user only has "beta" assigned, so will be able to access files that have "gamma" or "beta" but not "alpha".
    """
    hierarchy_attr = otdfctl.attribute_create(
        temporary_namespace,
        "hierarchy",
        abac.AttributeRule.HIERARCHY,
        ["alpha", "beta", "gamma"],
    )
    assert hierarchy_attr.values
    (alpha, beta, gamma) = hierarchy_attr.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"
    assert gamma.value == "gamma"

    # Assign hierarchical:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm.attribute_value.value == "beta"

    return hierarchy_attr


# Mixed grant scenarios (attribute + value)
@pytest.fixture(scope="module")
def attr_and_value_kas_grants_or(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_gamma: abac.KasEntry,
    kas_entry_alpha: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Attribute with ANY_OF rule and mixed attr+value KAS grants."""
    anyof = otdfctl.attribute_create(
        temporary_namespace,
        "attrorvalgrant",
        abac.AttributeRule.ANY_OF,
        ["alpha", "beta"],
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_gamma, anyof)
        otdfctl.grant_assign_value(kas_entry_alpha, beta)
    else:
        kas_key_attr = otdfctl.kas_registry_create_public_key_only(
            kas_entry_gamma, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_attr, anyof)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

    return anyof


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_and(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_gamma: abac.KasEntry,
    kas_entry_alpha: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Attribute with ALL_OF rule and mixed attr+value KAS grants."""
    allof = otdfctl.attribute_create(
        temporary_namespace,
        "attrandvalgrant",
        abac.AttributeRule.ALL_OF,
        ["alpha", "beta"],
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm2.attribute_value.value == "beta"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_gamma, allof)
        otdfctl.grant_assign_value(kas_entry_alpha, beta)
    else:
        kas_key_attr = otdfctl.kas_registry_create_public_key_only(
            kas_entry_gamma, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_attr, allof)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

    return allof


# Namespace-level KAS grant
@pytest.fixture(scope="module")
def one_attribute_ns_kas_grant(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_delta: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Attribute with namespace-level KAS grant."""
    anyof = otdfctl.attribute_create(
        temporary_namespace, "nsgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_ns(kas_entry_delta, temporary_namespace)
    else:
        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_delta, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temporary_namespace)

    return anyof


# Mixed grant scenarios (namespace + value)
@pytest.fixture(scope="module")
def ns_and_value_kas_grants_or(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_alpha: abac.KasEntry,
    kas_entry_delta: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
) -> abac.Attribute:
    """Attribute with ANY_OF rule and mixed ns+value KAS grants."""
    temp_namespace = create_temp_namesapce(otdfctl)
    anyof = otdfctl.attribute_create(
        temp_namespace,
        "nsorvalgrant",
        abac.AttributeRule.ANY_OF,
        ["alpha", "beta"],
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_alpha, beta)
        otdfctl.grant_assign_ns(kas_entry_delta, temp_namespace)
    else:
        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_delta, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temp_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_and(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_alpha: abac.KasEntry,
    kas_entry_delta: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
) -> abac.Attribute:
    """Attribute with ALL_OF rule and mixed ns+value KAS grants."""
    temp_namespace = create_temp_namesapce(otdfctl)
    allof = otdfctl.attribute_create(
        temp_namespace,
        "nsandvalgrant",
        abac.AttributeRule.ALL_OF,
        ["alpha", "beta"],
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm2.attribute_value.value == "beta"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_alpha, beta)
        otdfctl.grant_assign_ns(kas_entry_delta, temp_namespace)
    else:
        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_alpha, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_delta, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temp_namespace)

    return allof


# Default KAS RSA key fixture for tests that need explicit RSA wrapping
@pytest.fixture(scope="module")
def attribute_default_rsa(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Attribute with RSA key mapping on default KAS.

    Use this fixture when tests need to ensure RSA wrapping is used,
    regardless of what base_key may be configured on the platform.
    This prevents test order sensitivity when base_key tests run.
    """
    anyof = otdfctl.attribute_create(
        temporary_namespace, "defaultrsa", abac.AttributeRule.ANY_OF, ["wrapped"]
    )
    assert anyof.values
    (wrapped,) = anyof.values
    assert wrapped.value == "wrapped"

    # Assign to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, wrapped)
    assert sm.attribute_value.value == "wrapped"

    # Assign RSA key on default KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_default, wrapped)
    else:
        kas_key = otdfctl.kas_registry_create_public_key_only(
            kas_entry_default, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key, wrapped)

    return anyof
