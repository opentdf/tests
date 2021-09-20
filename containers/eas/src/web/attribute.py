"""Attribute interface.

This is the attribute module and supports all the REST actions for the
attribute collection.  API configured by connexion via openapi.yml
"""

import logging

from flask import current_app

from .status import NUM_ITEMS_HEADER, statusify
from ..eas_config import EASConfig
from ..errors import NotFound
from ..models import AttributeValue
from ..services import (
    ServiceSingleton,
    AbstractAttributeNameService,
    AbstractAttributeService,
)

logger = logging.getLogger(__name__)


def attr_service() -> AbstractAttributeService:
    return ServiceSingleton.get_instance().attribute_service


def attr_name_service() -> AbstractAttributeNameService:
    return ServiceSingleton.get_instance().attribute_name_service


@statusify(success=201)
def create(body):
    """Add an attribute."""

    uris = body
    return [attr_service().create({"attribute": u}).to_raw_dict() for u in uris]


@statusify(success=201)
def create_value(body, name="", namespace=""):
    """Add an attribute."""

    return attr_service().create(body).to_raw_dict()


@statusify
def retrieve(body):
    """Retrieve the attributes in the list."""

    attribute_uris = body
    current_app.logger.debug("Retrieving attributes = %s", attribute_uris)
    result = attr_service().retrieve_jwt(attribute_uris)
    return result, {NUM_ITEMS_HEADER: len(result)}


@statusify
def update(body):
    """Update an attribute."""

    current_app.logger.debug("Updating attribute = %s", body)
    attribute_value = AttributeValue.from_raw_dict(body)
    return [attr_service().update(attribute_value).to_raw_dict()]


@statusify
def put(name, value, body):
    """Update an attribute."""
    # TODO: use name, value

    current_app.logger.debug("Updating attribute = %s", body)
    attribute_value: AttributeValue = AttributeValue.from_raw_dict(body)
    attr = attr_service().update(attribute_value)
    return attr.to_raw_dict()


@statusify
def delete(authority, name, value):
    """Delete an attribute. URI is decomposed"""

    attribute_uri = AttributeValue.make_uri(authority, name, value)
    current_app.logger.debug("Deleting attribute = %s", attribute_uri)
    return [attr_service().delete(attribute_uri)]


@statusify
def get_value(name="", value="", namespace=""):
    logger.debug("Web - Attribute Value - get_value()")

    if not namespace:
        namespace = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")
    attr_uri = f"{namespace}/attr/{name}/value/{value}"
    result = attr_service().retrieve([attr_uri])
    if not result:
        raise NotFound(f"{attr_uri} not found")

    attr = result[0]
    attr_raw = attr.to_raw_dict()
    return attr_raw


@statusify
def get_values(namespace=None, name=None):
    logger.debug("Web - Attribute Value - get_values()")
    if not namespace:
        namespace = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")

    result = attr_service().get_values_for_name(namespace, name)
    if not result:
        # are namespace and name valid? this will throw error if not
        attr_name_service().get(namespace, name)
    return result, {NUM_ITEMS_HEADER: len(result)}
