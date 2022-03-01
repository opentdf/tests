"""Test the Adjudicator and helper functions."""

import pytest

from tdf3_kas_core.models import Policy
from tdf3_kas_core.models import Entity
from tdf3_kas_core.models import EntityAttributes
from tdf3_kas_core.models import AttributePolicyCache

from tdf3_kas_core.models import HIERARCHY

from tdf3_kas_core.errors import AuthorizationError

from tdf3_kas_core.util import get_public_key_from_disk

from .adjudicator import Adjudicator


PUBLIC_KEY = get_public_key_from_disk("test")


def test_adjudicator_construction_normal():
    """Test construction without config."""
    actual1 = Adjudicator(AttributePolicyCache())
    assert isinstance(actual1, Adjudicator)


# >>>>>>>>>> ALL OF <<<<<<<<<<<<<<<<<<


def test_adjudicator_allows_access_wildcard_dissem():
    """Test denies access."""
    # config = AttributePolicyConfig(POLICY_CONFIG_SAMPLE)
    cache = AttributePolicyCache()
    adjudicator = Adjudicator(cache)

    policy = Policy("a policy id", "a policy canonical")
    print("===== Policy")
    print(policy.dissem.list)

    entity = Entity("email2@example.com", PUBLIC_KEY, EntityAttributes())
    print("===== Entity")
    print(entity.user_id)

    assert adjudicator.can_access(policy, entity) is True


def test_adjudicator_allows_access_from_dissem():
    """Test denies access."""
    cache = AttributePolicyCache()
    adjudicator = Adjudicator(cache)

    policy = Policy("a policy id", "a policy canonical")
    policy.dissem.list = [
        "email1@example.com",
        "email2@example.com",
        "email3@example.com",
    ]

    print("===== Policy")
    print(policy.dissem.list)

    entity = Entity("email2@example.com", PUBLIC_KEY, EntityAttributes())

    print("===== Entity")
    print(entity.user_id)

    assert adjudicator.can_access(policy, entity) is True


def test_adjudicator_denies_access_from_dissem():
    """Test denies access."""
    cache = AttributePolicyCache()
    adjudicator = Adjudicator(cache)

    policy = Policy("a policy id", "a policy canonical")
    policy.dissem.list = [
        "email1@example.com",
        "email2@example.com",
        "email3@example.com",
    ]
    print("===== Policy")
    print(policy.dissem.list)
    entity = Entity("foo@bar.com", PUBLIC_KEY, EntityAttributes())
    print("===== Entity")
    print(entity.user_id)

    with pytest.raises(AuthorizationError):
        adjudicator.can_access(policy, entity)


# >>>>>>>>>> ALL OF <<<<<<<<<<<<<<<<<<

all_of_config = [
    {"authorityNamespace": "https://example.com", "name": "NTK", "rule": "allOf"}
]


def test_adjudicator_grants_access_allof_attribute():
    """Test grants access with an all-of attribute value."""
    cache = AttributePolicyCache()
    cache.load_config(all_of_config)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [
            {"attribute": "https://example.com/attr/NTK/value/projx"},
            {"attribute": "https://example.com/attr/NTK/value/financial"},
        ]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [
            {"attribute": "https://example.com/attr/NTK/value/projx"},
            {"attribute": "https://example.com/attr/NTK/value/financial"},
        ]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    assert adjudicator.can_access(policy, entity) is True


def test_adjudicator_denies_access_allof_attribute():
    """Test denies access with wrong any-of attribute value."""
    cache = AttributePolicyCache()
    cache.load_config(all_of_config)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [
            {"attribute": "https://example.com/attr/NTK/value/projx"},
            {"attribute": "https://example.com/attr/NTK/value/financial"},
        ]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [{"attribute": "https://example.com/attr/NTK/value/projx"}]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    with pytest.raises(AuthorizationError):
        adjudicator.can_access(policy, entity)


# >>>>>>>>>> ANY OF <<<<<<<<<<<<<<<<<<

any_of_config = [
    {"authorityNamespace": "https://example.com", "name": "Rel", "rule": "anyOf"}
]


def test_adjudicator_grants_access_anyof_attribute():
    """Test grants access with an any-of attribute value."""
    cache = AttributePolicyCache()
    cache.load_config(any_of_config)
    foo = cache.get("https://example.com/attr/Rel")
    print(foo.rule)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [
            {"attribute": "https://example.com/attr/Rel/value/CAN"},
            {"attribute": "https://example.com/attr/Rel/value/GBR"},
            {"attribute": "https://example.com/attr/Rel/value/USA"},
        ]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [
            {"attribute": "https://example.com/attr/Rel/value/GBR"},
            {"attribute": "https://example.com/attr/Rel/value/AUS"},
        ]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    assert adjudicator.can_access(policy, entity) is True


def test_adjudicator_denies_access_anyof_attribute():
    """Test denies access with wrong any-of attribute value."""
    cache = AttributePolicyCache()
    cache.load_config(any_of_config)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [
            {"attribute": "https://example.com/attr/Rel/value/CAN"},
            {"attribute": "https://example.com/attr/Rel/value/GBR"},
            {"attribute": "https://example.com/attr/Rel/value/USA"},
        ]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [{"attribute": "https://example.com/attr/Rel/value/AUS"}]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    with pytest.raises(AuthorizationError):
        adjudicator.can_access(policy, entity)


# >>>>>>>>>> HIERARCHY <<<<<<<<<<<<<<<<<<

hierarchy_config = [
    {
        "authorityNamespace": "https://example.com",
        "name": "classif",
        "order": ["TS", "S", "C", "U"],
        "rule": "hierarchy",
    }
]


def test_adjudicator_grants_access_hierarchy_attribute_equal():
    """Test hierarchy decision."""
    cache = AttributePolicyCache()
    cache.load_config(hierarchy_config)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [{"attribute": "https://example.com/attr/classif/value/S"}]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [{"attribute": "https://example.com/attr/classif/value/S"}]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    assert adjudicator.can_access(policy, entity) is True


def test_adjudicator_grants_access_hierarchy_entity_attribute_greater():
    """Test hierarchy decision."""
    cache = AttributePolicyCache()
    cache.load_config(hierarchy_config)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [{"attribute": "https://example.com/attr/classif/value/S"}]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [{"attribute": "https://example.com/attr/classif/value/TS"}]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    assert adjudicator.can_access(policy, entity) is True


def test_adjudicator_denies_access_hierarchy_entity_attribute_lesser():
    """Test hierarchy decision."""
    cache = AttributePolicyCache()
    cache.load_config(hierarchy_config)
    adjudicator = Adjudicator(cache)
    policy = Policy("a policy id", "a policy canonical")
    policy.data_attributes.load_raw(
        [{"attribute": "https://example.com/attr/classif/value/S"}]
    )
    entity_attributes = EntityAttributes.create_from_list(
        [{"attribute": "https://example.com/attr/classif/value/C"}]
    )
    entity = Entity("doesn't_matter", PUBLIC_KEY, entity_attributes)
    with pytest.raises(AuthorizationError):
        adjudicator.can_access(policy, entity)
