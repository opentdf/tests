"""AttributePolicy."""

import logging

from tdf3_kas_core.errors import AttributePolicyConfigError

from tdf3_kas_core.validation import attr_namespace_check

logger = logging.getLogger(__name__)

ALL_OF = "allOf"
ANY_OF = "anyOf"
HIERARCHY = "hierarchy"

DEFAULT = ALL_OF

TYPE_ENUMS = [ALL_OF, ANY_OF, HIERARCHY]


class AttributePolicy(object):
    """The AttributePolicy Classs.

    The AttributePolicy class represents an attribute policy; a rule or a set
    of rules for deciding authorization at the attribute namespace level.
    """

    def __init__(self, namespace=None, rule=None, **kwargs):
        """Initialize AttributePolicy with an attribute namespace string."""
        # Check and remember the namespace for the policy
        if not namespace:
            raise AttributePolicyConfigError("No namespace string")
        if not attr_namespace_check.match(namespace):
            logger.error("Attribute policy config error for namespace [%s]", namespace)
            return
        self.__namespace = namespace

        # Check and remember the rule for the policy
        if rule is None:
            rule = ALL_OF  # Defaults to AllOf. Covers singleton caseself.

        if rule not in TYPE_ENUMS:
            raise AttributePolicyConfigError(
                f"Attribute policy rule '{rule}' is invalid"
            )

        self.__rule = rule

        # Check and remember the keyword options
        self.__options = {}
        if rule == HIERARCHY:
            if "order" not in kwargs:
                raise AttributePolicyConfigError(
                    "Failed to create hierarchy policy - no order array"
                )
            # check for string
            order = []
            for val in kwargs["order"]:
                order.append(val)
            self.__options["order"] = tuple(order)

    def __eq__(self, other):
        """Return equality of equal but different objects."""
        return self.namespace == other.namespace

    def __hash__(self):
        """Hash function so identical objects have identical hashes."""
        return hash(self.namespace)

    def __str__(self):
        return f"namespace: {self.__namespace}, rule: {self.__rule}, options: {self.__options}"

    @property
    def namespace(self):
        """Getter for namespace property."""
        return self.__namespace

    @namespace.setter
    def namespace(self, new_value):
        """Setter for namespace property. Read-only, so noop."""
        pass

    @property
    def rule(self):
        """Getter for rule property."""
        return self.__rule

    @rule.setter
    def rule(self, new_value):
        """Setter for rule property is a noop. Read-only."""
        pass

    @property
    def options(self):
        """Getter for options property."""
        return self.__options

    @options.setter
    def options(self, new_options):
        """Setter for options property is a noop. Read-only."""
        pass
