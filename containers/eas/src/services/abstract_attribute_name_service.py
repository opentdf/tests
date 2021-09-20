"""Attribute Name Service SQLite."""

import logging
from typing import List, Optional

from ..errors import NotImplementedException

logger = logging.getLogger(__name__)

# TODO: Refactoring to return object arrays not dicts, see https://github.com/virtru/etheria/pull/182


class AbstractAttributeNameService:
    """Attribute Name Services data connector."""

    def create(self, attribute_name: dict) -> dict:
        """Create a new Attribute Name.

        Return the request body if the operation was successful, otherwise
        raise an error.
        """
        raise NotImplementedException

    def get(self, namespace: str, name: str) -> dict:
        """Retrieve a single Attribute Name."""
        raise NotImplementedException

    def find(self, namespace: str = None) -> List[Optional[dict]]:
        """Retrieve all Attribute Names."""
        raise NotImplementedException

    def get_many(self, uris: List[str]) -> List[dict]:
        """Retrieve a list of attribute names - designed for KAS attribute discovery."""
        raise NotImplementedException

    def update(self, body: dict, attribute_name: str, namespace: str = "") -> dict:
        """Update an attribute name object using the provided body."""
        raise NotImplementedException

    def patch(self, body: dict, attribute_name: str, namespace: str = None) -> dict:
        """Only update fields of attribute name provided in body and return updated attribute name."""
        raise NotImplementedException
