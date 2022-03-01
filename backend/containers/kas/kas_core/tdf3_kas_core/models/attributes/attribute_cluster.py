"""Attributes, plural."""

import logging

from tdf3_kas_core.errors import InvalidAttributeError
from tdf3_kas_core.validation import attr_namespace_check

from .attribute_value import AttributeValue

logger = logging.getLogger(__name__)


class AttributeCluster(object):
    """The AttributeCluster Classs."""

    def __init__(self, namespace):
        """Construct an empty attribute cluster with a namespace string."""
        if not namespace:
            raise InvalidAttributeError("No namespace string")
        if not attr_namespace_check.match(namespace):
            raise InvalidAttributeError(namespace)
        self.__namespace = namespace
        self.__values = {}

    @property
    def namespace(self):
        """Return the namespace for the cluster."""
        return self.__namespace

    @namespace.setter
    def namespace(self, data):
        """Do nothing. Setter is a noop."""
        pass

    @property
    def values(self):
        """Return an immutable set of the values."""
        return frozenset(self.__values.values())

    @values.setter
    def values(self, data):
        """Do nothing. Setter is a noop."""
        pass

    @property
    def size(self):
        """Return the number of values in the cluster."""
        return len(self.__values)

    # ======== Values CRUD ==================

    def add(self, attr):
        """Add/Overwrite an AttributeValue."""
        # Add AttributeValue to __values
        if not isinstance(attr, AttributeValue):
            raise InvalidAttributeError("Not an AttributeValue")
        self.__values[attr.attribute] = attr
        return attr

    def get(self, attribute):
        """Get an AttributeValue."""
        if attribute in self.__values:
            return self.__values[attribute]
        return None

    def remove(self, attribute):
        """Remove an Attribute."""
        if attribute in self.__values:
            removed = self.__values[attribute]
            del self.__values[attribute]
            return removed
        return None
