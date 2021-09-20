"""Setup the services."""

import json
import logging
import os
from typing import List

from .abstract_attribute_service import AbstractAttributeService
from .sql import AttributeServiceSql
from ..eas_config import EASConfig
from ..errors import AttributeExistsError
from ..util.keys.get_keys_from_disk import get_key_using_config

logger = logging.getLogger(__name__)


eas_config = EASConfig.get_instance()

WORKING_DIR = os.getcwd()
CONFIG_PATH = os.path.join(WORKING_DIR, "config")


def get_initial_attribute_urls(path: str) -> List[dict]:
    """Get the initial attributes set from the config directory."""
    # Pull the JSON string from the users.json config file
    logger.debug("Attribute urls path = %s", path)

    # Read the urls
    with open(path, "r") as u_file:
        urls_json = u_file.read()

    urls = json.loads(urls_json)

    logger.debug("URLS = %s", urls)
    return urls


def setup_attribute_service(
    *, eas_private_key: str = "", kas_url: str = "", kas_certificate: str = ""
) -> AbstractAttributeService:
    """Factory and initial data loader for attribute service.

    Default implementation is SQL (SQLite)."""
    if not eas_private_key:
        eas_private_key = get_key_using_config("EAS_PRIVATE_KEY")

    if not kas_certificate:
        kas_certificate = get_key_using_config("KAS_CERTIFICATE")

    if not kas_url:
        kas_url = eas_config.get_item("KAS_DEFAULT_URL")

    assert eas_private_key is not None
    # Throws error if type is not recognized
    attribute_service: AbstractAttributeService = AttributeServiceSql(
        eas_private_key=eas_private_key,
        default_kas_certificate=kas_certificate,
        default_kas_url=kas_url,
    )

    logger.debug("Attribute Service = %s", attribute_service)

    # Load up the initial values from JSON
    attribute_urls_path = os.environ.get(
        "EAS_ATTRIBUTES_JSON", os.path.join(CONFIG_PATH, "attribute_urls.json")
    )
    attributes = get_initial_attribute_urls(attribute_urls_path)
    logger.debug("Initial attributes = %s", attributes)

    # Assemble a dict to represent the users.  Key off of id.
    for url in attributes:
        try:
            attribute_service.create({"attribute": url})
        except AttributeExistsError as e:
            logger.warning(e.message)

    return attribute_service
