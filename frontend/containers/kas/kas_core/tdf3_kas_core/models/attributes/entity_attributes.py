"""EntityAttributes."""

import logging

import logging

from tdf3_kas_core.authorized import unpack_rs256_jwt

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_set import AttributeSet
from .attribute_value import AttributeValue

logger = logging.getLogger(__name__)


class EntityAttributes(AttributeSet):
    """EntityAttributes."""

    @classmethod
    def create_from_raw(cls, raw_entity_attributes, aa_public_key):
        """Construct an EntityAttribute from raw data (JWT)."""
        ea = cls()
        for attribute in raw_entity_attributes:
            # decode the JWT. Throws an error if JWT does not check out
            attr_obj = unpack_rs256_jwt(attribute["jwt"], aa_public_key)
            if "attribute" in attr_obj:
                ea.add(AttributeValue(attr_obj["attribute"]))
            elif "url" in attr_obj:
                logger.warning("DEPRECATED - attribute 'url' should be 'attribute'")
                ea.add(AttributeValue(attr_obj["url"]))
            else:
                msg = f"'attribute' field missing = {attr_obj}"
                logger.error(msg)
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise InvalidAttributeError(msg)

        return ea

    @classmethod
    def create_from_list(cls, attr_list):
        """Load attributes from a list of raw values."""
        ea = cls()
        for attr_value in attr_list:
            ea.add(AttributeValue(attr_value["attribute"]))
        return ea
