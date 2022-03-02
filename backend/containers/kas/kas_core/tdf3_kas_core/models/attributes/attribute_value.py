"""AttributeValue."""

import logging

from tdf3_kas_core.errors import InvalidAttributeError
from tdf3_kas_core.validation import attr_attribute_check

VALUE_ = "/value/"
ATTR_ = "/attr/"

logger = logging.getLogger(__name__)


class AttributeValue(object):
    """The AttributeValue Classs.

    Attribute values are immutable representations of a specific value of an
    attribute.  They perform compares, are sortable, and so on.

    On the KAS an AttributeValue only needs the URN string "attribute." This
    may change as attribute public keys become more important, but for now only
    the "attribute" string is required.
    """

    def __init__(self, attribute=None):
        """Initialize with a attribute string (aka URL or attribute)."""
        if not attribute:
            raise InvalidAttributeError("No attribute string")
        if not attr_attribute_check.match(attribute):
            raise InvalidAttributeError(f"[{attribute}]")

        first_splits = attribute.split(ATTR_)
        second_splits = first_splits[1].split(VALUE_)

        # Authority namespace is case insensitive
        self._authority = first_splits[0].lower()
        # Name and value are case sensitive
        self._name = second_splits[0]
        self._value = second_splits[1]

        logger.debug("Attribute Authority = %s", self._authority)
        logger.debug("Attribute Name  = %s", self._name)
        logger.debug("Attribute Value     = %s", self._value)

    def __eq__(self, other):
        """Compare self to other for equality."""
        namespace_equal = self.namespace == other.namespace
        value_equal = self.value == other.value
        return namespace_equal and value_equal

    def __hash__(self):
        """Generate a hash value common between all equal instances."""
        return hash((self.namespace, self.value))

    @property
    def namespace(self):
        """Return the fully defined namespace = authority + name name."""
        return f"{self._authority}/attr/{self._name}"

    @namespace.setter
    def namespace(self, new_namespace):
        """Do nothing. Read only."""
        pass

    @property
    def authorityNamespace(self):
        """Return the fully defined namespace = authority + name name."""
        return self._authority

    @property
    def authority(self):
        """Return only the authority portion of the attribute string."""
        return self._authority

    @authority.setter
    def authority(self, new_authority):
        """Do nothing. Read only."""
        pass

    @property
    def name(self):
        """Return the name name of the attribute."""
        return self._name

    @name.setter
    def name(self, new_name):
        """Do nothing (immutable). Read only."""
        pass

    @property
    def value(self):
        """Return the value portion of the attribute string."""
        return self._value

    @value.setter
    def value(self, new_value):
        """Do nothing. Read only."""
        pass

    @property
    def attribute(self):
        """Return the entire attribute string."""
        return self.make_uri(self._authority, self._name, self._value)

    @attribute.setter
    def attribute(self, new_attribute):
        """Do nothing. Read only."""
        pass

    @classmethod
    def make_uri(cls, authority: str, name: str, value: str) -> str:
        return f"{authority}/attr/{name}/value/{value}"
