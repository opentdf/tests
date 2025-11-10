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
from typing import cast


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

    def list_opt(name: str, t: typing.Any) -> list[str]:
        ttt = typing.get_args(t)
        v = metafunc.config.getoption(name)
        if not v:
            return []
        if type(v) is not str:
            raise ValueError(f"Invalid value for {name}: {v}")
        a = v.split()
        for i in a:
            if i not in ttt:
                raise ValueError(f"Invalid value for {name}: {i}, must be one of {ttt}")
        return a

    def defaulted_list_opt[T](
        names: list[str], t: typing.Any, default: list[T]
    ) -> list[T]:
        for name in names:
            v = metafunc.config.getoption(name)
            if v:
                return cast(list[T], list_opt(name, t))
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
            focus = cast(set[tdfs.sdk_type], set(list_opt("--focus", tdfs.focus_type)))
        focused_sdks = set(s for s in subject_sdks if s.sdk in focus)
        metafunc.parametrize("in_focus", [focused_sdks])

    if "container" in metafunc.fixturenames:
        containers: list[tdfs.container_type] = []
        if metafunc.config.getoption("--containers"):
            containers = cast(
                list[tdfs.container_type], list_opt("--containers", tdfs.container_type)
            )
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


def load_otdfctl() -> abac.OpentdfCommandLineTool:
    oh = os.environ.get("OTDFCTL_HEADS", "[]")
    try:
        heads = json.loads(oh)
        if heads:
            return abac.OpentdfCommandLineTool(f"sdk/go/dist/{heads[0]}/otdfctl.sh")
    except json.JSONDecodeError:
        print(f"Invalid OTDFCTL_HEADS environment variable: [{oh}]")
    if os.path.isfile("sdk/go/dist/main/otdfctl.sh"):
        return abac.OpentdfCommandLineTool("sdk/go/dist/main/otdfctl.sh")
    return abac.OpentdfCommandLineTool()


_otdfctl = load_otdfctl()


@pytest.fixture(scope="module")
def otdfctl():
    return _otdfctl


@pytest.fixture(scope="module")
def temporary_namespace(otdfctl: abac.OpentdfCommandLineTool):
    try:
        return create_temp_namesapce(otdfctl)
    except AssertionError as e:
        pytest.skip(f"Failed to create temporary namespace: {e}")


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


@pytest.fixture(scope="module")
def cached_kas_keys() -> abac.PublicKey:
    return load_cached_kas_keys()


class ExtraKey(typing.TypedDict):
    """TypedDict for extra keys in extra-keys.json"""

    kid: str
    alg: str
    privateKey: str | None
    cert: str


@pytest.fixture(scope="module")
def extra_keys() -> dict[str, ExtraKey]:
    """Extra key data from extra-keys.json"""
    extra_keys_file = Path("extra-keys.json")
    if not extra_keys_file.exists():
        raise FileNotFoundError(f"Extra keys file not found: {extra_keys_file}")
    with extra_keys_file.open("r") as f:
        extra_key_list = typing.cast(list[ExtraKey], json.load(f))
    return {k["kid"]: k for k in extra_key_list}


@pytest.fixture(scope="session")
def kas_public_key_r1() -> abac.KasPublicKey:
    with open(f"{PLATFORM_DIR}/kas-cert.pem", "r") as rsaFile:
        return abac.KasPublicKey(
            algStr="rsa:2048",
            kid="r1",
            pem=rsaFile.read(),
        )


@pytest.fixture(scope="session")
def kas_public_key_e1() -> abac.KasPublicKey:
    with open(f"{PLATFORM_DIR}/kas-ec-cert.pem", "r") as ecFile:
        return abac.KasPublicKey(
            algStr="ec:secp256r1",
            kid="e1",
            pem=ecFile.read(),
        )


@pytest.fixture(scope="session")
def kas_url_default():
    return os.getenv("KASURL", "http://localhost:8080/kas")


@pytest.fixture(scope="module")
def kas_entry_default(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_default: str,
) -> abac.KasEntry:
    return otdfctl.kas_registry_create_if_not_present(kas_url_default, cached_kas_keys)


@pytest.fixture(scope="session")
def kas_url_value1():
    return os.getenv("KASURL1", "http://localhost:8181/kas")


@pytest.fixture(scope="module")
def kas_entry_value1(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_value1: str,
) -> abac.KasEntry:
    return otdfctl.kas_registry_create_if_not_present(kas_url_value1, cached_kas_keys)


@pytest.fixture(scope="session")
def kas_url_value2():
    return os.getenv("KASURL2", "http://localhost:8282/kas")


@pytest.fixture(scope="module")
def kas_entry_value2(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_value2: str,
) -> abac.KasEntry:
    return otdfctl.kas_registry_create_if_not_present(kas_url_value2, cached_kas_keys)


@pytest.fixture(scope="session")
def kas_url_attr():
    return os.getenv("KASURL3", "http://localhost:8383/kas")


@pytest.fixture(scope="module")
def kas_entry_attr(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_attr: str,
) -> abac.KasEntry:
    return otdfctl.kas_registry_create_if_not_present(kas_url_attr, cached_kas_keys)


@pytest.fixture(scope="session")
def kas_url_ns():
    return os.getenv("KASURL4", "http://localhost:8484/kas")


@pytest.fixture(scope="module")
def kas_entry_ns(
    otdfctl: abac.OpentdfCommandLineTool,
    cached_kas_keys: abac.PublicKey,
    kas_url_ns: str,
) -> abac.KasEntry:
    return otdfctl.kas_registry_create_if_not_present(kas_url_ns, cached_kas_keys)


def pick_extra_key(extra_keys: dict[str, ExtraKey], kid: str) -> abac.KasPublicKey:
    if kid not in extra_keys:
        raise ValueError(f"Extra key with kid {kid} not found in extra keys")
    ek = extra_keys[kid]
    return abac.KasPublicKey(
        alg=abac.str_to_kas_public_key_alg(ek["alg"]),
        kid=ek["kid"],
        pem=ek["cert"],
    )


@pytest.fixture(scope="module")
def public_key_kas_default_kid_r1(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
) -> abac.KasKey:
    return otdfctl.kas_registry_create_public_key_only(
        kas_entry_default, kas_public_key_r1
    )


@pytest.fixture(scope="module")
def public_key_kas_default_kid_e1(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_e1: abac.KasPublicKey,
) -> abac.KasKey:
    return otdfctl.kas_registry_create_public_key_only(
        kas_entry_default, kas_public_key_e1
    )


@pytest.fixture(scope="module")
def attribute_with_different_kids(
    otdfctl: abac.OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
    public_key_kas_default_kid_r1: abac.KasKey,
    public_key_kas_default_kid_e1: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
):
    """
    Create an attribute with different KAS public keys.
    This is used to test the handling of multiple KAS public keys with different mechanisms.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip(
            "Key management feature is not enabled, skipping test for multiple KAS keys"
        )
    allof = otdfctl.attribute_create(
        temporary_namespace,
        "multikeys",
        abac.AttributeRule.ALL_OF,
        ["r1", "e1"],
    )
    assert allof.values
    (ar1, ae1) = allof.values
    assert ar1.value == "r1"
    assert ae1.value == "e1"

    for attr in [ar1, ae1]:
        # Then assign it to all clientIds = opentdf-sdk
        sm = otdfctl.scs_map(otdf_client_scs, attr)
        assert sm.attribute_value.value == attr.value

    # Assign kas key to the attribute values
    otdfctl.key_assign_value(public_key_kas_default_kid_e1, ae1)
    otdfctl.key_assign_value(public_key_kas_default_kid_r1, ar1)

    return allof


@pytest.fixture(scope="module")
def attribute_single_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
):
    pfs = tdfs.PlatformFeatureSet()
    anyof = otdfctl.attribute_create(
        temporary_namespace, "letter", abac.AttributeRule.ANY_OF, ["a"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "a"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "a"
    # Now assign it to the current KAS
    if "key_management" not in pfs.features:
        otdfctl.grant_assign_value(kas_entry_value1, alpha)
    else:
        kas_key = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key, alpha)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_value2: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
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
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, alpha)
        otdfctl.grant_assign_value(kas_entry_value2, beta)
    else:
        kas_key_alph = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_alph, alpha)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value2, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)
    return anyof


@pytest.fixture(scope="module")
def attribute_two_kas_grant_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_value2: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
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
    sm1 = otdfctl.scs_map(otdf_client_scs, alef)
    assert sm1.attribute_value.value == "alef"
    sm2 = otdfctl.scs_map(otdf_client_scs, bet)
    assert sm2.attribute_value.value == "bet"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, alef)
        otdfctl.grant_assign_value(kas_entry_value2, bet)
    else:
        kas_key_alpha = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_alpha, alef)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value2, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, bet)

    return allof


@pytest.fixture(scope="module")
def one_attribute_attr_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_attr: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace, "attrgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_attr, anyof)
    else:
        kas_key_alpha = otdfctl.kas_registry_create_public_key_only(
            kas_entry_attr, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_alpha, anyof)
    return anyof


@pytest.fixture(scope="module")
def attribute_with_or_type(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with OR type and assign it to a KAS entry.

    The attribute will have a rule of ANY_OF with values "alpha" and "beta".
    The user only has permission to access the attribute if they have the "alpha" value.
    Files with both will be accessible to the user, but files with only "beta" will not.
    """
    anyof = otdfctl.attribute_create(
        temporary_namespace, "or", abac.AttributeRule.ANY_OF, ["alpha", "beta"]
    )
    assert anyof.values
    (alpha, beta) = anyof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Assign or:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    return anyof


@pytest.fixture(scope="module")
def attribute_with_and_type(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with AND type and assign it to a KAS entry.

    The attribute will have a rule of ALL_OF with values "alpha" and "beta".
    The user only has alpha assigned, so will be able to access files that do not have beta applied.
    """
    allof = otdfctl.attribute_create(
        temporary_namespace, "and", abac.AttributeRule.ALL_OF, ["alpha", "beta"]
    )
    assert allof.values
    (alpha, beta) = allof.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"

    # Assign and:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    return allof


@pytest.fixture(scope="module")
def attribute_with_hierarchy_type(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    """Create an attribute with HIERARCHY type and assign it to a KAS entry.

    The attribute will have a rule of HIERARCHY with values "alpha", "beta" and "gamma".
    The user only has "beta" assigned, so will be able to access files that have "gamma" or "beta" but not "alpha".
    """
    hierarchy_attr = otdfctl.attribute_create(
        temporary_namespace,
        "hierarchy",
        abac.AttributeRule.HIERARCHY,
        ["alpha", "beta", "gamma"],
    )
    assert hierarchy_attr.values
    (alpha, beta, gamma) = hierarchy_attr.values
    assert alpha.value == "alpha"
    assert beta.value == "beta"
    assert gamma.value == "gamma"

    # Assign hierarchical:alpha to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm.attribute_value.value == "beta"

    return hierarchy_attr


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_attr: abac.KasEntry,
    kas_entry_value1: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
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
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_attr, anyof)
        otdfctl.grant_assign_value(kas_entry_value1, beta)
    else:
        kas_key_attr = otdfctl.kas_registry_create_public_key_only(
            kas_entry_attr, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_attr, anyof)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

    return anyof


@pytest.fixture(scope="module")
def attr_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_attr: abac.KasEntry,
    kas_entry_value1: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
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
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm2.attribute_value.value == "beta"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_attr(kas_entry_attr, allof)
        otdfctl.grant_assign_value(kas_entry_value1, beta)
    else:
        kas_key_attr = otdfctl.kas_registry_create_public_key_only(
            kas_entry_attr, kas_public_key_r1
        )
        otdfctl.key_assign_attr(kas_key_attr, allof)

        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

    return allof


@pytest.fixture(scope="module")
def one_attribute_ns_kas_grant(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_ns: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> abac.Attribute:
    anyof = otdfctl.attribute_create(
        temporary_namespace, "nsgrant", abac.AttributeRule.ANY_OF, ["alpha"]
    )
    assert anyof.values
    (alpha,) = anyof.values
    assert alpha.value == "alpha"

    # Then assign it to all clientIds = opentdf-sdk
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_ns(kas_entry_ns, temporary_namespace)
    else:
        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ns, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temporary_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_or(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_ns: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
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
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, beta)
        otdfctl.grant_assign_ns(kas_entry_ns, temp_namespace)
    else:
        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ns, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temp_namespace)

    return anyof


@pytest.fixture(scope="module")
def ns_and_value_kas_grants_and(
    otdfctl: abac.OpentdfCommandLineTool,
    kas_entry_value1: abac.KasEntry,
    kas_entry_ns: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
    otdf_client_scs: abac.SubjectConditionSet,
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
    sm = otdfctl.scs_map(otdf_client_scs, alpha)
    assert sm.attribute_value.value == "alpha"
    sm2 = otdfctl.scs_map(otdf_client_scs, beta)
    assert sm2.attribute_value.value == "beta"

    # Now assign it to the current KAS
    if "key_management" not in tdfs.PlatformFeatureSet().features:
        otdfctl.grant_assign_value(kas_entry_value1, beta)
        otdfctl.grant_assign_ns(kas_entry_ns, temp_namespace)
    else:
        kas_key_beta = otdfctl.kas_registry_create_public_key_only(
            kas_entry_value1, kas_public_key_r1
        )
        otdfctl.key_assign_value(kas_key_beta, beta)

        kas_key_ns = otdfctl.kas_registry_create_public_key_only(
            kas_entry_ns, kas_public_key_r1
        )
        otdfctl.key_assign_ns(kas_key_ns, temp_namespace)

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


@pytest.fixture(scope="module")
def otdf_client_scs(otdfctl: abac.OpentdfCommandLineTool) -> abac.SubjectConditionSet:
    """
    Creates a standard subject condition set for OpenTDF clients.
    This condition set matches client IDs 'opentdf' or 'opentdf-sdk'.

    Returns:
        abac.SubjectConditionSet: The created subject condition set
    """
    sc: abac.SubjectConditionSet = otdfctl.scs_create(
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
    return sc


def _obligation_setup_helper(
    *,
    otdfctl: abac.OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
    attr_name: str,
    attr_rule: abac.AttributeRule,
    attr_values: list[str],
    obligation_def_name: str,
    obligation_value_name: str,
    scs: abac.SubjectConditionSet | None,
    trigger_client_id: str | None,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """Shared helper for obligation test setup.

    Creates attribute and optional SCS mapping, obligation definition with a single value,
    and an obligation trigger (optionally scoped to a client id).
    """
    # Attribute
    attr = otdfctl.attribute_create(
        name=attr_name,
        namespace=temporary_namespace,
        t=attr_rule,
        values=attr_values,
    )
    assert attr is not None
    assert attr.fqn == f"{temporary_namespace.fqn}/attr/{attr.name}"
    assert len(attr.values) == 1
    attr_value = attr.values[0]
    assert (
        attr_value.fqn
        == f"{temporary_namespace.fqn}/attr/{attr.name}/value/{attr_value.value}"
    )

    # Optional SCS mapping
    if scs is not None:
        sm = otdfctl.scs_map(scs, attr_value)
        assert sm is not None

    # Obligation and value
    obligation = otdfctl.obligation_def_create(
        name=obligation_def_name,
        namespace=temporary_namespace,
        value=[obligation_value_name],
    )
    assert obligation is not None
    assert obligation.fqn == f"{temporary_namespace.fqn}/obl/{obligation.name}"
    assert len(obligation.values) == 1

    if obligation.values[0].fqn is None:
        assert obligation.values[0].value is not None
        assert obligation.values[0].value == obligation_value_name
        assert obligation.name is not None
        assert obligation.name == obligation_def_name
        obligation.values[0].fqn = f"{temporary_namespace.fqn}/obl/{obligation.name}/value/{obligation.values[0].value}"
    else:
        assert ( 
            obligation.values[0].fqn
            == f"{temporary_namespace.fqn}/obl/{obligation_def_name}/value/{obligation_value_name}"
        )

    # Trigger
    _ = otdfctl.obligation_triggers_create(
        obligation.values[0], "read", attr_value, trigger_client_id
    )
    assert _ is not None

    return attr, obligation.values[0]


@pytest.fixture(scope="module")
def obligation_setup_no_scs_unscoped_trigger(
    otdfctl: abac.OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute and obligation value.

    Creates:
    - A namespace for obligations testing
    - An attribute with a "alpha" value
    - An obligation definition with a required value
    - An obligation value instance

    Note: Subject mapping is intentionally omitted for testing scenarios
    where obligations should prevent access.

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """
    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test",
        attr_rule=abac.AttributeRule.ALL_OF,
        attr_values=["alpha"],
        obligation_def_name="test_obligation",
        obligation_value_name="watermark",
        scs=None,
        trigger_client_id=None,
    )


@pytest.fixture(scope="module")
def obligation_setup_scs_unscoped_trigger(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute, obligation value, and subject condition set.

    Creates:
    - A namespace for obligations testing
    - An attribute with a "beta" value
    - An obligation definition with a required value
    - An obligation value instance
    - Maps the attribute value to the provided subject condition set

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """

    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test-scs",
        attr_rule=abac.AttributeRule.ANY_OF,
        attr_values=["beta"],
        obligation_def_name="test_obligation_scs",
        obligation_value_name="geofence",
        scs=otdf_client_scs,
        trigger_client_id=None,
    )


@pytest.fixture(scope="module")
def obligation_setup_scs_scoped_trigger(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute, obligation value, and subject condition set.
    The obligation trigger will be scoped to the specified client ID.

    Args:
        client_id: The client ID to scope the obligation trigger to (defaults to "opentdf")

    Creates:
    - A namespace for obligations testing
    - An attribute with a "gamma" value
    - An obligation definition with a required value
    - An obligation value instance
    - Maps the attribute value to the provided subject condition set
    - Scopes a trigger to the specified client ID

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """
    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test-scs-scoped-otdf-client",
        attr_rule=abac.AttributeRule.ANY_OF,
        attr_values=["gamma"],
        obligation_def_name="obligation-test-scs-scoped-otdf-client",
        obligation_value_name="prevent-download",
        scs=otdf_client_scs,
        trigger_client_id="opentdf",
    )


@pytest.fixture(scope="module")
def obligation_setup_scs_scoped_trigger_different_client(
    otdfctl: abac.OpentdfCommandLineTool,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, abac.ObligationValue]:
    """
    Sets up an obligation test scenario with an attribute, obligation value, and subject condition set.
    The obligation trigger will be scoped to a different client ID than the one in the subject condition set.

    Args:
        client_id: The client ID to scope the obligation trigger to (defaults to "different-client")

    Creates:
    - A namespace for obligations testing
    - An attribute with a "delta" value
    - An obligation definition with a required value
    - An obligation value instance
    - Maps the attribute value to the provided subject condition set
    - Scopes a trigger to the specified different client ID

    Returns:
        tuple[abac.Attribute, abac.ObligationValue]: The attribute and obligation value for testing
    """
    return _obligation_setup_helper(
        otdfctl=otdfctl,
        temporary_namespace=temporary_namespace,
        attr_name="obligation-test-scs-scoped-different-client",
        attr_rule=abac.AttributeRule.ANY_OF,
        attr_values=["delta"],
        obligation_def_name="obligation-test-scs-scoped-different-client",
        obligation_value_name="prevent-download",
        scs=otdf_client_scs,
        trigger_client_id="different-client",
    )
