"""The decision functions decide access."""

import logging

from tdf3_kas_core.errors import AuthorizationError

logger = logging.getLogger(__name__)


def all_of_decision(data_values, entity_values):
    """Test all-of type attributes."""
    logger.debug("All-of decision function called")
    if data_values <= entity_values:
        logger.debug("All-of criteria satisfied")
        return True
    logger.debug("All-of criteria not satisfied")
    raise AuthorizationError("AllOf not satisfied")


def any_of_decision(data_values, entity_values):
    """Test any_of type attributes."""
    logger.debug("Any-of decision function called")
    intersect = data_values & entity_values
    if len(data_values) == 0 or len(intersect) > 0:
        logger.debug("All-of criteria satisfied")
        return True
    logger.debug("Any-of criteria not satisfied")
    raise AuthorizationError("AnyOf not satisfied")


def hierarchy_decision(data_values, entity_values, order):
    """Test hierarchy decision function."""
    logger.debug("Hierarchical decision function called")
    # Compute the rank of the data_attribute value
    if len(data_values) != 1:
        raise AuthorizationError("Hiearchy - must be one data value")
    data_value = next(iter(data_values))
    if data_value.value not in order:
        raise AuthorizationError("Hiearchy - data value not in attrib policy")
    data_rank = order.index(data_value.value)

    # Compute the rank of the entity_attribute value
    if len(entity_values) != 1:
        raise AuthorizationError("Hierarchy - must be one entity value")
    entity_value = next(iter(entity_values))
    if entity_value.value not in order:
        raise AuthorizationError("Hiearchy - entity value not in attrib policy")
    entity_rank = order.index(entity_value.value)

    # Compare the ranks to determine value satisfaction
    if entity_rank <= data_rank:
        logger.debug("Hierarchical criteria satisfied")
        return True

    logger.debug("Hierarchical criteria not satisfied")
    raise AuthorizationError("Hierarchy - entity value rank too low")
