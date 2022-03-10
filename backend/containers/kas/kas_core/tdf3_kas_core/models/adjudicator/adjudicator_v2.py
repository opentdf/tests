"""The Adjudicator adjudicates access to the wrapped key."""
import logging

import logging

from tdf3_kas_core.errors import AdjudicatorError
from tdf3_kas_core.errors import AuthorizationError

from tdf3_kas_core.models import ALL_OF
from tdf3_kas_core.models import ANY_OF
from tdf3_kas_core.models import HIERARCHY

from .decision_functions_v2 import all_of_decision
from .decision_functions_v2 import any_of_decision
from .decision_functions_v2 import hierarchy_decision

logger = logging.getLogger(__name__)


class AdjudicatorV2(object):
    """Adjudicator adjudicates.

    All checks to see whether the provided entity claims are sufficient to access the wrapped key split
    are in this model.

    The basic pattern is that failed checks raise errors. These are caught
    at the Web layer and converted to messages of the appropriate form.  If
    the entity claims pass all the tests without raising an error,
    then the authenticated entity who was issued the claims is assumed to be worthy.
    """

    def __init__(self, attribute_policy_cache=None):
        """Initialize with a policy config model."""
        if attribute_policy_cache is None:
            raise AdjudicatorError("Attribute Policy Cache missing")
        self._attribute_policy_cache = attribute_policy_cache

    def can_access(self, policy, claims):

        # TODO BML changes here
        """Determine if the presented entity claims are worthy."""
        # Check to see if this claimset fails the dissem tests.
        self._check_dissem(policy.dissem, claims.user_id)
        # Then check the attributes
        self._check_attributes(policy.data_attributes, claims)
        # Passed all the tests, The entity who was issued this claimset is Worthy!
        return True

    def _check_dissem(self, dissem, entity_id):
        """Test to see if entity is in dissem list.

        If the dissem list is empty then the dissem list is a wildcard
        and the entity passes by default. If the dissem list has elements
        the entity must be on the list.

        This check is something of a hack we need to excise -
        it short-circuits actual ABAC comparison logic, and it
        assumes that only one entity is involved in a key release operation -
        which is not a valid assumption.

        Additionally, it assumes an empty list is equivalent to valid auth - also a
        somewhat suspect assumption.

        Also, we should probably represent the dissem check as Just Another Attribute

        However, for backwards compat we're leaving this here, and assuming for now that the
        OIDC JWT's `preferred_username` field is "the entity" we should be using
        in the query.
        """
        if (dissem.size == 0) | dissem.contains(entity_id):
            return True
        else:
            logger.debug(f"Entity {entity_id} is not on dissem list {dissem.list}")
            raise AuthorizationError("Entity is not on dissem list.")

    def _check_attributes(self, data_attributes, claims):
        """Determine if the presented claims (entity attributes)
        fulfil the requirements of the data attributes

        Both the policy attributes and default rules are used.
        """
        # For every data attrib
        for data_cluster in data_attributes.clusters:
            # Get attrib key
            namespace = data_cluster.namespace

            logger.debug("Checking attribute cluster %s", namespace)

            # Get attrib value(s)
            data_values = data_cluster.values
            logger.debug("Cluster attribute values = %s", data_values)

            # Get policy that matches key
            attr_policy = self._attribute_policy_cache.get(namespace)
            rule = attr_policy.rule

            # We may have multiple entities, each with their own set of
            # entity attributes.
            #
            # So, pass the entire list of entities and their attrs to the decision funcs,
            # and let them resolve them, as how this resolution happens is currently different
            # per decision function: https://docs.google.com/document/d/1LKOD1kT6n3PD211RKVckTarQA7Q6gSUfXYOqy21E1aU/edit?usp=sharing

            # CASE All_OF (ALL OF entities must have ALL OF the data attributes)
            if rule == ALL_OF:
                all_of_decision(data_values, claims)

            # CASE ANY_OF (ANY OF the entities can satisfy the data attribute match requirement)
            if rule == ANY_OF:
                any_of_decision(data_values, claims)

            # CASE HIERARCHY (Lowest heirerchy value among all entities is the "heirarchy value", with None always being the lowest)
            if rule == HIERARCHY:
                hierarchy_decision(
                    data_values, claims, attr_policy.options["order"]
                )

        return True
