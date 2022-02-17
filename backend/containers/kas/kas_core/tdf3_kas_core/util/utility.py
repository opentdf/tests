"""Assorted helper functions"""

import sys
import os
import connexion
import string

import logging

logger = logging.getLogger(__name__)


def value_to_boolean(value):
    """Convert an unknown value to boolean. Accepts:
        *   Python or json 'bool' types (returns actual value)
        *   String 'true' or 'false' (case insensitive, returns appropriate boolean)
    None or other values log warning and return False.
    This should move to an EAS/KAS shared library when we add one."""
    if value is None:
        logger.warning("_value_to_boolean: no value received, returning false")
        return False
    if type(value) is bool:
        return value
    try:
        if value.lower() == "false":
            return False
        elif value.lower() == "true":
            return True
    except (AttributeError, ValueError):
        # No Op
        None
    logger.warning(
        "_value_to_boolean: Invalid boolean; defaulting to false. Requires 'true' or 'false' string or json boolean type. Received type: {}, value: {}".format(
            type(value), value
        )
    )
    return False
