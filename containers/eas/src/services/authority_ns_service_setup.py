"""Setup the service."""

import logging
from typing import List

from .abstract_authority_ns_service import AbstractAuthorityNamespaceService
from .sql.authority_ns_service_sql import AuthorityNamespaceSql
from ..eas_config import EASConfig
from ..errors import AuthorityNamespaceExistsError

logger = logging.getLogger(__name__)
eas_config = EASConfig.get_instance()


def get_default_authority_namespaces() -> List[dict]:
    """Get the initial namespace."""
    namespace = eas_config.get_item("DEFAULT_NAMESPACE")

    namespaces = [{"namespace": namespace, "isDefault": True}]

    logger.debug("Initial namespace = %s", namespaces)
    return namespaces


def setup_authority_ns_service(
    *, initial_values_path: str = None
) -> AbstractAuthorityNamespaceService:
    """Set up the services."""
    namespace_service = AuthorityNamespaceSql()

    logger.debug("Authority Namespace Service = %s", namespace_service)

    # Load up the default namespace
    namespaces = get_default_authority_namespaces()
    logger.debug("Default authority namespace = %s", namespaces)

    # We shouldn't need to load up any more authority namespaces.
    # Instead, during attribute_name_service_setup, when attribute names are created
    # it should automatically create the authority namespace

    # Assemble a dict to represent the namespaces.
    for namespace in namespaces:
        try:
            namespace_service.create(namespace)
        except AuthorityNamespaceExistsError:
            logger.info("namespace already loaded")

    return namespace_service
