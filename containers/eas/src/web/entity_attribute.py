import json
import logging
from typing import Any, Dict, List, Optional

from .status import statusify
from ..errors import EasRequestError, NotFound
from ..models import AttributeValue, EntityAttributeRelationship, State
from ..services import (
    AbstractAttributeService,
    AbstractEntityAttributeRelationshipService,
    AbstractEntityService,
    ServiceSingleton,
)

logger = logging.getLogger(__name__)


def ear_service() -> AbstractEntityAttributeRelationshipService:
    return ServiceSingleton.get_instance().ear_service


def entity_service() -> AbstractEntityService:
    return ServiceSingleton.get_instance().entity_service


def attribute_service() -> AbstractAttributeService:
    return ServiceSingleton.get_instance().attribute_service


@statusify
def get_entity_attribute():
    results = ear_service().read_all()
    response = []
    for result in results:
        response.append(json.loads(result.to_json()))
    return response


@statusify
def add_attribute_to_entity_via_attribute(body: list, attributeURI: str) -> List[str]:
    logger.debug(
        f"add_attribute_to_entity_via_attribute(body: {body}, attributeURI:{attributeURI}"
    )
    if type(body) != list:
        raise EasRequestError("PUT body must be a json list")
    response = []
    for entityId in body:
        ear = ear_service().read(entity_id=entityId, attribute_uri=attributeURI)
        if ear is not None:
            # update
            ear.next_state(EntityAttributeRelationship.Action.ACTIVATE)
            ear_service().update_state(ear)
            response.append(ear.entity_id)
        else:
            # insert
            ear = EntityAttributeRelationship(entityId, attributeURI)
            ear.next_state(EntityAttributeRelationship.Action.CREATE)
            ear_service().insert(ear)
            response.append(ear.entity_id)
    return response


@statusify
def add_attribute_to_entity_via_entity(body: list, entityId: str) -> dict:
    if type(body) != list:
        raise EasRequestError("PUT body must be a json list")
    for attributeURI in body:
        ear = ear_service().read(entity_id=entityId, attribute_uri=attributeURI)
        if ear is not None:
            # update
            ear.next_state(EntityAttributeRelationship.Action.ACTIVATE)
            ear_service().update_state(ear)
        else:
            ear = EntityAttributeRelationship(entityId, attributeURI)
            ear.next_state(EntityAttributeRelationship.Action.CREATE)
            ear_service().insert(ear)
    # get update entity
    entity = entity_service().retrieve(entityId)
    if not entity:
        raise NotFound(f"{entityId} was not found.")
    entity["nonPersonEntity"] = bool(entity["nonPersonEntity"])
    entity["state"] = State.from_input(entity["state"]).name.lower()
    return entity


@statusify
def delete_attribute_from_entity(entityId: str, attributeURI: str) -> None:
    """Soft delete an ear - set status to inactive"""
    ear = ear_service().read(entity_id=entityId, attribute_uri=attributeURI)
    if ear is None:
        raise NotFound(f"Found no relationship between {entityId} and {attributeURI}.")
    ear.next_state(EntityAttributeRelationship.Action.INACTIVATE)
    ear_service().update_state(ear)
    # no content
    return None


@statusify
def get_entities_for_attribute(
    name: str, value: str, namespace: str = None
) -> List[Optional[Dict[str, Any]]]:
    results = ear_service().read_by_attribute(
        name=name, value=value, namespace=namespace
    )
    response = active_ears_to_entities(results)
    return response


@statusify
def get_entities_for_attribute_name(
    name: str, namespace: str = None
) -> List[Optional[Dict[str, Any]]]:
    results = ear_service().read_by_attribute_name(name=name, namespace=namespace)
    response = expand_ears(results)
    return response


def active_ears_to_entities(
    results: List[EntityAttributeRelationship],
) -> List[Optional[Dict[str, Any]]]:
    # TODO: Refactor to use a single SQL query to improve performance and robustness.
    response = []
    for ear in results:
        if State.from_input(ear.state) == State.ACTIVE:
            response.append(entity_service().retrieve(ear.entity_id))
        else:
            logger.debug(
                "Not returning entity %s because relationship state is %s",
                ear.entity_id,
                ear.state,
            )
    return response


def expand_ears(results: list) -> List[Optional[Dict[str, Any]]]:
    """Return an array of Entity Attribute Relationships, expanded with full entity and attribute objects"""
    # TODO: Refactor to use a single SQL query to improve performance and robustness.
    response: List[Optional[Dict[str, Any]]] = []
    for ear in results:
        attr_fetch = attribute_service().retrieve([ear.attribute_uri])
        attr_obj: AttributeValue = attr_fetch[0]
        expanded = {
            "entity": entity_service().retrieve(ear.entity_id),
            "attribute": attr_obj.to_raw_dict(),
            "state": ear.state.to_string(),
        }
        response.append(expanded)
    return response
