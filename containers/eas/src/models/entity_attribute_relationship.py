import enum
import json
from enum import Enum
from typing import Optional

from .state import State


class EntityAttributeRelationship:
    # @startuml
    # [*] --> Active
    # Active --> Inactive
    # Inactive --> Active
    # @enduml

    @enum.unique
    class Action(Enum):
        CREATE = 1
        ACTIVATE = 2
        INACTIVATE = 3

    def __init__(
        self, entity_id: str = "", attribute_uri: str = "", state: State = None
    ):
        self.__entity_id = entity_id
        self.__attribute_uri = attribute_uri
        self.__state = state

    def to_json(self) -> str:
        return EntityAttributeRelationshipJSONEncoder().encode(self)

    @classmethod
    def from_raw(cls, data: dict) -> "EntityAttributeRelationship":
        """Construct a EntityAttributeRelationship model from a raw dictionary (import)."""
        return cls(
            entity_id=data["entityId"],
            attribute_uri=data["attributeURI"],
            state=State.from_input(data["state"]),
        )

    @property
    def entity_id(self) -> str:
        return self.__entity_id

    @property
    def attribute_uri(self) -> str:
        return self.__attribute_uri

    @property
    def state(self) -> Optional[State]:
        return self.__state

    def next_state(self, action=None) -> None:
        """update the state based on the action. Action is type EntityAttributeRelationship.Action"""
        if action is EntityAttributeRelationship.Action.CREATE and self.__state is None:
            self.__state = State.ACTIVE
        if (
            action is EntityAttributeRelationship.Action.ACTIVATE
            and self.__state is State.INACTIVE
        ):
            self.__state = State.ACTIVE
        if (
            action is EntityAttributeRelationship.Action.INACTIVATE
            and self.__state is State.ACTIVE
        ):
            self.__state = State.INACTIVE


class EntityAttributeRelationshipJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, EntityAttributeRelationship):
            return {
                "entityId": obj.entity_id,
                "attributeURI": obj.attribute_uri,
                "state": State.to_string(obj.state),
            }
        else:
            return super().default(obj)
