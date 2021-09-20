"""Setup the services."""

import json
import logging
import os
from typing import List

from .abstract_entity_attr_rel import AbstractEntityAttributeRelationshipService
from .abstract_entity_service import AbstractEntityService
from .sql import EntityServiceSql
from ..errors import EntityExistsError

logger = logging.getLogger(__name__)


def get_initial_entities(path: str) -> List[dict]:
    """Get the initial users set from the config directory."""
    # Pull the JSON string from the users.json config file
    logger.debug("Users path = %s", path)
    with open(path, "r") as u_file:
        users_json = u_file.read()
        logger.debug("Users json = %s", users_json)

    return json.loads(users_json)


def setup_entity_service(
    ear_service: AbstractEntityAttributeRelationshipService,
    initial_values_path: str = None,
) -> AbstractEntityService:
    """Factory and initial data loader for Entity Service"""
    logger.debug("User Service")
    assert isinstance(ear_service, AbstractEntityAttributeRelationshipService)
    entity_service: AbstractEntityService = EntityServiceSql(ear_service)

    logger.debug("Entity Service = %s", entity_service)

    # Load up the initial values from JSON
    if initial_values_path:
        users_path = initial_values_path
    else:
        users_path = os.environ.get(
            "EAS_USERS_JSON", os.path.join("config", "users.json")
        )
    users = get_initial_entities(users_path)
    logger.debug("Initial users = %s", users)

    # Assemble a dict to represent the users.  Key off of id.
    for user in users:
        try:
            entity_service.create(user)
        except EntityExistsError:
            logger.info("user already loaded")

    return entity_service
