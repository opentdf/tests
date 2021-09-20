"""Attribute Name interface.

This is the attribute module and supports all the REST actions for
Attribute Names. Note the distinction between Attribute Name and
Attribute Values; one Attribute Name is comprised of a classification,
multiple Attribute Values, and a rule.
API configured by connexion via openapi.yml
"""

import logging
from typing import Dict, List, Tuple

from .status import NUM_ITEMS_HEADER, statusify
from ..errors import (
    MalformedAttributeError,
    NotImplementedException,
)
from ..services import AbstractAttributeNameService, ServiceSingleton

logger = logging.getLogger(__name__)


def attr_name_service() -> AbstractAttributeNameService:
    return ServiceSingleton.get_instance().attribute_name_service


@statusify(success=201)
def create(body: List[dict]) -> Tuple[List[dict], Dict[str, int]]:
    """Takes list of dicts representing attribute names. Add one or more attribute names."""
    results = []
    attr_name_svc = attr_name_service()
    for attr_name in body:
        results.append(attr_name_svc.create(attr_name))

    return results, {NUM_ITEMS_HEADER: len(results)}


@statusify
def head(namespace=None):
    """Retrieve an attribute name - header only."""
    attr_name_svc = attr_name_service()
    items = attr_name_svc.find(namespace)
    return None, {NUM_ITEMS_HEADER: len(items)}


@statusify
def get(name: str, namespace: str = ""):
    """Retrieve an attribute name."""
    attr_name_svc = attr_name_service()
    return attr_name_svc.get(namespace, name)


@statusify
def find(namespace=None):
    """Retrieve all attribute names."""
    attr_name_svc = attr_name_service()
    result = attr_name_svc.find(namespace)
    return result, {NUM_ITEMS_HEADER: len(result)}


@statusify
def get_many(body):
    """Retrieve a list of attribute names."""
    attr_name_svc = attr_name_service()
    result = attr_name_svc.get_many(body)
    return result, {NUM_ITEMS_HEADER: len(result)}


@statusify
def update(body: dict, name: str, namespace: str = ""):
    """Update an attribute name."""
    attr_name_svc = attr_name_service()
    return attr_name_svc.update(body, name, namespace)


@statusify
def patch(body: List[dict], namespace=None) -> List[dict]:
    """Update an attribute name (patch)."""
    logger.debug("def patch(body, namespace=None) -> List[dict]:")
    logger.debug(f"body={body}")
    logger.debug(f"namespace={namespace}")
    results = []
    attr_name_svc = attr_name_service()

    data_item: dict
    for data_item in body:
        if not isinstance(data_item, dict):
            raise MalformedAttributeError(
                f"data item is not a dict, instead it is {type(data_item)}"
            )

        if "name" not in data_item:
            raise MalformedAttributeError("'name' missing from attribute name object.")
        # For namespace, first check body then use query param.
        this_namespace = (
            data_item["namespace"] if "namespace" in data_item else namespace
        )
        results.append(
            attr_name_svc.patch(
                attribute_name=data_item["name"],
                namespace=this_namespace,
                body=data_item,
            )
        )
    return results


@statusify
def delete():
    """Delete an attribute name."""
    raise NotImplementedException
