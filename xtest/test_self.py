import random
import string

import pytest
import abac


otdfctl = abac.OpentdfCommandLineTool()


@pytest.mark.req("BR-102")  # Environment setup
@pytest.mark.cap(feature="cli-tools")
def test_namespaces_list() -> None:
    ns = otdfctl.namespace_list()
    assert len(ns) >= 4


@pytest.mark.req("BR-102")  # Environment setup
@pytest.mark.cap(feature="cli-tools", policy="abac")
def test_attribute_create() -> None:
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    anyof = otdfctl.attribute_create(
        ns, "free", abac.AttributeRule.ANY_OF, ["1", "2", "3"]
    )
    allof = otdfctl.attribute_create(
        ns, "strict", abac.AttributeRule.ALL_OF, ["1", "2", "3"]
    )
    assert anyof != allof


@pytest.mark.req("BR-102")  # Environment setup
@pytest.mark.cap(feature="cli-tools", policy="abac")
def test_scs_create() -> None:
    c = abac.Condition(
        subject_external_selector_value=".clientId",
        operator=abac.SubjectMappingOperatorEnum.IN,
        subject_external_values=["opentdf-sdk"],
    )
    cg = abac.ConditionGroup(
        boolean_operator=abac.ConditionBooleanTypeEnum.OR, conditions=[c]
    )

    sc = otdfctl.scs_create(
        [abac.SubjectSet(condition_groups=[cg])],
    )
    assert len(sc.subject_sets) == 1
