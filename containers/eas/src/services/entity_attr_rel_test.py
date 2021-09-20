import json

import pytest  # noqa: F401

from .abstract_entity_attr_rel import AbstractEntityAttributeRelationshipService
from . import EntityAttributeRelationshipServiceSQL
from ..models import AttributeValue, EntityAttributeRelationship, State


def test_next_state():
    ears = []
    ear = EntityAttributeRelationship("entity1", "attr1")
    assert ear.to_json()
    ear.next_state(EntityAttributeRelationship.Action.CREATE)
    assert ear.to_json()
    ears.append(ear.to_json())
    assert State.ACTIVE == ear.state
    ear = EntityAttributeRelationship("entity1", "attr1", State.INACTIVE)
    ear.next_state(EntityAttributeRelationship.Action.ACTIVATE)
    ears.append(ear.to_json())
    assert State.ACTIVE == ear.state
    ear = EntityAttributeRelationship("entity1", "attr1", State.ACTIVE)
    ear.next_state(EntityAttributeRelationship.Action.INACTIVATE)
    ears.append(ear.to_json())
    assert State.INACTIVE == ear.state
    assert json.dumps(ears)


@pytest.fixture(scope="session")
def entity_attribute_relationship_service():
    return EntityAttributeRelationshipServiceSQL()


def test_attribute_service_insert_read_state(entity_attribute_relationship_service):
    # This attr is defined in attribute_names.json
    attr1 = "https://eas.virtru.com/attr/ClassificationUS/value/Secret"
    user1 = "Charlie_1234"
    ear = EntityAttributeRelationship(
        entity_id="Charlie_1234", attribute_uri=attr1, state=State.ACTIVE
    )
    entity_attribute_relationship_service.insert(ear)

    # Reading by attribute uri should return 1 result with same id
    result = entity_attribute_relationship_service.read_by_attribute_uri(
        ear.attribute_uri
    )
    assert len(result) > 0
    assert result[0].attribute_uri == ear.attribute_uri
    assert result[0].entity_id == ear.entity_id

    # Reading by attribute name/value/namespace should also return 1 result with same id
    attr_value = AttributeValue.from_uri(ear.attribute_uri)
    result = entity_attribute_relationship_service.read_by_attribute(
        name=attr_value.name,
        value=attr_value.value,
        namespace=attr_value.authorityNamespace,
    )
    assert len(result) > 0
    assert result[0].attribute_uri == ear.attribute_uri
    assert result[0].entity_id == ear.entity_id

    # Reading by entity should return 1 result with same id
    result = entity_attribute_relationship_service.read_by_entity_id(ear.entity_id)
    assert len(result) > 0
    # results should match the entity id
    assert result[0].entity_id == ear.entity_id

    # And the read function should bring back the relationship too
    result = entity_attribute_relationship_service.read(
        attribute_uri=attr1, entity_id=user1
    )
    assert isinstance(result, EntityAttributeRelationship)
    assert result.attribute_uri == attr1
    assert result.entity_id == user1

    # Test read all while we're at it
    result = entity_attribute_relationship_service.read_all()
    assert result
    assert len(result)

    # Test state changes
    ear.next_state(EntityAttributeRelationship.Action.INACTIVATE)
    entity_attribute_relationship_service.update_state(
        entity_attribute_relationship=ear
    )
    result = entity_attribute_relationship_service.read(
        attribute_uri=attr1, entity_id=user1
    )
    assert isinstance(result, EntityAttributeRelationship)
    assert result.state == State.INACTIVE

    # Test state changes
    ear.next_state(EntityAttributeRelationship.Action.ACTIVATE)
    entity_attribute_relationship_service.update_state(
        entity_attribute_relationship=ear
    )
    result = entity_attribute_relationship_service.read(
        attribute_uri=attr1, entity_id=user1
    )
    assert isinstance(result, EntityAttributeRelationship)
    assert result.state == State.ACTIVE


def test_abstract_ear_service():
    # Ensure we can't instantiate this abstract class
    with pytest.raises(TypeError):
        AbstractEntityAttributeRelationshipService()
