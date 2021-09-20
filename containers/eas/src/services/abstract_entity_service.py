"""User Service SQLite."""

import logging
from typing import Any, Dict, List, Optional

from ..errors import NotImplementedException

logger = logging.getLogger(__name__)


class AbstractEntityService:
    """User Services data connector."""

    def create(self, body: dict) -> dict:
        """Create a new user.

        Return the request body if the operation was successful, otherwise
        raise an error.
        """
        raise NotImplementedException

    def retrieve(
        self, userid_or_email: str, by_email: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a single user."""
        raise NotImplementedException

    def retrieveAll(self) -> List[Optional[Dict[str, Any]]]:
        """Retrieve all users."""
        raise NotImplementedException

    def retrieveAllByQuery(self, query: str) -> List[Optional[Dict[str, Any]]]:
        """Retrieve all users."""
        raise NotImplementedException

    def update(self, body: dict) -> Dict[str, Any]:
        """Update entity record, as selected by userId
        Note that if entity already has attribute in DB but update call doesn't include attribute,
        the attribute will be removed."""
        raise NotImplementedException

    def delete(self, user_id: str) -> Dict[str, Any]:
        """Delete specified user.
        :param user_id ID of specified user
        :return return user object for specified user if deleted raise NotFound if doesn't exist."""
        raise NotImplementedException
