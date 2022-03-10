"""Test the AdjudicatorV2 helper functions."""

import pytest

from tdf3_kas_core.models import AttributeValue
from tdf3_kas_core.models import AttributePolicy

from tdf3_kas_core.errors import AuthorizationError

from .decision_functions_v2 import all_of_decision
from .decision_functions_v2 import any_of_decision
from .decision_functions_v2 import hierarchy_decision

from tdf3_kas_core.models import HIERARCHY

from tdf3_kas_core.models import Claims

def compose_jwt(primary_ent, entity_bundles):
    return {
        "exp": 1638810866,
        "iat": 1638810566,
        "jti": "64770e73-b670-4a4d-9ad0-a0f2fd61a0b1",
        "iss": "http://keycloak-http/auth/realms/tdf-pki/realms/tdf-pki",
        "aud": [
            "realm-management",
            "account"
        ],
        "sub": primary_subj,
        "typ": "Bearer",
        "azp": "tdf-client",
        "session_state": "e07edbee-e0ae-4f1d-b5c4-8f4273a58a80",
        "acr": "1",
        "allowed-origins": [
            "http://dcr-keycloak:80"
        ],
        "realm_access": {
            "roles": [
            "default-roles-tdf-pki",
            "offline_access",
            "uma_authorization"
            ]
        },
        "resource_access": {
            "realm-management": {
            "roles": [
                "view-users",
                "view-clients",
                "query-clients",
                "query-groups",
                "query-users"
            ]
            },
            "account": {
            "roles": [
                "manage-account",
                "manage-account-links",
                "view-profile"
            ]
            }
        },
        "scope": "profile email",
        "sid": "e07edbee-e0ae-4f1d-b5c4-8f4273a58a80",
        "email_verified": "false",
        "tdf_claims": {
            "entitlements": entity_bundles,
        "client_public_signing_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwGPf6H2cuq8ZfqwnBlKY\nFi5Jk9fzEuXoeyidKjCHE2WRPx7W7zVjaulrrRKBL1J0PfnFaG1hFZPxnJXaqq5S\nnTfloZA+klgUALNGpklnwWFOUCylT4mq9bjQwt44grdgaXh7qhFjARCtIVz8BxeR\nowXYEd7+WRlgcRRk7FWuCAZYsWgiYoS3J1fWs/z8SMJrB47TtNmHjXqZiTac5mpt\nOyVs4l9ZBfpdT7Arlibi7E3V9H7NeX4sEPMm3lAVR9YHP2EaMvsUXl6XIotrW/VJ\nttMiuXwfOb46Xn9DQEvL/kFgYDx4nM16WPrYZP0T7+CXzuLUUCeP7/sj2xSvWmNZ\nJQIDAQAB\n-----END PUBLIC KEY-----\n"  },
        "preferred_username": primary_ent
    }

def entity_with_attrs(ent_id, ent_attrs):
    format_attrs = []

    for attr in ent_attrs:
        format_attrs.append({"attribute": attr})


    return {
        "entity_identifier": ent_id,
        "entity_attributes": format_attrs
      }
# ========== ALL OF ===================

def test_all_of_decision_succeed_all_entity_have_all_claims():
    """All of the entities have the correct attribute - so AllOf should succeed"""

    sub1 = entity_with_attrs("bubb", [
        "https://agency1.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/Env/value/CleanRoom"
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
    ])

    agency2ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency2")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([agency2ConflictAttr])

    assert all_of_decision(data_values, claims) is True

def test_all_of_decision_fail_one_entity_partially_lacking_claims():
    """2 of the 3 entities lack AllOf the correct attributes - so AllOf should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://agency1.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/Env/value/CleanRoom"
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
    ])

    agency1ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency1")
    agency2ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency2")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([agency1ConflictAttr, agency2ConflictAttr])

    with pytest.raises(AuthorizationError):
        all_of_decision(data_values, claims)

def test_all_of_decision_fail_one_entity_lacking_claims():
    """2 of the 3 entity completely lack the correct attribute - so AllOf should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://agency1.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/Env/value/CleanRoom"
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
    ])

    agency2ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency2")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([agency2ConflictAttr])

    with pytest.raises(AuthorizationError):
        all_of_decision(data_values, claims)

def test_all_of_decision_succeed_empty_data_values():
    """Data value attrs empty - should succeed"""

    sub1 = entity_with_attrs("bubb", [
        "https://agency1.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/Env/value/CleanRoom"
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
    ])

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([])

    assert all_of_decision(data_values, claims) is True

def test_all_of_decision_fails_empty_entity_values():
    """Entity entitlements empty - should fail"""

    ent1 = entity_with_attrs("bubb", [
    ])

    ent2 = entity_with_attrs("rubb", [
    ])

    ent3 = entity_with_attrs("woowoo", [
    ])

    decodedJwt = compose_jwt("bubb", [ent1, ent2, ent3])
    agency2ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency2")
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([agency2ConflictAttr])

    with pytest.raises(AuthorizationError):
        all_of_decision(data_values, claims)

# ========== ANY OF ===================

def test_any_of_decision_succeed_union_of_entities_have_all_claims():
    """The union of attributes provided by the entities satisfies all data attr requirements - so Anyof should succeed"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    agency1ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency1")
    agency2ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency2")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([agency1ConflictAttr, agency2ConflictAttr])

    assert any_of_decision(data_values, claims) is True

def test_any_of_decision_succeed_union_of_entities_have_all_claims():
    """The union of attributes provided by the entities satisfies all data attr requirements - so Anyof should succeed"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/conflictReport/value/agency2",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    agency1ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency1")
    agency2ConflictAttr = AttributeValue("https://example.com/attr/conflictReport/value/agency2")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([agency1ConflictAttr, agency2ConflictAttr])

    assert any_of_decision(data_values, claims) is True

def test_any_of_decision_succeed_union_of_entities_have_all_claims_disjoint_namespaces():
    """The union of attributes provided by the entities satisfies all data attr requirements - so Anyof should succeed"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRZ",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRX",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRY",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    PRXattr = AttributeValue("https://example.com/attr/COI/value/PRX")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([PRXattr])

    assert any_of_decision(data_values, claims) is True

def test_any_of_decision_fail_union_of_entities_have_missing_claims():
    """The union of attributes provided by the entities does not satisfy all data attr requirements - so Anyof should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRZ",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRQ",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/Classification/value/S",
        "https://example.com/attr/COI/value/PRY",
        "https://example.com/attr/Env/value/CleanRoom",
        "https://agency1.com/attr/investigations/value/access",
        "https://agency2.com/attr/investigations/value/access",
        "https://example.com/attr/conflictReport/value/agency1",
        "https://example.com/attr/conflictReport/value/agency2"
    ])

    PRXattr = AttributeValue("https://example.com/attr/COI/value/PRX")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([PRXattr])

    with pytest.raises(AuthorizationError):
        all_of_decision(data_values, claims)


def test_any_of_decision_fail_union_of_entities_have_no_claims():
    """Entities have no claims but data has attributes - so Anyof should fail"""

    sub1 = entity_with_attrs("bubb", [
    ])

    sub2 = entity_with_attrs("rubb", [
    ])

    sub3 = entity_with_attrs("woowoo", [
    ])

    PRXattr = AttributeValue("https://example.com/attr/COI/value/PRX")

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([PRXattr])

    with pytest.raises(AuthorizationError):
        all_of_decision(data_values, claims)

def test_any_of_decision_succeed_union_of_data_has_no_attrs():
    """Entities have no claims but data has no attributes - so Anyof should succeed"""

    sub1 = entity_with_attrs("bubb", [
    ])

    sub2 = entity_with_attrs("rubb", [
    ])

    sub3 = entity_with_attrs("woowoo", [
    ])

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([])

    assert all_of_decision(data_values, claims) is True


# # ========== HIERARCHY ===================

def test_hierarchy_decision_fail_union_of_entity_attrs_not_meet_threshold():
    """None of the entites have a high enough rank - so Hierarchy should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/classif/value/U",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/classif/value/C",
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/classif/value/S",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/TS")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([classif_attr])

    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, claims, classif_policy.options["order"])

def test_hierarchy_decision_fail_union_of_entity_attrs_use_lowest_rank():
    """Some of the entities have a high enough rank - but the lowest entity rank in the set is what we use to compare, so Hierarchy should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/classif/value/U",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/classif/value/C",
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/C")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([classif_attr])

    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, claims, classif_policy.options["order"])

def test_hierarchy_decision_succeed_union_of_entity_attrs_use_lowest_rank():
    """The lowest entity rank in the set meets the rank requirement, so Hierarchy should succeed"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/classif/value/C",
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/C")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([classif_attr])

    assert hierarchy_decision(data_values, claims, classif_policy.options["order"]) is True


def test_hierarchy_decision_fail_union_of_entity_attrs_use_wrong_ranks():
    """Entities have invalid hierarchy values - so Hierarchy should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/classif/value/B",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/classif/value/Q",
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/classif/value/TEP",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/C")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([classif_attr])

    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, claims, classif_policy.options["order"])

def test_hierarchy_decision_fail_union_of_entity_attrs_use_wrong_data_ranks():
    """Data attrib has invalid hierarchy value - so Hierarchy should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/classif/value/C",
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/Q")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([classif_attr])

    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, claims, classif_policy.options["order"])

def test_hierarchy_decision_fail_no_entity_claims():
    """Entities lack hierarchy value - so Hierarchy should fail"""

    sub1 = entity_with_attrs("bubb", [
    ])

    sub2 = entity_with_attrs("rubb", [
    ])

    sub3 = entity_with_attrs("woowoo", [
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/C")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([classif_attr])

    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, claims, classif_policy.options["order"])

def test_hierarchy_decision_fail_no_data_claims():
    """Data entirely lack attribute value - so Hierarchy should fail"""

    sub1 = entity_with_attrs("bubb", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    sub2 = entity_with_attrs("rubb", [
        "https://example.com/attr/classif/value/C",
    ])

    sub3 = entity_with_attrs("woowoo", [
        "https://example.com/attr/classif/value/C",
        "https://example.com/attr/conflictReport/value/agency4",
    ])

    classif_attr = AttributeValue("https://example.com/attr/classif/value/C")

    classif_policy = AttributePolicy(
        "https://example.com/attr/classif", HIERARCHY, order=["TS", "S", "C", "U"]
    )

    decodedJwt = compose_jwt("bubb", [sub1, sub2, sub3])
    claims = Claims.load_from_raw_data(decodedJwt)
    data_values = frozenset([])

    with pytest.raises(AuthorizationError):
        hierarchy_decision(data_values, claims, classif_policy.options["order"])
