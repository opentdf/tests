from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import EntityAttributeRelationship


class AbstractEntityAttributeRelationshipService(ABC):
    @abstractmethod
    def insert(
        self, entity_attribute_relationship: EntityAttributeRelationship
    ) -> None:
        pass

    @abstractmethod
    def read(
        self, entity_id: str = "", attribute_uri: str = ""
    ) -> Optional[EntityAttributeRelationship]:
        pass

    @abstractmethod
    def read_all(self) -> List[EntityAttributeRelationship]:
        pass

    @abstractmethod
    def read_by_entity_id(
        self, entity_id: str = ""
    ) -> List[EntityAttributeRelationship]:
        pass

    @abstractmethod
    def read_by_attribute_uri(
        self, attribute_uri: str = ""
    ) -> List[EntityAttributeRelationship]:
        pass

    @abstractmethod
    def read_by_attribute(
        self, name: str, value: str, namespace: str = None
    ) -> List[EntityAttributeRelationship]:
        pass

    @abstractmethod
    def read_by_attribute_name(
        self, name: str, namespace: str = None
    ) -> List[EntityAttributeRelationship]:
        pass

    @abstractmethod
    def update_state(
        self, entity_attribute_relationship: EntityAttributeRelationship
    ) -> None:
        pass

    @abstractmethod
    def add_attributes_to_user(self, userId: str, attribute_urls: List[str]) -> None:
        pass

    @abstractmethod
    def update_attributes_for_entity(
        self, userId: str, desired_attributes: List[str], existing_attributes: List[str]
    ) -> None:
        pass
