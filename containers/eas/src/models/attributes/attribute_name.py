"""Entity model (former User model.)"""

import logging
from pprint import pprint

from .rule_type import RuleType
from ..state import State
from ...errors import MalformedAttributeError

logger = logging.getLogger(__name__)

ATTR = "/attr/"


class AttributeName(object):
    """The Attribute Name is a grouping of related attribute values.
    An Attribute Nme belongs to an authority namespace and has a rule"""

    def __init__(
        self,
        name,
        authorityNamespace,
        order=None,
        rule=RuleType.ALL_OF,
        state=State.ACTIVE,
    ):
        """
        :param authorityNamespace: String or authorityNamespace object
        :param string name: The name of the attribute (formerly category or classification)
        :param list order: List of values in priority: high to low. (relevant only for hierarchy rules)
        :param rule: RuleType enum object or valid string. Default AllOf
        :param state: State enum or valid integer representation
        """
        if order is None:
            order = []
        self.__authority_namespace = authorityNamespace.lower()  # case insensitivity
        self.__name = name
        self.__order = order
        self.__rule = RuleType.from_input(rule)
        self.__state = State.from_input(state)

    @classmethod
    def from_raw_dict(cls, raw_dict) -> "AttributeName":
        logger.debug("Attribute Name raw dict = %s", raw_dict)

        # Validate input
        if "authorityNamespace" not in raw_dict or "name" not in raw_dict:
            raise MalformedAttributeError("authorityNamespace and name are required")

        order_ = []
        if "order" in raw_dict and isinstance(raw_dict["order"], list):
            order_ = raw_dict["order"]

        state_ = State.ACTIVE
        if "state" in raw_dict and State.from_input(raw_dict["state"]):
            state_ = State.from_input(raw_dict["state"])

        rule_ = RuleType.ALL_OF
        if "rule" in raw_dict and RuleType.from_input(raw_dict["rule"]):
            rule_ = RuleType.from_input(raw_dict["rule"])

        return AttributeName(
            raw_dict["name"],
            raw_dict["authorityNamespace"],
            order=order_,
            rule=rule_,
            state=state_,
        )

    @classmethod
    def from_uri_and_raw_dict(cls, uri, raw_dict) -> "AttributeName":
        """For situations where we need to create a Attribute Name from both a URI
        and an AttributeNameConfig schema dict (like AttributeName schema minus name and namespace)

        :param raw_dict:dict dict without name and namespace
        :param uri:str string with an attribute name uri: http://namespace/attr/name
        """
        logger.debug("Attribute Name raw dict = %s", raw_dict)

        if not isinstance(raw_dict, dict):
            raise MalformedAttributeError("Must be a dictionary object")
        # Validate input
        if not uri:
            raise MalformedAttributeError("uri is required")

        order_ = []
        if "order" in raw_dict and isinstance(raw_dict["order"], list):
            order_ = raw_dict["order"]

        state_ = State.ACTIVE
        if "state" in raw_dict and State.from_input(raw_dict["state"]):
            state_ = State.from_input(raw_dict["state"])

        rule_ = RuleType.ALL_OF
        if "rule" in raw_dict and RuleType.from_input(raw_dict["rule"]):
            rule_ = RuleType.from_input(raw_dict["rule"])

        attr_name = AttributeName.from_uri(uri)
        attr_name.order = order_
        attr_name.rule = rule_
        attr_name.state = state_
        return attr_name

    def to_raw_dict(self) -> dict:
        """Export a raw dict."""
        raw_dict = {
            "name": self.name,
            "authorityNamespace": self.authorityNamespace,
            "rule": self.rule.to_string(),
            "order": self.order,
            "state": self.state.to_string(),
        }
        logger.debug("Exporting raw_dict = %s", raw_dict)
        return raw_dict

    @classmethod
    def from_uri(cls, uri) -> "AttributeName":
        """Generate a basic attribute name object from a URI. Default state, rule and order."""
        logger.debug("Attribute Name uri = %s", uri)
        parts = uri.split("/attr/")

        namespace_ = parts[0]
        name_ = parts[1]

        # TODO: would be nice to use urlparse, but code below is buggy.
        # parsed_uri = urlparse(uri)
        # namespace_ = (parsed_uri.scheme + "://" + parsed_uri.netloc).lower()
        # name_ = parsed_uri.path.lstrip(ATTR)
        return AttributeName(
            authorityNamespace=namespace_,
            name=name_,
        )

    @property
    def authorityNamespace(self):
        """Return the authorityNamespace value."""
        return self.__authority_namespace

    @authorityNamespace.setter
    def authorityNamespace(self, authorityNamespace):
        """Do nothing: Read-only/immutable"""
        pass

    @property
    def name(self):
        """Return the name of the attribute (aka classification or category)."""
        return self.__name

    @name.setter
    def name(self, authorityNamespace):
        """Do nothing. Read-only/Immutable."""
        pass

    @property
    def order(self):
        """Return the authorityNamespace value."""
        return self.__order

    @order.setter
    def order(self, order):
        if isinstance(order, list):
            self.__order = order
        else:
            logger.warning(
                "Order must be a list of string values, received %s instead",
                type(order),
            )

    @property
    def state(self):
        """Return the id value."""
        return self.__state

    @state.setter
    def state(self, s):
        """Validate before setting."""
        state_value = State.from_input(s)
        if state_value:
            self.__state = state_value

    @property
    def rule(self):
        """Return the id value."""
        return self.__rule

    @rule.setter
    def rule(self, r):
        """Validate before setting."""
        rule_value = RuleType.from_input(r)
        if rule_value:
            self.__rule = rule_value

    @property
    def uri(self):
        """Return the full attribute url string."""
        return f"{self.__authority_namespace}/attr/{self.__name}"

    def equals_with_attributes(self, other) -> bool:
        """Compare entities, including attributes

        This comparison includes attributes. Helpful for testing.
        """
        print(f"{__name__}.equals_with_attributes()")
        print(self.to_raw_dict())
        print(other.to_raw_dict())
        return (
            self.authorityNamespace == other.authorityNamespace
            and self.order == other.order
            and self.name == other.name
            and self.rule == other.rule
            and self.state == other.state
        )
