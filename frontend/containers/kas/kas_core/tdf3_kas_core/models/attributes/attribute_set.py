"""AttributeSet - Container class for values and clusters."""

import logging

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_value import AttributeValue
from .attribute_cluster import AttributeCluster

logger = logging.getLogger(__name__)


class AttributeSet(object):
    """The AttributeSet Classs.

    Attribute sets look like they are holding values, but internally they
    contain clusters of values.  The clusters mirror the AttributePolicy
    instances in the AttributePolicyCache.  The AttributeSet is built this way
    because the decision logic on access is conducted at the cluster level.
    """

    def __init__(self):
        """Construct an empty attribute set.

        The main data structure is a dictionary of AttributeCluster instances.
        """
        self.__clusters = {}

    @property
    def values(self):
        """Return an immutable set of AttributeValues.

        This is a fairly expensive operation. Use sparingly. If a set clone
        is needed do it directly at the AttributeCluster level.
        """
        values = set()
        for cluster in self.__clusters.values():
            values = values | cluster.values
        return frozenset(values)

    @values.setter
    def values(self, data):
        """Do nothing. Setter is a noop."""
        pass

    @property
    def n_values(self):
        """Return the number of values in the AttributeSet."""
        count = 0
        for cluster in self.__clusters.values():
            count = count + cluster.size
        return count

    @property
    def n_clusters(self):
        """Return the nubmer of clusters in the AttributeSet."""
        count = 0
        for cluster in self.__clusters.values():
            count = count + cluster.size
        return count

    # ======== Values CRUD ==================

    def add(self, attr):
        """Add/Overwrite an Attribute."""
        if not isinstance(attr, AttributeValue):
            raise InvalidAttributeError("Not an AttributeValue")
        if attr.namespace not in self.__clusters:
            self.__clusters[attr.namespace] = AttributeCluster(attr.namespace)
        self.__clusters[attr.namespace].add(attr)
        return attr

    def get(self, descriptor):
        """Get an AttributeValue."""
        # Start by creating an AttributeValue to parse the descriptor string
        # using the latest code. Doing this directly by parsing descriptor
        # risks bypassing validation checks on the descriptor string.
        attr = AttributeValue(descriptor)
        # Find the cluster that would hold the AttributeValue, if any
        if attr.namespace in self.__clusters:
            # ask that cluster to return the AttributeValue
            return self.__clusters[attr.namespace].get(descriptor)
        # otherwise return none
        return None

    def remove(self, descriptor):
        """Remove an Attribute."""
        # remove from policy cluster.  Start by creating an AttributeValue
        # to parse the descriptor string (with the latest code).  Doing this
        # directly by parsing descriptor would be slightly faster, but also
        # much riskier because it would bypass the validation checks in the
        # AttributeValue constructor.
        attr = AttributeValue(descriptor)
        # Remove the value from the cluster
        if attr.namespace in self.__clusters:
            return self.__clusters[attr.namespace].remove(descriptor)
        return None

    @property
    def clusters(self):
        """Return a set of cluster objects."""
        return frozenset(self.__clusters.values())

    @property
    def cluster_namespaces(self):
        """Return the cluster namespaces as a list."""
        return self.__clusters.keys()

    def cluster(self, namespace):
        """Get the AttributeCluster for this attribute namespace."""
        if namespace in self.__clusters:
            return self.__clusters[namespace]
        return None
