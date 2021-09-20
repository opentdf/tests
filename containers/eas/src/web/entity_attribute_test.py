import pytest

from .entity_attribute import (
    add_attribute_to_entity_via_attribute,
    add_attribute_to_entity_via_entity,
    delete_attribute_from_entity,
    get_entity_attribute,
)


def test_get_entity_attribute():
    with pytest.raises(RuntimeError):
        get_entity_attribute()


def test_add_attribute_to_entity_via_attribute():
    (response, code, headers) = add_attribute_to_entity_via_attribute(None, None)
    assert response["title"] == "Bad request"
    assert code == 400


def test_add_attribute_to_entity_via_entity():
    (response, code, headers) = add_attribute_to_entity_via_entity(None, None)
    assert response["title"] == "Bad request"
    assert code == 400


def test_delete_attribute_from_entity():
    (response, code, headers) = delete_attribute_from_entity(None, None)
    assert response
    assert code == 400
