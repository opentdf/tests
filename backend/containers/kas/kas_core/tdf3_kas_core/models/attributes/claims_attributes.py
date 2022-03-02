"""ClaimsAttributes."""

import logging

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_set import AttributeSet
from .attribute_value import AttributeValue

logger = logging.getLogger(__name__)


class ClaimsAttributes(AttributeSet):
    """ClaimsAttributes."""

    # TODO I don't understand why we have/handle attribute objects, and not just flat strings.
    @classmethod
    def create_from_raw(cls, raw_claims_attributes):
        """Construct an ClaimsAttribute from raw data (dict)."""
        ea = cls()
        for attributeObj in raw_claims_attributes:
            if "attribute" in attributeObj:
                ea.add(AttributeValue(attributeObj['attribute']))
            elif "url" in attributeObj:
                logger.warning("DEPRECATED - attribute 'url' should be 'attribute'")
                ea.add(AttributeValue(attributeObj['url']))
            else:
                msg = f"'attribute' field missing = {attribute}"
                logger.error(msg)
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise InvalidAttributeError(msg)

        return ea

    # TODO I don't understand why we have/handle attribute objects, and not just flat strings.
    @classmethod
    def create_from_list(cls, attr_list):
        """Load attributes from a list of attribute objects."""
        ea = cls()
        for attr_obj in attr_list:
            ea.add(AttributeValue(attr_obj['attribute']))
        return ea
