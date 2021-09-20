"""Test the Entity model."""


import pytest  # noqa: F401

from .entity import Entity
from ...eas_config import EASConfig
from ...services.attribute_service_test import random_attribute

ATTR_LANGUAGE_VALUE_JAPANESE = "/attr/language/value/japanese"

ATTR_LANGUAGE_VALUE_FRENCH = "/attr/language/value/french"

ATTR_LANGUAGE_VALUE_URDU = "/attr/language/value/urdu"

DEFAULT_NAMESPACE = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")


def test_entity_constructor():
    """Test user."""
    userId = "Fred Flintsone"
    actual = Entity(userId)
    assert isinstance(actual, Entity)
    assert actual.userId is userId
    assert actual.name is None
    assert actual.email is None
    assert actual.attributes == []


def test_entity_name():
    """Test user."""
    userId = "Fred Flintsone"
    test_case = Entity(userId)
    expected = "expecto"
    test_case.name = "expecto"
    actual = test_case.name
    assert actual == expected


def test_entity_email():
    """Test user."""
    userId = "Fred Flintsone"
    test_case = Entity(userId)
    expected = "expected@obvious.com"
    test_case.email = "expected@obvious.com"
    actual = test_case.email
    assert actual == expected


def test_entity_add_attribute():
    """Test user."""
    userId = "Fred Flintsone"
    test_case = Entity(userId)

    expected_1 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_URDU
    expected_2 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_FRENCH
    expected_3 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_JAPANESE
    expected = [expected_1, expected_2, expected_3]

    test_case.add_attribute(expected_1)
    test_case.add_attribute(expected_2)
    test_case.add_attribute(expected_3)
    actual = test_case.attributes

    assert set(actual) == set(expected)


def test_entity_equality():
    """Test user."""
    id_1 = "Fred Flintsone"
    id_2 = "Barney Rubble"

    entity_base = Entity(id_1)
    entity_same = Entity(id_1)
    user_id_wrong = Entity(id_2)

    assert entity_base == entity_same
    assert entity_base != user_id_wrong


def test_entity_hash():
    """Test user."""
    id_1 = "Fred Flintsone"
    id_2 = "Barney Rubble"

    entity_base = Entity(id_1)
    entity_same = Entity(id_1)
    user_id_wrong = Entity(id_2)

    assert entity_base.__hash__() == entity_same.__hash__()
    assert entity_base.__hash__() != user_id_wrong.__hash__()


def test_entity_remove_attribute():
    """Test user."""
    userId = "Fred Flintstone"
    test_case = Entity(userId)

    expected_1 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_URDU
    expected_2 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_FRENCH
    expected_3 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_JAPANESE
    expected = [expected_3]

    test_case.add_attribute(expected_1)
    test_case.add_attribute(expected_2)
    test_case.add_attribute(expected_3)

    test_case.remove_attribute(expected_1)
    test_case.remove_attribute(expected_2)
    actual = test_case.attributes

    assert set(actual) == set(expected)


def test_entity_has_attribute():
    """Test user."""
    userId = "Fred Flintstone"
    test_case = Entity(userId)

    expected_1 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_URDU
    expected_2 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_FRENCH
    expected_3 = DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_JAPANESE
    expected = [expected_1, expected_2, expected_3]

    test_case.add_attribute(expected_1)
    test_case.add_attribute(expected_2)
    test_case.add_attribute(expected_3)

    assert test_case.has_attribute(expected_1) is True
    assert test_case.has_attribute(expected_2) is True
    assert test_case.has_attribute(expected_3) is True
    assert test_case.has_attribute("huh?") is False


def test_entity_import_export():
    """Test user."""
    expected = {
        "userId": "Alice@example.com",
        "name": "Alice",
        "email": "Alice@example.com",
        "attributes": [
            DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_URDU,
            DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_FRENCH,
            DEFAULT_NAMESPACE + ATTR_LANGUAGE_VALUE_JAPANESE,
        ],
    }
    user = Entity.from_raw(expected)
    assert isinstance(user, Entity)
    actual = user.to_raw()
    assert len(actual.keys()) == 7
    assert actual["userId"] == expected["userId"]
    assert actual["name"] == expected["name"]
    assert actual["email"] == expected["email"]
    # order is unimportant
    assert set(actual["attributes"]) == set(expected["attributes"])


def test_entity_properties():
    """Test constructors, getters, and setters."""
    user_id = "vtruman"
    e = Entity(user_id)
    assert e.userId == user_id
    assert not e.nonPersonEntity
    e.nonPersonEntity = True
    assert e.nonPersonEntity
    assert not e.name
    e.name = "Virgil Truman"
    assert e.name == "Virgil Truman"
    assert e.attributes == []
    attr = [random_attribute(), random_attribute(), random_attribute()]
    e.attributes = attr
    assert e.attributes.sort() == attr.sort()
