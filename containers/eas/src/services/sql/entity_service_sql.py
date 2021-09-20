"""Entity Service SQLite - Users and Non-Person Entities."""

import logging
from typing import Any, Dict, List, Optional

from ..abstract_entity_attr_rel import AbstractEntityAttributeRelationshipService
from ..abstract_entity_service import AbstractEntityService
from ...db_connectors import SQLiteConnector
from ...errors import EntityExistsError, MalformedEntityError, NotFound
from ...models import Entity, State

logger = logging.getLogger(__name__)


class EntityServiceSql(AbstractEntityService):
    """Entity Services data connector."""

    def __init__(self, ear_service: AbstractEntityAttributeRelationshipService):
        """Construct data connector with db path."""
        self.connector = SQLiteConnector.get_instance()
        assert ear_service
        assert isinstance(ear_service, AbstractEntityAttributeRelationshipService)
        self.ear_service: AbstractEntityAttributeRelationshipService = ear_service

    def create(self, body: dict) -> dict:
        """Create a new entity."""
        logger.debug("Creating new user with body = %s", body)

        if "userId" not in body:
            raise MalformedEntityError("userId is required.")
        userId = body["userId"]

        # Try to form a user model with the provided info
        entity = Entity.from_raw(body)

        # Check to see if user exists
        if self.retrieve(userId):
            raise EntityExistsError(f"Duplicate userId {userId}")
        if self.retrieve(entity.email, by_email=True):
            raise EntityExistsError(f"Duplicate userId {userId}")

        # Insert the basic entity record
        command = """
                INSERT INTO entity
                    ("userId", "name", "email", "nonPersonEntity", "state", "pubKey")
                VALUES
                    (?, ?, ?, ?, ?, ?)
            """
        parameters = (
            entity.userId,
            entity.name,
            entity.email,
            int(entity.nonPersonEntity),
            entity.state.value,
            entity.pubKey,
        )
        entity_result = self.connector.run(command, parameters)
        assert entity_result

        # Add attributes
        self.ear_service.add_attributes_to_user(entity.userId, entity.attributes)
        return entity.to_raw()

    def retrieve(
        self, userid_or_email: str, by_email: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieve data (email and attributes) for a single user, by userId"""
        if by_email:
            criteria = "email"
        else:
            criteria = "userId"

        logger.debug(
            "entity_service_sql.retrieve(%s, by_email=%s)",
            userid_or_email,
            by_email,
        )
        command = """
                SELECT
                    userId, email, name, nonPersonEntity, entityState, pubKey, attribute_uri, attrState
                FROM entityAttributeView
                WHERE {} = ?
            """.format(
            criteria
        )
        parameters = (userid_or_email,)
        response = self.connector.run(command, parameters)
        results = response.fetchall()

        if not results:
            logger.debug("entity_service_sql.retrieve() returned nothing")
            return None

        logger.debug("db returned row %s", results[0])
        (
            user_id,
            email,
            name,
            nonPersonEntity,
            entity_state,
            pub_key,
            attribute_uri,  # result not used
            attribute_state,  # result not used
        ) = results[0]
        user_dict = {
            "userId": str(user_id or ""),
            "email": str(email or ""),
            "name": str(name or ""),
            "nonPersonEntity": bool(nonPersonEntity),
            "state": State(entity_state).to_string(),
            "pubKey": str(pub_key or ""),
            "attributes": [],
        }

        # Populate the attributes. The entityAttributeView has one row per attribute
        for result in results:
            # add the attribute
            attribute_uri, attribute_state = result[6], result[7]
            if attribute_uri and attribute_state == State.ACTIVE.value:
                user_dict["attributes"].append(attribute_uri)
        logger.debug("entity_service_sql.retrieve() returned %s", user_dict)
        return user_dict

    def retrieveAll(self) -> List[Optional[Dict[str, Any]]]:
        """Retrieve all user records."""
        command = """
            SELECT userId FROM entity
        """

        results = self.connector.run(command, ()).fetchall()

        # The following runs a query for each user to get the user object with attributes.
        # May not scale well to very large numbers of entity.
        result_set = []
        for result in results:
            result_set.append(self.retrieve(result[0], False))

        return result_set

    def update(self, body: dict) -> Dict[str, Any]:
        """Update entity record, as selected by userId
        Note that if entity already has attribute in DB but update call doesn't include attribute,
        the attribute will be removed."""
        logger.debug(f"update({body.__repr__()})")

        if "userId" not in body:
            raise MalformedEntityError("userId is required")
        userId = body["userId"]

        # Verify entity exists
        existing_entity = self.retrieve(userId)
        if not existing_entity:
            raise EntityExistsError(
                message=f"Cannot update entity {userId} because entity does not exist."
            )

        # Form a entity model with the provided info
        entity = Entity.from_raw(body)

        # Note: Currently there are separate transaction for update, remove attributes, and add attributes.
        # It would be better to wrap in a transaction.

        # Insert the basic entity record
        command = """
            UPDATE entity
                SET "email"= ?, "name"= ?, "nonPersonEntity"= ?, "state"=?, "pubKey"=?
            WHERE
                "userId" = ?
            """
        parameters = (
            entity.email,
            entity.name,
            int(entity.nonPersonEntity),
            entity.state.value,
            entity.pubKey,
            entity.userId,
        )
        result = self.connector.run(command, parameters)
        assert result

        # Add attributes in provided list of attributes
        self.ear_service.update_attributes_for_entity(
            entity.userId,
            desired_attributes=entity.attributes,
            existing_attributes=existing_entity["attributes"],
        )

        return entity.to_raw()

    def delete(self, userId: str) -> Dict[str, Any]:
        """Set state of specified entity to inactive."""
        entity = self.retrieve(userId)
        if not entity:
            raise NotFound(
                f"Could not deactivate {userId} because this entity was not found."
            )
        entity["state"] = "inactive"
        command = """
            UPDATE entity
            SET state = ?
            WHERE userId = ?
        """
        parameters = (State.INACTIVE.value, userId)
        # Force commit because inactivating a user should happen immediately.
        assert self.connector.run(command, parameters, force_commit=True)
        return entity

    def retrieveAllByQuery(self, query: str) -> List[Optional[Dict[str, Any]]]:
        """Retrieve all user records."""
        command = """
            SELECT * FROM entity
            WHERE userId LIKE ? OR email LIKE ? OR name LIKE ?
        """
        st = "%" + query + "%"
        parameters = (
            st,
            st,
            st,
        )
        results = self.connector.run(command, parameters).fetchall()

        # The following runs a query for each user to get the user object with attributes.
        # May not scale well to very large numbers of entity.
        result_set = []
        for result in results:
            result_set.append(self.retrieve(result[0], False))

        return result_set
