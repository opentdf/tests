"""The Adjudicator adjudicates access to the wrapped key."""
import logging

import logging

from tdf3_kas_core.errors import AdjudicatorError
from tdf3_kas_core.errors import AuthorizationError

from tdf3_kas_core.models import ALL_OF
from tdf3_kas_core.models import ANY_OF
from tdf3_kas_core.models import HIERARCHY

from .decision_functions import all_of_decision
from .decision_functions import any_of_decision
from .decision_functions import hierarchy_decision

logger = logging.getLogger(__name__)


class Adjudicator(object):
    """Adjudicator adjudicates.

    All checks to see whether the entity can access the wrapped key split
    are in this model.

    The basic pattern is that failed checks raise errors.  These are caught
    at the Web layer and converted to messages of the appropriate form.  If
    the Entity passes all the tests without raising an error then it is
    assumed to be worthy.
    """

    def __init__(self, attribute_policy_cache=None):
        """Initialize with a policy config model."""
        if attribute_policy_cache is None:
            raise AdjudicatorError("Attribute Policy Cache missing")
        self._attribute_policy_cache = attribute_policy_cache

    def can_access(self, policy, entity):
        """Determine if the entity is worthy."""
        # Check to see if this entity fails the dissem tests.
        self._check_dissem(policy.dissem, entity.user_id)
        # Then check the attributes
        self._check_attributes(policy.data_attributes, entity.attributes)
        # Passed all the tests, The Entity is Worthy!
        return True

    def _check_dissem(self, dissem, entity_id):
        """Test to see if entity is in dissem list.

        If the dissem list is empty then the dissem list is a wildcard
        and the entity passes by default. If the dissem list has elements
        the entity must be on the list.
        """
        if (dissem.size == 0) | dissem.contains(entity_id):
            return True
        else:
            logger.debug(f"Entity {entity_id} is not on dissem list {dissem.list}")
            raise AuthorizationError("Entity is not on dissem list.")

    def _check_attributes(self, data_attributes, entity_attributes):
        """Determine if the Entity's attributes are worthy.

        Both the policy attributes and default rules are used.
        """
        for data_cluster in data_attributes.clusters:
            namespace = data_cluster.namespace

            logger.debug("Checking attribute cluster %s", namespace)

            data_values = data_cluster.values
            logger.debug("Cluster attribute values = %s", data_values)

            attr_policy = self._attribute_policy_cache.get(namespace)

            entity_cluster = entity_attributes.cluster(namespace)
            if entity_cluster is None:
                msg = f"Not authorized; entity fails on {namespace}"
                logger.error(msg)
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise AuthorizationError(msg)

            entity_values = entity_cluster.values
            logger.debug("Attribute entity values = %s", entity_values)

            rule = attr_policy.rule

            # CASE All_OF
            if rule == ALL_OF:
                all_of_decision(data_values, entity_values)

            # CASE All_OF
            if rule == ANY_OF:
                any_of_decision(data_values, entity_values)

            # CASE HIERARCHY
            if rule == HIERARCHY:
                hierarchy_decision(
                    data_values, entity_values, attr_policy.options["order"]
                )

        return True
