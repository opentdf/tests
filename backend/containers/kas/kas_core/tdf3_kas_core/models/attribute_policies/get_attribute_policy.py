"""Get Attribute Policy.

This is a stub for now.  It just constructs default AttributePolcies.
It will evolve into an async call to reference endpoint(s), possibly via
plugins.
"""

import logging

from .attribute_policy import AttributePolicy

logger = logging.getLogger(__name__)


def get_attribute_policy(namespace):
    """Get an Attribute Policy."""
    return AttributePolicy(namespace)
