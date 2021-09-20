import logging
from .sql import EntityAttributeRelationshipServiceSQL
from .abstract_entity_attr_rel import AbstractEntityAttributeRelationshipService

logger = logging.getLogger(__name__)


def setup_entity_attr_rel_service() -> AbstractEntityAttributeRelationshipService:
    """Factory Method for EntityAttributeRelationshipService."""
    logger.debug(f"Creating EntityAttributeRelationshipService")
    # Select the service type and instantiate the services.
    return EntityAttributeRelationshipServiceSQL()
