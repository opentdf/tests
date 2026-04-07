"""Key management fixtures for testing explicit KAS key operations.

This module contains fixtures for:
- Extra keys loaded from extra-keys.json
- Managed key creation and assignment (RSA, EC, X-Wing)
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


def _get_or_create_key(
    otdfctl: OpentdfCommandLineTool,
    kas_entry: abac.KasEntry,
    key_id_prefix: str,
    algorithm: abac.kas_algorithm_type,
    root_key: str,
    *required_features: tdfs.feature_type,
) -> abac.KasKey:
    """Get or create a managed key, skipping if required platform features are missing.

    Key ID is "{prefix}-{root_key_hash}" to ensure uniqueness across root key changes.
    """
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", *required_features)

    key_id = f"{key_id_prefix}-{_key_id_suffix(root_key)}"
    existing_keys = otdfctl.kas_registry_keys_list(kas_entry)
    key = next((k for k in existing_keys if k.key.key_id == key_id), None)
    if key is None:
        key = otdfctl.kas_registry_create_key(
            kas_entry,
            key_id=key_id,
            mode="local",
            algorithm=algorithm,
            wrapping_key=root_key,
            wrapping_key_id="root",
        )
    return key


def _create_keyed_attribute(
    otdfctl: OpentdfCommandLineTool,
    namespace: abac.Namespace,
    attr_name: str,
    value_key_pairs: list[tuple[str, abac.KasKey]],
    scs: abac.SubjectConditionSet,
    *required_features: tdfs.feature_type,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute, SCS-map each value, and assign keys at value level.

    Returns (attribute, [key_id, ...]).
    """
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", *required_features)

    value_names = [name for name, _ in value_key_pairs]
    attr = otdfctl.attribute_create(
        namespace, attr_name, abac.AttributeRule.ALL_OF, value_names
    )
    assert attr.values and len(attr.values) == len(value_key_pairs)

    for val, (expected_name, key) in zip(attr.values, value_key_pairs, strict=True):
        assert val.value == expected_name
        sm = otdfctl.scs_map(scs, val)
        assert sm.attribute_value.value == val.value
        otdfctl.key_assign_value(key, val)

    return (attr, [key.key.key_id for _, key in value_key_pairs])


# ---------------------------------------------------------------------------
# Extra keys (loaded from JSON)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Managed key fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def managed_key_km1_rsa(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create RSA managed key on km1."""
    return _get_or_create_key(otdfctl, kas_entry_km1, "km1-rsa", "rsa:2048", root_key)


@pytest.fixture(scope="module")
def managed_key_km2_ec(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC managed key on km2."""
    return _get_or_create_key(
        otdfctl, kas_entry_km2, "km2-ec", "ec:secp256r1", root_key
    )


@pytest.fixture(scope="module")
def key_e256(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC secp256r1 managed key on km2."""
    return _get_or_create_key(otdfctl, kas_entry_km2, "e256", "ec:secp256r1", root_key)


@pytest.fixture(scope="module")
def key_e384(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC secp384r1 managed key on km2."""
    return _get_or_create_key(otdfctl, kas_entry_km2, "e384", "ec:secp384r1", root_key)


@pytest.fixture(scope="module")
def key_e521(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create EC secp521r1 managed key on km2."""
    return _get_or_create_key(otdfctl, kas_entry_km2, "e521", "ec:secp521r1", root_key)


@pytest.fixture(scope="module")
def key_r2048(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create RSA 2048 managed key on km1."""
    return _get_or_create_key(otdfctl, kas_entry_km1, "r2048", "rsa:2048", root_key)


@pytest.fixture(scope="module")
def key_r4096(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create RSA 4096 managed key on km1."""
    return _get_or_create_key(otdfctl, kas_entry_km1, "r4096", "rsa:4096", root_key)


@pytest.fixture(scope="module")
def key_xwing(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km1: abac.KasEntry,
    root_key: str,
) -> abac.KasKey:
    """Get or create X-Wing hybrid PQ/T managed key on km1."""
    return _get_or_create_key(
        otdfctl, kas_entry_km1, "xwing", "hpqt:xwing", root_key, "mechanism-xwing"
    )


# ---------------------------------------------------------------------------
# Attribute + key assignment fixtures (value-level)
# ---------------------------------------------------------------------------


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
    """Create an ALL_OF attribute and assign extended mechanism keys to it."""
    return _create_keyed_attribute(
        otdfctl,
        temporary_namespace,
        "mechanism-select",
        [
            ("ec-secp256r1", key_e256),
            ("ec-secp384r1", key_e384),
            ("ec-secp521r1", key_e521),
            ("rsa-2048", key_r2048),
            ("rsa-4096", key_r4096),
        ],
        otdf_client_scs,
    )


@pytest.fixture(scope="module")
def attribute_with_different_kids(
    otdfctl: OpentdfCommandLineTool,
    temporary_namespace: abac.Namespace,
    public_key_kas_default_kid_r1: abac.KasKey,
    public_key_kas_default_kid_e1: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
) -> abac.Attribute:
    """Create an attribute with different KAS public keys (value-level assignment)."""
    attr, _ = _create_keyed_attribute(
        otdfctl,
        temporary_namespace,
        "multikeys",
        [("r1", public_key_kas_default_kid_r1), ("e1", public_key_kas_default_kid_e1)],
        otdf_client_scs,
    )
    return attr


@pytest.fixture(scope="module")
def attribute_with_xwing_key(
    otdfctl: OpentdfCommandLineTool,
    key_xwing: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute and assign an X-Wing key to it."""
    return _create_keyed_attribute(
        otdfctl,
        temporary_namespace,
        "xwing-test",
        [("xw1", key_xwing)],
        otdf_client_scs,
        "mechanism-xwing",
    )


@pytest.fixture(scope="module")
def attribute_with_xwing_and_ec_keys(
    otdfctl: OpentdfCommandLineTool,
    key_xwing: abac.KasKey,
    managed_key_km2_ec: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute with both X-Wing and EC keys assigned."""
    return _create_keyed_attribute(
        otdfctl,
        temporary_namespace,
        "xwing-hybrid-test",
        [("xw1", key_xwing), ("ec1", managed_key_km2_ec)],
        otdf_client_scs,
        "mechanism-xwing",
    )


# ---------------------------------------------------------------------------
# Attribute + key assignment fixture (attribute-level)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def attribute_allof_with_two_managed_keys(
    otdfctl: OpentdfCommandLineTool,
    managed_key_km1_rsa: abac.KasKey,
    managed_key_km2_ec: abac.KasKey,
    otdf_client_scs: abac.SubjectConditionSet,
    temporary_namespace: abac.Namespace,
) -> tuple[abac.Attribute, list[str]]:
    """Create an ALL_OF attribute and assign two managed keys at attribute level."""
    tdfs.get_platform_features().skip_if_unsupported("key_management")

    attr = otdfctl.attribute_create(
        temporary_namespace, "kmallof", abac.AttributeRule.ALL_OF, ["r1", "e1"]
    )
    assert attr.values and len(attr.values) == 2
    r1, e1 = attr.values
    assert r1.value == "r1"
    assert e1.value == "e1"

    for val in [r1, e1]:
        sm = otdfctl.scs_map(otdf_client_scs, val)
        assert sm.attribute_value.value == val.value

    otdfctl.key_assign_attr(managed_key_km1_rsa, attr)
    otdfctl.key_assign_attr(managed_key_km2_ec, attr)

    return (attr, [managed_key_km1_rsa.key.key_id, managed_key_km2_ec.key.key_id])


# ---------------------------------------------------------------------------
# Public key registration fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Legacy and base key fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def legacy_imported_golden_r1_key(
    otdfctl: OpentdfCommandLineTool,
    kas_entry_km2: abac.KasEntry,
    extra_keys: dict[str, ExtraKey],
    root_key: str,
) -> abac.KasKey:
    """Import (or reuse) the legacy 'golden-r1' key for decrypting golden TDFs."""
    tdfs.get_platform_features().skip_if_unsupported("key_management")

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
    """Ensure a managed key 'e1' exists on km1 and is configured as the base key."""
    tdfs.get_platform_features().skip_if_unsupported("key_management")

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
