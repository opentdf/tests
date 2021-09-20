"""Authority Namespace model."""

import logging

from ...errors import MalformedAuthorityNamespaceError

logger = logging.getLogger(__name__)


class AuthorityNamespace(object):
    """This class is a DTO for authority namespaces."""

    @classmethod
    def from_raw(cls, data):
        """Construct a Authority Namespace model from a raw dictionary (import)."""
        # check to see if data is already an entity model
        logger.debug("Namespace data = %s", data)

        # Load the user up. Use the setter functions to get validation.
        if "namespace" in data and "isDefault" in data:
            namespace = data["namespace"]
            isDefault = data["isDefault"]
            displayName = ""
            if "displayName" in data:
                displayName = data["displayName"]
        else:
            raise MalformedAuthorityNamespaceError(data)

        # Construct a namespace model
        auth_ns = cls(namespace, isDefault, displayName=displayName)

        return auth_ns

    def __init__(self, namespace: str, isDefault: bool, displayName: str = ""):
        """Initialize an empty namespace."""
        if not namespace:
            raise MalformedAuthorityNamespaceError("namespace cannot be null")
        if namespace[-1] == "/":
            namespace = namespace[:-1]
        self.__namespace = namespace.lower()
        self.__is_default = isDefault
        self.__display_name = displayName

    def to_raw(self) -> dict:
        """Construct a dictionary from a AuthorityNamespace model (export)."""
        return {
            "namespace": self.namespace,
            "isDefault": self.isDefault,
            "displayName": self.displayName,
        }

    def __eq__(self, other):
        """Compare namespaces"""
        return self.namespace == other.namespace and self.isDefault == other.isDefault

    def __hash__(self):
        """Return a hash integer."""
        return hash((self.__namespace, self.__is_default))

    @property
    def namespace(self):
        """Return the namespace value."""
        return self.__namespace

    @namespace.setter
    def namespace(self, value):
        """Set namespace is a noop."""
        pass

    @property
    def isDefault(self):
        """Return the isDefault value."""
        return self.__is_default

    @isDefault.setter
    def isDefault(self, value):
        """Set valid isDefault."""
        self.__is_default = value

    @property
    def displayName(self):
        """Return the namespace value."""
        return self.__display_name

    @displayName.setter
    def displayName(self, value):
        """Set namespace is a noop."""
        self.__display_name = value
