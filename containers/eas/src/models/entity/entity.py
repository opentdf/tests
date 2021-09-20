"""User model."""

import logging

from ..state import State
from ...errors import MalformedEntityError

logger = logging.getLogger(__name__)


class Entity(object):
    """This class is a DTO for users."""

    @classmethod
    def from_raw(cls, data):
        """Construct a Entity model from a raw dictionary (import)."""
        # check to see if data is already an entity model
        logger.debug("Entity data = %s", data)

        # Load the user up. Use the setter functions to get validation.
        if "userId" in data:
            userId = data["userId"]
        else:
            raise MalformedEntityError(f"Entity could not be created from: {data}")

        # Construct an empty user model
        entity = cls(userId)

        if "email" in data:
            entity.email = data["email"]

        if "name" in data:
            entity.name = data["name"]

        if "attributes" in data:
            entity.attributes = data["attributes"]

        if "state" in data:
            entity.state = State.from_input(data["state"])

        if "pubKey" in data:
            entity.pubKey = data["pubKey"]

        if "nonPersonEntity" in data:
            entity.nonPersonEntity = data["nonPersonEntity"]

        if "status" in data:
            entity.status = State.from_input(data["status"])

        return entity

    def __init__(self, userId, name=None, email=None, nonPersonEntity=False):
        """Initialize an empty user."""
        # Note that protected properties are used where validation is needed;
        # Simple properties otherwise.

        self.__user_id = userId
        self.name = name
        self.email = email
        self.__attributes = set()
        self.__state = State.ACTIVE
        self.pubKey = None
        self.__non_person_entity = nonPersonEntity

    def to_raw(self):
        """Construct a dictionary from a User model (export)."""
        return {
            "userId": self.userId,
            "name": self.name,
            "email": self.email,
            "attributes": self.attributes,
            "nonPersonEntity": self.nonPersonEntity,
            "state": self.state.to_string(),
            "pubKey": self.pubKey,
        }

    def to_json_raw(self):
        """A Dict with None replaced with empty string"""
        name = self.name
        if name is None:
            name = ""
        email = self.email
        if email is None:
            email = ""
        key = self.pubKey
        if key is None:
            key = ""
        return {
            "userId": self.userId,
            "name": name,
            "email": email,
            "attributes": self.attributes,
            "nonPersonEntity": self.nonPersonEntity,
            "state": self.state.to_string(),
            "pubKey": key,
        }

    def __eq__(self, other):
        """Compare entities, userId and email only (the unique columns)

        This comparison ignores attributes.
        """
        return self.userId == other.userId and self.email == other.email

    def equals_with_attributes(self, other):
        """Compare entities, including attributes

        This comparison includes attributes. Helpful for testing.
        """
        return (
            self.userId == other.userId
            and self.email == other.email
            and self.name == other.name
            and self.nonPersonEntity == other.nonPersonEntity
            and self.state == other.state
            and set(self.attributes) == set(other.attributes)
        )

    def __hash__(self):
        """Return a hash integer."""
        return hash((self.__user_id, self.email))

    @property
    def userId(self):
        """Return the id value."""
        return self.__user_id

    @userId.setter
    def userId(self, value):
        """Set id is a noop."""
        pass

    @property
    def state(self):
        """Return the id value."""
        return self.__state

    @state.setter
    def state(self, s):
        """Validate before setting."""
        state_value = State.from_input(s)
        if state_value:
            self.__state = state_value

    @property
    def nonPersonEntity(self):
        """Return the id value."""
        return self.__non_person_entity

    @nonPersonEntity.setter
    def nonPersonEntity(self, npe):
        """Validate before setting - ensure boolean."""
        self.__non_person_entity = bool(npe)

    @property
    def attributes(self):
        """Return the attribute urls."""
        return list(self.__attributes)

    @attributes.setter
    def attributes(self, attributes):
        """Add attributes the attribute urls."""
        # zero out the old attributes
        self.__attributes.clear()
        for attribute in attributes:
            self.add_attribute(attribute)

    def add_attribute(self, value):
        """Add an attribute."""
        self.__attributes.add(value)

    def remove_attribute(self, value):
        """Remove an attribute."""
        self.__attributes.remove(value)

    def has_attribute(self, value):
        """Answer the existence question."""
        return value in self.__attributes
