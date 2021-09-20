"""Abstract Attribute Service.

Override the methods in this base class to create a plugin service.
"""

import logging
from typing import Dict, List, Union

from ..errors import NotImplementedException
from ..models import AttributeValue

logger = logging.getLogger(__name__)


class AbstractAttributeService(object):
    """Abstract Attribute Service."""

    def create(self, body: dict) -> AttributeValue:
        """Create an attribute record in the store.

        Only the "attribute" url field is required in the body object. The
        other values will be set to defaults.

        Indicate failure by returning None.  Successful calls to this method
        should return the newly created attribute's object.
        """
        raise NotImplementedException

    def read(self) -> List[dict]:
        """Read all attribute records."""

    def retrieve(
        self, attribute_urls: List[str] = None, kas_certificate: str = None
    ) -> List[AttributeValue]:
        """Retrieve list of attribute records by urls.

        :param attribute_urls: List of attribute values to retrieve. If attribute_urls argument is missing
            or None the method returns all attributes.
        :param kas_certificate: KAS Public key to use
        :return list of jwts or attribute_value objects for the attributes retrieved.

        Indicate failure by returning an empty list.  Successful calls should
        return a list of attribute objects. Order is not preserved.
        """
        raise NotImplementedException

    def retrieve_jwt(
        self, attribute_urls: List[str] = None, kas_certificate: str = None
    ) -> List[Dict[str, str]]:
        """Retrieve list of attribute records by urls, as jwt dicts"""
        raise NotImplementedException

    def delete(self, attribute_url: str) -> AttributeValue:
        """Select an attribute value by URL and set status to inactive

        :param attribute_url: The url of the attribute to delete
        :return return attribute object if deleted raise NotFound if doesn't exist."""
        raise NotImplementedException

    def update(self, attr_value: AttributeValue) -> AttributeValue:
        """Update an attribute record. Won't update url because that is identity column.

        :param attr_value: An attribute_value object with the new values.
        :param as_jwt: Default is true, to return attributes as a list of jwts.
                       If false, return a list of AttributeValue objects
        :return attribute_value object for the attribute successfully updated, or None for failure."""
        raise NotImplementedException

    def get_kas_public_key(self) -> str:
        raise NotImplementedException

    def get_values_for_name(self, namespace: str, name: str) -> List[dict]:
        """Read all attribute values for this attribute name."""
        raise NotImplementedException
