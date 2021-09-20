"""Setup the service."""

import json
import logging
import os
from typing import Dict, List, Optional

from .sql.attribute_name_service_sql import AttributeNameServiceSQL
from ..eas_config import EASConfig
from ..errors import AttributeExistsError
from ..models import AttributeName
from ..services import (
    AbstractAttributeNameService,
    AbstractAttributeService,
    AbstractAuthorityNamespaceService,
)

logger = logging.getLogger(__name__)
eas_config = EASConfig.get_instance()


def get_initial_names(path: str) -> List[Dict[str, dict]]:
    """Get the initial attribute names set from the config directory."""
    # Pull the JSON string from the attribute_names.json config file
    # TODO: API is standardizing on lists of objects - List[Dict[str, Any]]. This code uses a nested dictionary instead.
    #   Convert this file `config/attribute_names.json` and the code in setup_attribute_name_service() that reads it.
    logger.debug("Attribute Name path = %s", path)
    with open(path, "r") as a_file:
        attr_name_json = a_file.read()
        logger.debug("Attribute Name json = %s", attr_name_json)

    return json.loads(attr_name_json)


def setup_attribute_name_service(
    authority_ns_service: AbstractAuthorityNamespaceService,
    attribute_service: AbstractAttributeService,
    default_namespace: str = "",
    initial_values_path: Optional[str] = None,
) -> AbstractAttributeNameService:
    """Set up the services."""
    logger.debug("Attribute Name Service NS = %s", default_namespace)
    attribute_name_service = AttributeNameServiceSQL(
        authority_ns_service, attribute_service, default_namespace
    )

    logger.debug("Attribute Name Service = %s", attribute_name_service)

    # Load up the initial values from JSON
    if initial_values_path:
        attr_name_path = initial_values_path
    else:
        attr_name_path = os.environ.get(
            "ATTRIBUTE_NAME_JSON", os.path.join("config", "attribute_names.json")
        )
    names: List[Dict[str, dict]] = get_initial_names(attr_name_path)
    logger.debug("Initial attribute names = %s", names)

    for name in names:
        try:
            uri = list(name.keys())[0]
            attr_name = AttributeName.from_uri_and_raw_dict(uri, name[uri])
            attribute_name_service.create(attr_name.to_raw_dict())
        except AttributeExistsError:
            logger.info(
                "attribute name already loaded: [%s]+[%s] => [%s]", name, uri, attr_name
            )

    return attribute_name_service
