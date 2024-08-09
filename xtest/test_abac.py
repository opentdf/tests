import filecmp
import random
import string

import abac
import tdfs


def test_namespaces_list(otdfctl):
    ns = abac.namespace_list(otdfctl)
    assert len(ns) >= 4


def test_attribute_create(otdfctl):
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = abac.namespace_create(otdfctl, random_ns)
    anyof = abac.attribute_create(
        otdfctl, ns, "free", abac.AttributeRule.ANY_OF, ["1", "2", "3"]
    )
    allof = abac.attribute_create(
        otdfctl, ns, "strict", abac.AttributeRule.ALL_OF, ["1", "2", "3"]
    )
    assert anyof != allof


def test_scs_create(otdfctl):
    c = abac.Condition(
        subject_external_selector_value=".clientId",
        operator=abac.SubjectMappingOperatorEnum.IN,
        subject_external_values=["opentdf-sdk"],
    )
    cg = abac.ConditionGroup(
        boolean_operator=abac.ConditionBooleanTypeEnum.OR, conditions=[c]
    )

    sc = abac.scs_create(
        otdfctl,
        [abac.SubjectSet(condition_groups=[cg])],
    )
    assert len(sc.subject_sets) == 1


def test_autoconfigure_one_attribute(otdfctl, tmp_dir, pt_file):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = abac.namespace_create(otdfctl, random_ns)
    anyof = abac.attribute_create(
        otdfctl, ns, "letra", abac.AttributeRule.ANY_OF, ["alpha", "beta", "gamma"]
    )
    alpha, beta, gamma = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"
    assert gamma.value == "gamma"

    # Then assign it to all clientIds = opentdf-sdk
    sc = abac.scs_create(
        otdfctl,
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = abac.scs_map(otdfctl, sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_alpha = abac.kas_registry_create_if_not_present(
        otdfctl, "http://localhost:8080", "../platform/kas-cert.pem"
    )
    abac.grant_assign_value(otdfctl, kas_entry_alpha, alpha)

    kas_entry_beta = abac.kas_registry_create_if_not_present(
        otdfctl, "http://localhost:8282", "../platform/kas-cert.pem"
    )
    abac.grant_assign_value(otdfctl, kas_entry_beta, beta)

    # We have a grant for alpha to localhost kas. Now try to use it...
    ct_file = f"{tmp_dir}test-abac.tdf"
    tdfs.encrypt(
        "go",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[f"https://{random_ns}/attr/letra/value/alpha"],
    )

    rt_file = f"{tmp_dir}test-abac.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_double_kas(otdfctl, tmp_dir, pt_file):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = abac.namespace_create(otdfctl, random_ns)
    allof = abac.attribute_create(
        otdfctl, ns, "ot", abac.AttributeRule.ANY_OF, ["alef", "bet", "gimmel"]
    )
    alef, bet, gimmel = allof.values
    assert alef.value == "alef"
    assert bet.value == "bet"
    assert gimmel.value == "gimmel"

    # Then assign it to all clientIds = opentdf-sdk
    sc = abac.scs_create(
        otdfctl,
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm1 = abac.scs_map(otdfctl, sc, alef)
    assert sm1.attribute_value.value == "alef"
    sm2 = abac.scs_map(otdfctl, sc, bet)
    assert sm2.attribute_value.value == "bet"
    # Now assign it to the current KAS
    kas_entry_alpha = abac.kas_registry_create_if_not_present(
        otdfctl, "http://localhost:8080", "../platform/kas-cert.pem"
    )
    abac.grant_assign_value(otdfctl, kas_entry_alpha, alef)

    kas_entry_beta = abac.kas_registry_create_if_not_present(
        otdfctl, "http://localhost:8282", "../platform/kas-cert.pem"
    )
    abac.grant_assign_value(otdfctl, kas_entry_beta, bet)

    # We have a grant for alpha to localhost kas. Now try to use it...
    ct_file = f"{tmp_dir}test-abac-double.tdf"
    tdfs.encrypt(
        "go",
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt="ztdf",
        attr_values=[
            f"https://{random_ns}/attr/ot/value/alef",
            f"https://{random_ns}/attr/ot/value/bet",
        ],
    )

    rt_file = f"{tmp_dir}test-abac-double.untdf"
    tdfs.decrypt("go", ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
