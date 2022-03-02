"""Data attributes."""
import logging

import logging

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_set import AttributeSet
from .attribute_value import AttributeValue

logger = logging.getLogger(__name__)


class DataAttributes(AttributeSet):
    """The DataAttributes Classs."""

    @classmethod
    def create_from_raw(cls, raw_list):
        """Create a DataAttributes model from a raw list."""
        da = cls()
        for attr in raw_list:
            da.add(AttributeValue(attr["attribute"]))
        return da

    def load_raw(self, raw_list):
        """Load this instance from raw list.

        Note that there is a breaking change about to happen.
        The 'url' field in the original data attributes spec is about
        to be changed to 'attribute'. Both are acceptable now, but this should
        not last forever.
        """
        for attr_obj in raw_list:
            # Do not import the kasUrl value as the attribute descriptor!!
            if "attribute" in attr_obj:
                self.add(AttributeValue(attr_obj["attribute"]))
            elif "url" in attr_obj:
                logger.warning("DEPRECATED - attribute 'url' should be 'attribute'")
                self.add(AttributeValue(attr_obj["url"]))
            else:
                msg = f"URL field missing from data attribute = {attr_obj}"
                logger.error(msg)
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise InvalidAttributeError(msg)

    def export_raw(self):
        """Export this instance as a raw list."""
        # get a set of AttributeValues
        values = self.values
        lst = []
        for value in values:
            lst.append({"attribute": value.attribute})
        return lst
