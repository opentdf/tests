"""Namespace interface.

This is the namespace module and supports all the REST actions for
namespaces. 
API configured by connexion via openapi.yml
"""

import logging

from flask import current_app

from .status import statusify, NUM_ITEMS_HEADER
from ..services import ServiceSingleton

logger = logging.getLogger(__name__)


@statusify
def get(isDefault=None):
    """Retrieve the namespaces for this EAS."""
    current_app.logger.debug(
        "Retrieve Authority Namespaces where defailt = %s", isDefault
    )
    namespace_service = ServiceSingleton.get_instance().authority_ns_service
    namespaces = namespace_service.retrieve(isDefault=isDefault)
    current_app.logger.debug(
        "Authority Namespaces where defailt = %s: %s", isDefault, namespaces
    )
    return namespaces, {NUM_ITEMS_HEADER: len(namespaces)}


@statusify
def create(body):
    """Add a namespace to this EAS."""
    current_app.logger.debug("Create Authority Namespace with body = %s", body)
    namespace_service = ServiceSingleton.get_instance().authority_ns_service
    namespace = namespace_service.create(body)
    current_app.logger.debug("Authority Namespace created as %s", namespace)
    return namespace
