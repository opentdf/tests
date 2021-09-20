import logging
from typing import List, Optional

from ...db_connectors import SQLiteConnector
from ...eas_config import EASConfig
from ...models import AttributeValue, EntityAttributeRelationship, State
from ...services import AbstractEntityAttributeRelationshipService

logger = logging.getLogger(__name__)


class EntityAttributeRelationshipServiceSQL(AbstractEntityAttributeRelationshipService):
    def __init__(self) -> None:
        """Construct data connector with db path."""
        self.connector: SQLiteConnector = SQLiteConnector.get_instance()

    def insert(
        self, entity_attribute_relationship: EntityAttributeRelationship
    ) -> None:
        """
        Insert an EntityAttributeRelationship into entityAttribute table.

        :param entity_attribute_relationship: EntityAttributeRelationship object to insert
        :return: int representing primary key id of inserted row
        """
        logger.debug(
            f"insert({entity_attribute_relationship.to_json() if entity_attribute_relationship else 'None'})"
        )

        # If already exists, do an update instead.
        if self.read(
            entity_attribute_relationship.entity_id,
            entity_attribute_relationship.attribute_uri,
        ):
            return self.update_state(entity_attribute_relationship)

        # If state has not been established, do "CREATE" action to add state.
        if not entity_attribute_relationship.state:
            entity_attribute_relationship.next_state(
                action=EntityAttributeRelationship.Action.CREATE
            )

        attr_value = AttributeValue.from_uri(
            entity_attribute_relationship.attribute_uri
        )
        command = """
            INSERT INTO entityAttribute
                (state, userId, namespace, name, value)
            VALUES (?, ?, ?, ?, ?)
        """
        parameters = (
            entity_attribute_relationship.state.value
            if entity_attribute_relationship.state
            else None,
            entity_attribute_relationship.entity_id,
            attr_value.authorityNamespace,
            attr_value.name,
            attr_value.value,
        )
        result = self.connector.run(command, parameters)
        assert result.lastrowid

    def read(
        self, entity_id: str = "", attribute_uri: str = ""
    ) -> Optional[EntityAttributeRelationship]:
        attr_value = AttributeValue.from_uri(attribute_uri)
        command = """
            SELECT state,
                   userId,
                   namespace || '/attr/' || name || '/value/' || value AS attribute_uri
            FROM entityAttribute
            WHERE
                userId = ? 
                AND
                namespace = ? AND name = ? and VALUE = ?
            """
        parameters = (
            entity_id,
            attr_value.authorityNamespace,
            attr_value.name,
            attr_value.value,
        )
        response = self.connector.run(command, parameters)
        result = response.fetchone()
        if result is None:
            return None
        state = State(result[0])
        return EntityAttributeRelationship(result[1], result[2], state)

    def read_all(self) -> List[EntityAttributeRelationship]:
        command = """
            SELECT state,
                   userId,
                   namespace || '/attr/' || name || '/value/' || value AS attribute_uri
            FROM entityAttribute
            """
        parameters = ()
        response = self.connector.run(command, parameters)
        results = response.fetchall()
        return self.results_to_ears(results)

    @staticmethod
    def results_to_ears(results: List[list]) -> List[EntityAttributeRelationship]:
        """Transform database results (state integer, userId, uri) to list of ear"""
        if results is None:
            return []
        result_set = []
        for result in results:
            state_int, entity_id, attribute_uri = result[:3]
            state = State(state_int)
            result_set.append(
                EntityAttributeRelationship(entity_id, attribute_uri, state)
            )
        return result_set

    def read_by_entity_id(
        self, entity_id: str = ""
    ) -> List[EntityAttributeRelationship]:
        command = """
            SELECT state,
                   userId,
                   namespace || '/attr/' || name || '/value/' || value AS attribute_uri
            FROM entityAttribute
            WHERE
                userId = ? 
            """
        parameters = (entity_id,)
        response = self.connector.run(command, parameters)
        results = response.fetchall()
        return self.results_to_ears(results)

    def read_by_attribute_uri(
        self, attribute_uri: str = ""
    ) -> List[EntityAttributeRelationship]:
        """Given attribute uri, return list of EntityAttributeRelationship(s)"""
        attr_value = AttributeValue.from_uri(attribute_uri)
        return self.read_by_attribute(
            name=attr_value.name,
            value=attr_value.value,
            namespace=attr_value.authorityNamespace,
        )

    def read_by_attribute(
        self, name: str, value: str, namespace: str = None
    ) -> List[EntityAttributeRelationship]:
        """Given attribute name/value/namespace, return list of EntityAttributeRelationship(s)"""
        if not namespace:
            namespace = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")
        command = """
            SELECT state,
                   userId,
                   namespace || '/attr/' || name || '/value/' || value AS attribute_uri
            FROM entityAttribute
            WHERE
                namespace = ? AND name = ? and VALUE = ?
            """
        parameters = (namespace, name, value)
        response = self.connector.run(command, parameters)
        results = response.fetchall()
        return self.results_to_ears(results)

    def read_by_attribute_name(
        self, name: str, namespace: str = None
    ) -> List[EntityAttributeRelationship]:
        """Given attribute name/namespace (no value), return list of EntityAttributeRelationship(s)"""
        if not namespace:
            namespace = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")
        command = """
            SELECT state,
                   userId,
                   namespace || '/attr/' || name || '/value/' || value AS attribute_uri
            FROM entityAttribute
            WHERE
                namespace = ? AND name = ?
            """
        parameters = (namespace, name)
        response = self.connector.run(command, parameters)
        results = response.fetchall()
        return self.results_to_ears(results)

    def update_state(
        self, entity_attribute_relationship: EntityAttributeRelationship
    ) -> None:
        logger.debug(
            f"update_state({entity_attribute_relationship.to_json() if entity_attribute_relationship else 'None'})"
        )
        attr_value = AttributeValue.from_uri(
            entity_attribute_relationship.attribute_uri
        )
        command = """
            UPDATE entityAttribute
            SET
                state = ?
            WHERE
                userId = ? 
                AND
                namespace = ?
                AND
                name = ?
                AND
                value = ?
            """
        parameters = (
            entity_attribute_relationship.state.value
            if entity_attribute_relationship.state
            else None,
            entity_attribute_relationship.entity_id,
            attr_value.authorityNamespace,
            attr_value.name,
            attr_value.value,
        )
        self.connector.run(command, parameters, force_commit=True)

    def add_attributes_to_user(self, userId: str, attribute_urls: List[str]) -> None:
        """Private method - Update entity with new attribute."""
        if len(attribute_urls) == 0:
            logger.debug("No attributes to add")
            return
        ears: List[EntityAttributeRelationship] = [
            EntityAttributeRelationship(
                entity_id=userId, attribute_uri=attr, state=State.ACTIVE
            )
            for attr in attribute_urls
        ]
        for ear in ears:
            self.insert(entity_attribute_relationship=ear)

    def update_attributes_for_entity(
        self, userId: str, desired_attributes: List[str], existing_attributes: List[str]
    ) -> None:
        """Private Method - Set the entity Attribute relationship to ACTIVE or INACTIVE state"""

        # Use set comparison to see what attributes to remove:
        remove_attributes = list(set(existing_attributes) - set(desired_attributes))
        # Convert to list of INACTIVE ears:
        inactivate_ears = [
            EntityAttributeRelationship(
                entity_id=userId, attribute_uri=uri, state=State.INACTIVE
            )
            for uri in remove_attributes
        ]
        # Update states of ears to remove the attributes
        for ear in inactivate_ears:
            self.update_state(entity_attribute_relationship=ear)

        # Use set comparison to see what attributes to add, and add them:
        new_attributes = list(set(desired_attributes) - set(existing_attributes))
        self.add_attributes_to_user(userId, new_attributes)
