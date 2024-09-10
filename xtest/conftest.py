import os
import pytest
import random
import string

import abac


def pytest_addoption(parser):
    parser.addoption(
        "--large",
        action="store_true",
        help="generate a large (greater than 4 GiB) file for testing",
    )
    parser.addoption(
        "--sdks", help="select which sdks to run by default, unless overridden"
    )
    parser.addoption("--sdks-decrypt", help="select which sdks to run for decrypt only")
    parser.addoption("--sdks-encrypt", help="select which sdks to run for encrypt only")
    parser.addoption("--containers", help="which container formats to test")


def pytest_generate_tests(metafunc):
    if "size" in metafunc.fixturenames:
        metafunc.parametrize(
            "size",
            ["large" if metafunc.config.getoption("large") else "small"],
            scope="session",
        )
    if "encrypt_sdk" in metafunc.fixturenames:
        if metafunc.config.getoption("--sdks-encrypt"):
            encrypt_sdks = metafunc.config.getoption("--sdks-encrypt").split()
        elif metafunc.config.getoption("--sdks"):
            encrypt_sdks = metafunc.config.getoption("--sdks").split()
        else:
            encrypt_sdks = ["js", "go", "java"]
        metafunc.parametrize("encrypt_sdk", encrypt_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        if metafunc.config.getoption("--sdks-decrypt"):
            decrypt_sdks = metafunc.config.getoption("--sdks-decrypt").split()
        elif metafunc.config.getoption("--sdks"):
            decrypt_sdks = metafunc.config.getoption("--sdks").split()
        else:
            decrypt_sdks = ["js", "go", "java"]
        metafunc.parametrize("decrypt_sdk", decrypt_sdks)
    if "container" in metafunc.fixturenames:
        if metafunc.config.getoption("--containers"):
            containers = metafunc.config.getoption("--containers").split()
        else:
            containers = ["nano", "ztdf"]
        metafunc.parametrize("container", containers)


@pytest.fixture(scope="module")
def pt_file(tmp_dir, size):
    pt_file = f"{tmp_dir}test-plain-{size}.txt"
    length = (5 * 2**30) if size == "large" else 128
    with open(pt_file, "w") as f:
        for i in range(0, length, 16):
            f.write("{:15,d}\n".format(i))
    return pt_file


@pytest.fixture(scope="module")
def tmp_dir():
    dname = "tmp/"
    isExist = os.path.exists(dname)
    if not isExist:
        os.makedirs(dname)
    return dname


_otdfctl = abac.OpentdfCommandLineTool()


@pytest.fixture(scope="module")
def otdfctl():
    return _otdfctl


@pytest.fixture(scope="module")
def temporary_namespace(otdfctl: abac.OpentdfCommandLineTool):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    return ns

@pytest.fixture(scope="function")
def more_temporary_namespace(otdfctl: abac.OpentdfCommandLineTool):
    # Create a new attribute in a random namespace
    random_ns = "".join(random.choices(string.ascii_lowercase, k=8)) + ".com"
    ns = otdfctl.namespace_create(random_ns)
    return ns


PLATFORM_DIR = os.getenv("PLATFORM_DIR", "../../platform")


def load_cached_kas_keys() -> abac.PublicKey:
    keyset: list[abac.KasPublicKey] = []
    with open(f"{PLATFORM_DIR}/kas-cert.pem", "r") as rsaFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_RSA_2048,
                kid="r1",
                pem=rsaFile.read(),
            )
        )
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem", "r") as ecFile:
        keyset.append(
            abac.KasPublicKey(
                alg=abac.KAS_PUBLIC_KEY_ALG_ENUM_EC_SECP256R1,
                kid="e1",
                pem=ecFile.read(),
            )
        )
    return abac.PublicKey(
        cached=abac.KasPublicKeySet(
            keys=keyset,
        )
    )


@pytest.fixture(scope="session")
def kas_url1():
    return os.getenv("KASURL", "http://localhost:8080/kas")


@pytest.fixture(scope="session")
def kas_url2():
    return os.getenv("KASURL2", "http://localhost:8282/kas")


@pytest.fixture(scope="module")
def attribute_single_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letter", abac.AttributeRule.ANY_OF, ["a"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "a"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "a"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alpha)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    kas_url2: str,
    temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letra", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    alpha, beta = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alpha)

    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    kas_url2: str,
    temporary_namespace: abac.Namespace,
):
    allof = otdfctl.attribute_create(
        temporary_namespace, "ot", abac.AttributeRule.ALL_OF, ["alef", "bet", "gimmel"]
    )
    assert allof.values
    alef, bet, gimmel = allof.values
    assert alef.value == "alef"
    assert bet.value == "bet"
    assert gimmel.value == "gimmel"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm1 = otdfctl.scs_map(sc, alef)
    assert sm1.attribute_value.value == "alef"
    sm2 = otdfctl.scs_map(sc, bet)
    assert sm2.attribute_value.value == "bet"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alef)

    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, bet)

    return allof



@pytest.fixture(scope="module")
def one_attribute_attr_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url2: str,
    temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(temporary_namespace, "attrgrant", abac.AttributeRule.ANY_OF, ["alpha"])
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_alpha = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_attr(kas_entry_alpha, anyof)
    
    return anyof

@pytest.fixture(scope="module")
def attr_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    kas_url2: str,
    temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(temporary_namespace, "attrorvalgrant", abac.AttributeRule.ANY_OF, ["alpha", "beta"])
    assert anyof.values
    (alpha,beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_attr = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_attr(kas_entry_attr, anyof)
    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    
    return anyof

@pytest.fixture(scope="module")
def attr_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    kas_url2: str,
    temporary_namespace: abac.Namespace,
):
    allof = otdfctl.attribute_create(temporary_namespace, "attrandvalgrant", abac.AttributeRule.ALL_OF, ["alpha", "beta"])
    assert allof.values
    (alpha,beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(sc, beta)
    assert sm2.attribute_value.value == "beta"
    # Now assign it to the current KAS
    kas_entry_attr = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_attr(kas_entry_attr, allof)
    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    
    return allof

@pytest.fixture(scope="function")
def one_attribute_ns_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url2: str,
    more_temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(more_temporary_namespace, "nsgrant", abac.AttributeRule.ANY_OF, ["alpha"])
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_ns = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_ns(kas_entry_ns, more_temporary_namespace)
    
    return anyof

@pytest.fixture(scope="function")
def ns_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    kas_url2: str,
    more_temporary_namespace: abac.Namespace,
):
    anyof = otdfctl.attribute_create(more_temporary_namespace, "nsorvalgrant", abac.AttributeRule.ANY_OF, ["alpha", "beta"])
    assert anyof.values
    (alpha,beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    kas_entry_ns = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_ns(kas_entry_ns, more_temporary_namespace)
    
    return anyof

@pytest.fixture(scope="function")
def ns_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url1: str,
    kas_url2: str,
    more_temporary_namespace: abac.Namespace,
):
    allof = otdfctl.attribute_create(more_temporary_namespace, "nsandvalgrant", abac.AttributeRule.ALL_OF, ["alpha", "beta"])
    assert allof.values
    (alpha,beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Then assign it to all clientIds = opentdf-sdk
    sc = otdfctl.scs_create(
        [
            abac.SubjectSet(
                condition_groups=[
                    abac.ConditionGroup(
                        boolean_operator=abac.ConditionBooleanTypeEnum.OR,
                        conditions=[
                            abac.Condition(
                                subject_external_selector_value=".clientId",
                                operator=abac.SubjectMappingOperatorEnum.IN,
                                subject_external_values=["opentdf", "opentdf-sdk"],
                            )
                        ],
                    )
                ]
            )
        ],
    )
    sm = otdfctl.scs_map(sc, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(sc, beta)
    assert sm2.attribute_value.value == "beta"
    # Now assign it to the current KAS
    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    kas_entry_ns = otdfctl.kas_registry_create_if_not_present(
        kas_url2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_ns(kas_entry_ns, more_temporary_namespace)
    
    return allof