"""ClaimsAttributes."""

import logging

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_set import AttributeSet
from .attribute_value import AttributeValue

logger = logging.getLogger(__name__)


class ClaimsAttributes(AttributeSet):
    """ClaimsAttributes."""

    # TODO This object model is whack, I don't get why AttributeSet exists
    # We're just putting simple structures in lists, we don't need custom classes for that.
    @classmethod
    def create_from_raw(cls, raw_claims_attributes):
        """Construct a dict of ClaimsAttributes for each entity (keyed by entity ID) from raw data (dict)."""
        entitlements = {}

        logger.debug("RAW CLAIMS IS IS: {}".format(raw_claims_attributes))
        for entitlement in raw_claims_attributes:
            entityname = entitlement['entity_identifier']
            entityattrs = entitlement['entity_attributes']
            logger.debug("ENTITYATTRS IS: {}".format(entityattrs))
            entity_attribute_set = cls()
            for attributeObj in entityattrs:
                if "attribute" in attributeObj:
                    logger.debug("AttributeOBJ IS: {}".format(attributeObj))
                    logger.debug("AttributeOBJ ATTRIB IS: {}".format(attributeObj['attribute']))
                    entity_attribute_set.add(AttributeValue(attributeObj['attribute']))
                elif "url" in attributeObj:
                    logger.warning("DEPRECATED - attribute 'url' should be 'attribute'")
                    entity_attribute_set.add(AttributeValue(attributeObj['url']))
                else:
                    msg = f"'attribute' field missing = {attributeObj}"
                    logger.error(msg)
                    logger.setLevel(logging.DEBUG)  # dynamically escalate level
                    raise InvalidAttributeError(msg)
            entitlements[entityname] = entity_attribute_set

        return entitlements

    @classmethod
    def create_from_list(cls, entity_id, attr_list):
        """Load entity attributes from a list of raw values and a entity identifier"""
        entities = {}
        ea = cls()
        for attr_value in attr_list:
            ea.add(AttributeValue(attr_value["attribute"]))
        entities[entity_id] = ea
        return entities
