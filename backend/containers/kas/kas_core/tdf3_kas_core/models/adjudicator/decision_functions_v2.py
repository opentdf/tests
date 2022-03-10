"""The decision functions decide access."""

import logging

from tdf3_kas_core.errors import AuthorizationError

logger = logging.getLogger(__name__)


def all_of_decision(data_values, entity_claims):
    """Test all-of type attributes."""
    logger.debug("All-of decision function called")

    for dv in data_values:
        logger.debug("DV attrib: %s", dv.attribute)
        logger.debug(entity_claims.entity_attributes)
        for entity_id, entity_attributes in entity_claims.entity_attributes.items():
            ent_attr_cluster = entity_attributes.cluster(dv.namespace)
            if ent_attr_cluster is None:
                logger.debug(f"All-of criteria NOT satisfied for entity: {entity_id} - lacked attribute")
                raise AuthorizationError("AllOf not satisfied")
            if not data_values <= ent_attr_cluster.values:
                logger.debug(f"All-of criteria NOT satisfied for entity: {entity_id} - wrong attribute value")
                raise AuthorizationError("AllOf not satisfied")
    return True

def any_of_decision(data_values, entity_claims):
    """Test any_of type attributes."""
    logger.debug("Any-of decision function called")

    for dv in data_values:
        found_dv_match = False
        logger.debug("DV attrib: %s", dv.attribute)
        for entity_id, entity_attributes in entity_claims.enntity_attributes.items():
            ent_attr_cluster = entity_attributes.cluster(dv.namespace)

            if ent_attr_cluster is None:
                logger.debug(f"Any-of criteria not satisfied for attr: {dv.attribute} on entity: {entity_id} - keep looking")
            else:
                intersect = data_values & ent_attr_cluster.values
                if len(data_values) == 0 or len(intersect) > 0:
                    logger.debug(f"Any-of criteria satisfied for attr: {dv.attribute} on entity: {entity_id}")
                    found_dv_match = True

        if not found_dv_match:
            logger.debug(f"Any-of criteria not satisfied - no entity in claims entitled with {dv.attribute}")
            raise AuthorizationError("AnyOf not satisfied")
        else:
            return True

def hierarchy_decision(data_values, entity_claims, order):
    """Test hierarchy decision function."""
    logger.debug("Hierarchical decision function called")

    # TODO this is a preexisting check - but why would we ever have more than one data value?
    # <attrnamespace>/<attrvalue> would be unique in all cases that matter to a PDP.
    if len(data_values) != 1:
        raise AuthorizationError("Hiearchy - must be one data value")
    data_value = next(iter(data_values))
    if data_value.value not in order:
        raise AuthorizationError("Hiearchy - data value not in attrib policy")
    data_rank = order.index(data_value.value)

    merged_entity_attr_values = set()

    #Mush all the entity attr values for this namespace into a single set,
    #then calc order on least-significant one
    for entity_id, entity_attributes in entity_claims.entity_attributes.items():
        # Get entity attrib key that == data attrib key
        ent_attr_cluster = entity_attributes.cluster(data_value.namespace)
        # Add a null value if no value is found - for purposes of Hierarchy comparison,
        # entity with "no value" always counts one lower than the lowest "valid" value in a
        # hierarchy comparison - that is, an automatic fail.

        if ent_attr_cluster is None:
            merged_entity_attr_values.add(None)
        else:
            merged_entity_attr_values.update(ent_attr_cluster.values)
        logger.debug("Attribute entity values for entity {} = {}".format(entity_id, merged_entity_attr_values))


    # Compute the rank of the entity attr value against the rank of the data value
    # While we only ever compare against a single value, we may have several
    # entity values to deal with - so we go with the value that has the least-significant index
    least_ent_rank = 0
    for val in merged_entity_attr_values:
        if val is None or val.value not in order:
            raise AuthorizationError("Hierarchy - entity missing hierarchy value, which is an automatic hierarchy failure")
        value_rank = order.index(val.value)
        print(f"VAL IS {value_rank} AND LEAST IS {least_ent_rank}")
        if value_rank >= least_ent_rank:
            least_ent_rank = value_rank

    # Compare the ranks to determine value satisfaction

    print(f"DATA VAL IS {data_rank} AND LEAST IS {least_ent_rank}")
    if least_ent_rank <= data_rank:
        logger.debug("Hierarchical criteria satisfied")
        return True

    # Y
    logger.debug("Hierarchical criteria not satisfied")
    raise AuthorizationError("Hierarchy - entity attribute value rank too low")
