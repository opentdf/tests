import os
import typing
import pytest
import random
import string
import base64
import secrets
import assertions
import json
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from pathlib import Path
from pydantic_core import to_jsonable_python

import abac
import tdfs


def englist(s: tuple[str]) -> str:
    if len(s) > 1:
        return ", ".join(s[:-1]) + ", or " + s[-1]
    elif s:
        return s[0]
    return ""


def is_type_or_list_of_types(t: typing.Any) -> typing.Callable[[str], typing.Any]:
    def is_a(v: str) -> typing.Any:
        for i in v.split():
            if i not in typing.get_args(t):
                raise ValueError(f"Invalid value for {t}: {i}")
        return v

    return is_a


def pytest_addoption(parser: pytest.Parser):
    parser.addoption(
        "--large",
        action="store_true",
        help="generate a large (greater than 4 GiB) file for testing",
    )
    parser.addoption(
        "--sdks",
        help=f"select which sdks to run by default, unless overridden, one or more of {englist(typing.get_args(tdfs.sdk_type))}",
        type=is_type_or_list_of_types(tdfs.sdk_type),
    )
    parser.addoption(
        "--focus",
        help="skips tests which don't use the requested sdk",
        type=is_type_or_list_of_types(tdfs.focus_type),
    )
    parser.addoption(
        "--sdks-decrypt",
        help="select which sdks to run for decrypt only",
        type=is_type_or_list_of_types(tdfs.sdk_type),
    )
    parser.addoption(
        "--sdks-encrypt",
        help="select which sdks to run for encrypt only",
        type=is_type_or_list_of_types(tdfs.sdk_type),
    )
    parser.addoption(
        "--containers",
        help=f"which container formats to test, one or more of {englist(typing.get_args(tdfs.container_type))}",
        type=is_type_or_list_of_types(tdfs.container_type),
    )


def pytest_generate_tests(metafunc: pytest.Metafunc):
    if "size" in metafunc.fixturenames:
        metafunc.parametrize(
            "size",
            ["large" if metafunc.config.getoption("large") else "small"],
            scope="session",
        )

    def list_opt[T](name: str, t: typing.Any) -> list[T]:
        ttt = typing.get_args(t)
        v = metafunc.config.getoption(name)
        if not v:
            return []
        if type(v) is not str:
            raise ValueError(f"Invalid value for {name}: {v}")
        for i in v.split():
            if i not in ttt:
                raise ValueError(f"Invalid value for {name}: {i}, must be one of {ttt}")
        return [typing.cast(T, i) for i in v.split()]

    def defaulted_list_opt[T](
        names: list[str], t: typing.Any, default: list[T]
    ) -> list[T]:
        for name in names:
            v = metafunc.config.getoption(name)
            if v:
                return list_opt(name, t)
        return default

    subject_sdks: set[tdfs.SDK] = set()

    if "encrypt_sdk" in metafunc.fixturenames:
        encrypt_sdks: list[tdfs.sdk_type] = []
        encrypt_sdks = defaulted_list_opt(
            ["--sdks-encrypt", "--sdks"],
            tdfs.sdk_type,
            list(typing.get_args(tdfs.sdk_type)),
        )
        # convert list of sdk_type to list of SDK objects
        e_sdks = [
            v
            for sdks in [tdfs.all_versions_of(sdk) for sdk in encrypt_sdks]
            for v in sdks
        ]
        metafunc.parametrize("encrypt_sdk", e_sdks, ids=[str(x) for x in e_sdks])
        subject_sdks |= set(e_sdks)
    if "decrypt_sdk" in metafunc.fixturenames:
        decrypt_sdks: list[tdfs.sdk_type] = []
        decrypt_sdks = defaulted_list_opt(
            ["--sdks-decrypt", "--sdks"],
            tdfs.sdk_type,
            list(typing.get_args(tdfs.sdk_type)),
        )
        d_sdks = [
            v
            for sdks in [tdfs.all_versions_of(sdk) for sdk in decrypt_sdks]
            for v in sdks
        ]
        metafunc.parametrize("decrypt_sdk", d_sdks, ids=[str(x) for x in d_sdks])
        subject_sdks |= set(d_sdks)

    if "in_focus" in metafunc.fixturenames:
        focus_opt = "all"
        if metafunc.config.getoption("--focus"):
            focus_opt = metafunc.config.getoption("--focus")
        focus: set[tdfs.sdk_type] = set()
        if focus_opt == "all":
            focus = set(typing.get_args(tdfs.sdk_type))
        else:
            focus = set(list_opt("--focus", tdfs.focus_type))
        focused_sdks = set(s for s in subject_sdks if s.sdk in focus)
        metafunc.parametrize("in_focus", [focused_sdks])

    if "container" in metafunc.fixturenames:
        containers: list[tdfs.container_type] = []
        if metafunc.config.getoption("--containers"):
            containers = list_opt("--containers", tdfs.container_type)
        else:
            containers = list(typing.get_args(tdfs.container_type))
        metafunc.parametrize("container", containers)


@pytest.fixture(scope="module")
def pt_file(tmp_dir: Path, size: str) -> Path:
    pt_file = tmp_dir / f"test-plain-{size}.txt"
    length = (5 * 2**30) if size == "large" else 128
    with pt_file.open("w") as f:
        for i in range(0, length, 16):
            f.write("{:15,d}\n".format(i))
    return pt_file


@pytest.fixture(scope="module")
def tmp_dir() -> Path:
    dname = Path("tmp/")
    dname.mkdir(parents=True, exist_ok=True)
    return dname


_otdfctl = abac.OpentdfCommandLineTool()


@pytest.fixture(scope="module")
def otdfctl():
    return _otdfctl


@pytest.fixture(scope="module")
def temporary_namespace(otdfctl: abac.OpentdfCommandLineTool):
    return create_temp_namesapce(otdfctl)


def create_temp_namesapce(otdfctl: abac.OpentdfCommandLineTool):
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
def kas_url_default():
    return os.getenv("KASURL", "http://localhost:8080/kas")


@pytest.fixture(scope="session")
def kas_url_value1():
    return os.getenv("KASURL1", "http://localhost:8181/kas")


@pytest.fixture(scope="session")
def kas_url_value2():
    return os.getenv("KASURL2", "http://localhost:8282/kas")


@pytest.fixture(scope="session")
def kas_url_attr():
    return os.getenv("KASURL3", "http://localhost:8383/kas")


@pytest.fixture(scope="session")
def kas_url_ns():
    return os.getenv("KASURL4", "http://localhost:8484/kas")


@pytest.fixture(scope="module")
def attribute_single_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_value1: str,
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
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alpha)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_value1: str,
    kas_url_value2: str,
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
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alpha)

    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url_value2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_value1: str,
    kas_url_value2: str,
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
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_alpha, alef)

    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url_value2,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, bet)

    return allof


@pytest.fixture(scope="module")
def one_attribute_attr_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_attr: str,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace, "attrgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
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
        kas_url_attr,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_attr(kas_entry_alpha, anyof)

    return anyof


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_attr: str,
    kas_url_value1: str,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace,
        "attrorvalgrant",
        abac.AttributeRule.ANY_OF,
        ["alpha", "beta"],
    )
    assert anyof.values
    (alpha, beta) = anyof.values
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
        kas_url_attr,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_attr(kas_entry_attr, anyof)
    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)

    return anyof


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_attr: str,
    kas_url_value1: str,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    allof = otdfctl.attribute_create(
        temporary_namespace,
        "attrandvalgrant",
        abac.AttributeRule.ALL_OF,
        ["alpha", "beta"],
    )
    assert allof.values
    (alpha, beta) = allof.values
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
        kas_url_attr,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_attr(kas_entry_attr, allof)
    kas_entry_beta = otdfctl.kas_registry_create_if_not_present(
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)

    return allof


@pytest.fixture(scope="module")
def one_attribute_ns_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_ns: str,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace, "nsgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
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
        kas_url_ns,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_ns(kas_entry_ns, temporary_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_value1: str,
    kas_url_ns: str,
) -> abac.Attribute:
    temp_namespace = create_temp_namesapce(otdfctl)
    anyof = otdfctl.attribute_create(
        temp_namespace,
        "nsorvalgrant",
        abac.AttributeRule.ANY_OF,
        ["alpha", "beta"],
    )
    assert anyof.values
    (alpha, beta) = anyof.values
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
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    kas_entry_ns = otdfctl.kas_registry_create_if_not_present(
        kas_url_ns,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_ns(kas_entry_ns, temp_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_url_value1: str,
    kas_url_ns: str,
) -> abac.Attribute:
    temp_namespace = create_temp_namesapce(otdfctl)
    allof = otdfctl.attribute_create(
        temp_namespace,
        "nsandvalgrant",
        abac.AttributeRule.ALL_OF,
        ["alpha", "beta"],
    )
    assert allof.values
    (alpha, beta) = allof.values
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
        kas_url_value1,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_value(kas_entry_beta, beta)
    kas_entry_ns = otdfctl.kas_registry_create_if_not_present(
        kas_url_ns,
        load_cached_kas_keys(),
    )
    otdfctl.grant_assign_ns(kas_entry_ns, temp_namespace)

    return allof


@pytest.fixture(scope="module")
def hs256_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


@pytest.fixture(scope="module")
def rs256_keys() -> tuple[str, str]:
    # Generate an RSA private key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Generate the public key from the private key
    public_key = private_key.public_key()

    # Serialize the private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize the public key to PEM format
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Convert to string with escaped newlines
    private_pem_str = private_pem.decode("utf-8")
    public_pem_str = public_pem.decode("utf-8")

    return private_pem_str, public_pem_str


def write_assertion_to_file(
    tmp_dir: Path, file_name: str, assertion_list: list[assertions.Assertion] = []
) -> Path:
    as_file = tmp_dir / f"test-assertion-{file_name}.json"
    assertion_json = json.dumps(to_jsonable_python(assertion_list, exclude_none=True))
    with as_file.open("w") as f:
        f.write(assertion_json)
    return as_file


@pytest.fixture(scope="module")
def assertion_file_no_keys(tmp_dir: Path) -> Path:
    assertion_list = [
        assertions.Assertion(
            appliesToState="encrypted",
            id="424ff3a3-50ca-4f01-a2ae-ef851cd3cac0",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
        )
    ]
    return write_assertion_to_file(
        tmp_dir, "assertion_1_no_signing_key", assertion_list
    )


@pytest.fixture(scope="module")
def assertion_file_rs_and_hs_keys(
    tmp_dir: Path, hs256_key: str, rs256_keys: tuple[str, str]
) -> Path:
    rs256_private, _ = rs256_keys
    assertion_list = [
        assertions.Assertion(
            appliesToState="encrypted",
            id="assertion1",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
            signingKey=assertions.AssertionKey(
                alg="HS256",
                key=hs256_key,
            ),
        ),
        assertions.Assertion(
            appliesToState="encrypted",
            id="assertion2",
            scope="tdo",
            statement=assertions.Statement(
                format="json+stanag5636",
                schema="urn:nato:stanag:5636:A:1:elements:json",
                value='{"ocl":{"pol":"62c76c68-d73d-4628-8ccc-4c1e18118c22","cls":"SECRET","catl":[{"type":"P","name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},"context":{"[@base](https://github.com/base)":"urn:nato:stanag:5636:A:1:elements:json"}}',
            ),
            type="handling",
            signingKey=assertions.AssertionKey(
                alg="RS256",
                key=rs256_private,
            ),
        ),
    ]
    return write_assertion_to_file(
        tmp_dir, "assertion1_hs_assertion2_rs", assertion_list
    )


def write_assertion_verification_keys_to_file(
    tmp_dir: Path,
    file_name: str,
    assertion_verification_keys: assertions.AssertionVerificationKeys,
) -> Path:
    as_file = tmp_dir / f"test-assertion-verification-{file_name}.json"
    assertion_verification_json = json.dumps(
        to_jsonable_python(assertion_verification_keys, exclude_none=True)
    )
    with as_file.open("w") as f:
        f.write(assertion_verification_json)
    return as_file


@pytest.fixture(scope="module")
def assertion_verification_file_rs_and_hs_keys(
    tmp_dir: Path, hs256_key: str, rs256_keys: tuple[str, str]
) -> Path:
    _, rs256_public = rs256_keys
    assertion_verification = assertions.AssertionVerificationKeys(
        keys={
            "assertion1": assertions.AssertionKey(
                alg="HS256",
                key=hs256_key,
            ),
            "assertion2": assertions.AssertionKey(
                alg="RS256",
                key=rs256_public,
            ),
        }
    )
    return write_assertion_verification_keys_to_file(
        tmp_dir, "assertion1_hs_assertion2_rs", assertion_verification
    )
