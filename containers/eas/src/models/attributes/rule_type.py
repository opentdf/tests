import logging
from enum import Enum

logger = logging.getLogger(__name__)

enum_to_string = {"ANY_OF": "anyOf", "ALL_OF": "allOf", "HIERARCHY": "hierarchy"}

string_to_enum = {"anyOf": "ANY_OF", "allOf": "ALL_OF", "hierarchy": "HIERARCHY"}


class RuleType(Enum):
    """
        RuleType:
      type: string
      enum: [anyOf, allOf, hierarchy]
      example: anyOf
    UserId:
      type: string
      example: user@virtru.com
    Version:
      type: object
      properties:
        version:
          type: string
          example: "0.0.0"

    """

    ANY_OF = 1
    ALL_OF = 2
    HIERARCHY = 3

    @staticmethod
    def from_string(s):
        """Take string input and return RuleType enum. Throws KeyError on invalid input."""
        # handle mixed case strings
        if s in string_to_enum:
            return RuleType[string_to_enum[s]]
        # handle ENUM names
        return RuleType[s]

    @staticmethod
    def from_input(rule):
        """Given RuleType object, string, or int, Return a valid rule
        :param rule: Accepts object, string, or int representation of RuleType
        :return: valid RuleType object
        """
        if isinstance(rule, RuleType):
            return rule
        elif isinstance(rule, int):
            return RuleType[rule]
        else:
            return RuleType.from_string(rule)

    def to_string(self):
        return enum_to_string[self.name]
