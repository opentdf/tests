"""Key management fixtures for testing explicit KAS key operations.

This module contains fixtures for:
- Extra keys loaded from extra-keys.json
- Managed key creation and assignment
- Public key registration
- Legacy key imports
- Base key configuration
"""

import os
import json
import typing
import pytest
import abac
import tdfs
from pathlib import Path
from otdfctl import OpentdfCommandLineTool


@pytest.fixture(scope="session")
def root_key() -> str:
    """Get the root key from environment variable."""
    ot_root_key = os.getenv("OT_ROOT_KEY")
    assert ot_root_key is not None, "OT_ROOT_KEY environment variable is not set"
    return ot_root_key


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
def attribute_allof_with_two_managed_keys(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    kas_entry_km2: abac.KasEntry,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
    root_key: str,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute and assign two managed keys (RSA and EC) to it.

    - Uses km1 (rsa:2048) and km2 (ec:secp256r1)
    - Creates managed keys on each KAS
    - Assigns both keys to the same attribute (attribute-level assignment)
    - Maps both attribute values to the client SCS
    """
    pfs = tdfs.PlatformFeatureSet()
    if "key_management" not in pfs.features:
        pytest.skip(
            "Key management feature is not enabled; skipping key assignment fixture"
        )

    # Create attribute with two values under ALL_OF
    wrapping_key_id = "root"

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

    km1_rsa_key = otdfctl.kas_registry_create_key(
        kas_entry_km1,
        key_id="km1-rsa",
        mode="local",
        algorithm="rsa:2048",
        wrapping_key=root_key,
        wrapping_key_id=wrapping_key_id,
    )
    km2_ec_key = otdfctl.kas_registry_create_key(
        kas_entry_km2,
        key_id="km2-ec",
        mode="local",
        algorithm="ec:secp256r1",
        wrapping_key=root_key,
        wrapping_key_id=wrapping_key_id,
    )

    # Assign both keys to the attribute
    otdfctl.key_assign_attr(km1_rsa_key, attr)
    otdfctl.key_assign_attr(km2_ec_key, attr)

    return [attr, [km1_rsa_key.key.key_id, km2_ec_key.key.key_id]]


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
