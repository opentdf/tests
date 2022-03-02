"""AttributesCache, a reference for AttributePolicies."""
import logging

from tdf3_kas_core.errors import InvalidAttributeError
from tdf3_kas_core.server_timing import Timing

from .attribute_policy import AttributePolicy
from .attribute_policy import HIERARCHY
from .get_attribute_policy import get_attribute_policy

logger = logging.getLogger(__name__)


class AttributePolicyCache(object):
    """The AttributePolicyCache Class.

    This class caches AttributePolicies.
    """

    def __init__(self):
        """Construct an empty set."""
        self.__policies = {}  # URL keyed dict of AttributePolicies

    @property
    def size(self):
        """Return the number of policies in the cache."""
        return len(self.__policies)

    def load_config(self, attribute_policy_config):
        """Load policies defined in a config dict."""
        if not attribute_policy_config:
            logger.warn("No attribute configs found")
            return
        Timing.start("attribute_load")
        logger.debug(
            "--- Fetch attribute_policy_config  [attribute = %s] ---",
            attribute_policy_config,
        )
        for attribute_object in attribute_policy_config:
            # use the policy constructor to validate the inputs
            authority_namespace = attribute_object["authorityNamespace"]
            attribute_name = attribute_object["name"]
            attribute_name_object = f"{authority_namespace}/attr/{attribute_name}"
            if "rule" in attribute_object:
                # specialize the arguments for the rule
                if attribute_object["rule"] == HIERARCHY:
                    if "order" not in attribute_object:
                        raise InvalidAttributeError(
                            """
                            Failed to create hierarchy policy
                             - no order array
                        """
                        )
                    policy = AttributePolicy(
                        attribute_name_object,
                        rule=attribute_object["rule"],
                        order=attribute_object["order"],
                    )
                else:  # No special options argument list
                    policy = AttributePolicy(
                        attribute_name_object, rule=attribute_object["rule"]
                    )
            else:
                # Use the default rule
                policy = AttributePolicy(attribute_name_object)

            # Add to the cache
            logger.debug("--- cached  [policy = %s] ---", str(policy))
            if policy is not None:
                self.__policies[attribute_name_object] = policy
        Timing.stop("attribute_load")

    def get(self, namespace):
        """Get an AttributePolicy."""
        try:
            count = 2
            while (namespace not in self.__policies) and (count > 0):
                ap = get_attribute_policy(namespace)
                if isinstance(ap, AttributePolicy):
                    self.__policies[namespace] = ap
                count = count - 1

            if namespace not in self.__policies:
                raise Exception()
            return self.__policies[namespace]
        except Exception as e:
            logger.exception(e)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            return None
