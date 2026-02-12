"""Key management fixtures for testing explicit KAS key operations.

This module contains fixtures for:
- Extra keys loaded from extra-keys.json
- Managed key creation and assignment
- Public key registration
- Legacy key imports
- Base key configuration
"""

import hashlib
import json
import os
import typing
from pathlib import Path

import pytest

import abac
import tdfs
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(scope="session")
def root_key() -> str:
    """Get the root key from environment variable."""
    ot_root_key = os.getenv("OT_ROOT_KEY")
    assert ot_root_key is not None, "OT_ROOT_KEY environment variable is not set"
    return ot_root_key


def _key_id_suffix(wrapping_key: str) -> str:
    """Generate a short suffix from the wrapping key to ensure uniqueness per key."""
    return hashlib.sha256(wrapping_key.encode()).hexdigest()[:8]


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


def pick_extra_key(extra_keys: dict[str, ExtraKey], kid: str) -> abac.KasPublicKey:
    """Select an extra key by kid and convert to KasPublicKey."""
    if kid not in extra_keys:
        raise ValueError(f"Extra key with kid {kid} not found in extra keys")
    ek = extra_keys[kid]
    return abac.KasPublicKey(
        alg=abac.str_to_kas_public_key_alg(ek["alg"]),
        kid=ek["kid"],
        pem=ek["cert"],
    )


@pytest.fixture(scope="module")
def managed_key_km1_rsa(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create RSA managed key on km1.

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"km1-rsa-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km1)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km1,
            key_id=key_id,
            mode="local",
            algorithm="rsa:2048",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def managed_key_km2_ec(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC managed key on km2.

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"km2-ec-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km2)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km2,
            key_id=key_id,
            mode="local",
            algorithm="ec:secp256r1",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def key_e256(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC secp256r1 managed key on km2.

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"e256-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km2)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km2,
            key_id=key_id,
            mode="local",
            algorithm="ec:secp256r1",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def key_e384(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC secp384r1 managed key on km2

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"e384-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km2)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km2,
            key_id=key_id,
            mode="local",
            algorithm="ec:secp384r1",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def key_e521(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC secp521r1 managed key on km2.

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"e521-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km2)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km2,
            key_id=key_id,
            mode="local",
            algorithm="ec:secp521r1",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def key_r2048(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create RSA 2048 managed key on km1.

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"r2048-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km1)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km1,
            key_id=key_id,
            mode="local",
            algorithm="rsa:2048",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def key_r4096(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create RSA 4096 managed key on km1.

    Key ID includes a hash of the root key to ensure that if the root key changes,
    a new key will be created instead of reusing an incompatible one.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled")

    key_id = f"r4096-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km1)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km1,
            key_id=key_id,
            mode="local",
            algorithm="rsa:4096",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


@pytest.fixture(scope="module")
def attribute_allof_with_extended_mechanisms(
    otdfctl: OpentdfCommandLineTool,
    key_e256: abac.KasKey,
    key_e384: abac.KasKey,
    key_e521: abac.KasKey,
    key_r2048: abac.KasKey,
    key_r4096: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute and assign extended mechanism keys to it.

    - Uses ec:secp256r1, ec:secp384r1, ec:secp521r1, and rsa:2048, rsa:4096 keys
    - Reuses existing managed keys
    - Assigns all keys to attribute values (value-level assignment)
    - Maps all attribute values to the client SCS
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip(
            "Key management feature is not enabled; skipping key assignment fixture"
        )

    # Create attribute with three values under ALL_OF
    attr = otdfctl.attribute_create(
        temporary_namespace,
        "mechanism-select",
        abac.AttributeRule.ALL_OF,
        ["ec-secp256r1", "ec-secp384r1", "ec-secp521r1", "rsa:2048", "rsa:4096"],
    )
    assert attr.values and len(attr.values) == 5
    v_e256, v_e384, v_e521, v_r2048, v_r4096 = attr.values
    assert v_e256.value == "ec-secp256r1"
    assert v_e384.value == "ec-secp384r1"
    assert v_e521.value == "ec-secp521r1"
    assert v_r2048.value == "rsa-2048"
    assert v_r4096.value == "rsa-4096"

    # Ensure client has access to all values
    sm1 = otdfctl.scs_map(otdf_client_scs, v_e256)
    assert sm1.attribute_value.value == v_e256.value
    sm2 = otdfctl.scs_map(otdf_client_scs, v_e384)
    assert sm2.attribute_value.value == v_e384.value
    sm3 = otdfctl.scs_map(otdf_client_scs, v_e521)
    assert sm3.attribute_value.value == v_e521.value
    sm4 = otdfctl.scs_map(otdf_client_scs, v_r2048)
    assert sm4.attribute_value.value == v_r2048.value
    sm5 = otdfctl.scs_map(otdf_client_scs, v_r4096)
    assert sm5.attribute_value.value == v_r4096.value

    # Assign keys to corresponding attribute values
    otdfctl.key_assign_value(key_e256, v_e256)
    otdfctl.key_assign_value(key_e384, v_e384)
    otdfctl.key_assign_value(key_e521, v_e521)
    otdfctl.key_assign_value(key_r2048, v_r2048)
    otdfctl.key_assign_value(key_r4096, v_r4096)

    return (
        attr,
        [
            key_e256.key.key_id,
            key_e384.key.key_id,
            key_e521.key.key_id,
            key_r2048.key.key_id,
            key_r4096.key.key_id,
        ],
    )


@pytest.fixture(scope="module")
def attribute_allof_with_two_managed_keys(
    otdfctl: OpentdfCommandLineTool,
    managed_key_km1_rsa: abac.KasKey,
    managed_key_km2_ec: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute and assign two managed keys (RSA and EC) to it.

    - Uses km1 (rsa:2048) and km2 (ec:secp256r1)
    - Reuses existing managed keys
    - Assigns both keys to the same attribute (attribute-level assignment)
    - Maps both attribute values to the client SCS
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip(
            "Key management feature is not enabled; skipping key assignment fixture"
        )

    # Create attribute with two values under ALL_OF
    attr = otdfctl.attribute_create(
        temporary_namespace, "kmallof", abac.AttributeRule.ALL_OF, ["r1", "e1"]
    )
    assert attr.values and len(attr.values) == 2
    r1, e1 = attr.values
    assert r1.value == "r1"
    assert e1.value == "e1"

    # Ensure client has access to both values
    sm1 = otdfctl.scs_map(otdf_client_scs, r1)
    assert sm1.attribute_value.value == r1.value
    sm2 = otdfctl.scs_map(otdf_client_scs, e1)
    assert sm2.attribute_value.value == e1.value

    # Assign both keys to the attribute
    otdfctl.key_assign_attr(managed_key_km1_rsa, attr)
    otdfctl.key_assign_attr(managed_key_km2_ec, attr)

    return (attr, [managed_key_km1_rsa.key.key_id, managed_key_km2_ec.key.key_id])


@pytest.fixture(scope="module")
def public_key_kas_default_kid_r1(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_r1: abac.KasPublicKey,
) -> abac.KasKey:
    """Register RSA public key (kid='r1') on default KAS."""
    return otdfctl.kas_registry_create_public_key_only(
        kas_entry_default, kas_public_key_r1
    )


@pytest.fixture(scope="module")
def public_key_kas_default_kid_e1(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_default: abac.KasEntry,
    kas_public_key_e1: abac.KasPublicKey,
) -> abac.KasKey:
    """Register EC public key (kid='e1') on default KAS."""
    return otdfctl.kas_registry_create_public_key_only(
        kas_entry_default, kas_public_key_e1
    )


@pytest.fixture(scope="module")
def attribute_with_different_kids(
    otdfctl: OpentdfCommandLineTool,
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
def legacy_imported_golden_r1_key(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    extra_keys: dict[str, ExtraKey],
    root_key: str,
) -> abac.KasKey:
    """
    Import (or reuse) the legacy 'golden-r1' key for decrypting golden TDFs.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip(
            "Key management feature is not enabled; skipping legacy key import fixture"
        )

    golden_key = extra_keys["golden-r1"]
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km2)
    for key in existing_keys:
        if key.key.key_id == golden_key["kid"]:
            return key

    return otdfctl.kas_registry_import_key(
        kas_entry_km2,
        private_pem=golden_key["privateKey"],
        public_pem=golden_key["cert"],
        key_id="r1",
        legacy=True,
        wrapping_key=root_key,
        wrapping_key_id="root",
        algorithm=golden_key["alg"],
    )


@pytest.fixture(scope="module")
def base_key_e1(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> None:
    """
    Ensure a managed key with key_id 'e1' exists on the default KAS
    and is configured as the base key.
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip("Key management feature is not enabled; skipping base key fixture")

    existing_keys = otdfctl.kas_registry_keys_list(kas_entry_km1)
    key_id = "e1"
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry_km1,
            key_id=key_id,
            mode="local",
            algorithm="ec:secp256r1",
            wrapping_key=root_key,
            wrapping_key_id="root",
        )

    return otdfctl.set_base_key(key, kas_entry_km1)
