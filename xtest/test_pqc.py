"""Tests for X-Wing hybrid post-quantum/traditional KEM (ML-KEM-768 + X25519).

These tests verify that TDF encryption and decryption work correctly when
X-Wing managed keys are assigned to attributes via the policy service.
"""

import base64
import filecmp
from pathlib import Path

import pytest

import tdfs
from abac import Attribute, KasKey
from tdfs import KeyAccessObject

cipherTexts: dict[str, Path] = {}

# X-Wing KEM sizes per draft-connolly-cfrg-xwing-kem-10
XWING_ENCAPSULATION_KEY_SIZE = 1216  # public key, bytes
XWING_CIPHERTEXT_SIZE = 1120  # KEM ciphertext (wrappedKey), bytes


def _b64_decoded_len(s: str) -> int:
    """Return the byte length of a base64-encoded string."""
    return len(base64.b64decode(s))


def _pem_decoded_len(pem: str) -> int:
    """Return the byte length of the DER payload inside a PEM block."""
    lines = [
        ln
        for ln in pem.strip().splitlines()
        if not ln.startswith("-----")
    ]
    return len(base64.b64decode("".join(lines)))


def assert_xwing_kao_sizes(kao: KeyAccessObject):
    """Assert that an X-Wing KAO has correctly sized wrappedKey and ephemeralPublicKey."""
    wrapped_len = _b64_decoded_len(kao.wrappedKey)
    assert wrapped_len == XWING_CIPHERTEXT_SIZE, (
        f"X-Wing wrappedKey should be {XWING_CIPHERTEXT_SIZE} bytes, got {wrapped_len}"
    )
    assert kao.ephemeralPublicKey is not None, (
        "X-Wing KAO must include an ephemeralPublicKey"
    )
    epk_len = _b64_decoded_len(kao.ephemeralPublicKey)
    assert epk_len == XWING_ENCAPSULATION_KEY_SIZE, (
        f"X-Wing ephemeralPublicKey should be {XWING_ENCAPSULATION_KEY_SIZE} bytes, got {epk_len}"
    )


def assert_xwing_public_key_size(kas_key: KasKey):
    """Assert that the KAS registry public key for X-Wing is the expected size."""
    pem = kas_key.key.public_key_ctx.pem
    der_len = _pem_decoded_len(pem)
    assert der_len >= XWING_ENCAPSULATION_KEY_SIZE, (
        f"X-Wing public key DER should be >= {XWING_ENCAPSULATION_KEY_SIZE} bytes, got {der_len}"
    )


def test_xwing_roundtrip(
    attribute_with_xwing_key: tuple[Attribute, list[str]],
    key_xwing: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
):
    """Encrypt and decrypt with an X-Wing managed key."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.require("key_management", "autoconfigure", "mechanism-xwing")
    encrypt_sdk.skip_if_unsupported("key_management", "autoconfigure", "mechanism-xwing")
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_with_xwing_key

    sample_name = f"xwing-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=attr.value_fqns,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1

    manifest_kids = {kao.kid for kao in manifest.encryptionInformation.keyAccess}
    expected_kids = set(key_ids)
    assert manifest_kids == expected_kids, (
        f"Expected key IDs {expected_kids} but got {manifest_kids}"
    )

    manifest_urls = {kao.url for kao in manifest.encryptionInformation.keyAccess}
    assert kas_url_km1 in manifest_urls

    # Verify X-Wing KEM sizes in the KAO and registered public key
    kao = manifest.encryptionInformation.keyAccess[0]
    assert_xwing_kao_sizes(kao)
    assert_xwing_public_key_size(key_xwing)

    rt_file = tmp_dir / f"xwing-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_xwing_with_ec_roundtrip(
    attribute_with_xwing_and_ec_keys: tuple[Attribute, list[str]],
    key_xwing: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_km1: str,
    kas_url_km2: str,
    in_focus: set[tdfs.SDK],
):
    """Encrypt and decrypt with both X-Wing and EC keys (multi-mechanism)."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.require("key_management", "autoconfigure", "mechanism-xwing")
    encrypt_sdk.skip_if_unsupported("key_management", "autoconfigure", "mechanism-xwing")
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_with_xwing_and_ec_keys

    sample_name = f"xwing-ec-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=attr.value_fqns,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2

    manifest_kids = {kao.kid for kao in manifest.encryptionInformation.keyAccess}
    expected_kids = set(key_ids)
    assert manifest_kids == expected_kids, (
        f"Expected key IDs {expected_kids} but got {manifest_kids}"
    )

    manifest_urls = {kao.url for kao in manifest.encryptionInformation.keyAccess}
    assert manifest_urls <= {kas_url_km1, kas_url_km2}, (
        f"Expected KAS URLs from km1 or km2, but got {manifest_urls}"
    )

    # Verify X-Wing KEM sizes on the xwing KAO
    xwing_kid = key_xwing.key.key_id
    for kao in manifest.encryptionInformation.keyAccess:
        if kao.kid == xwing_kid:
            assert_xwing_kao_sizes(kao)
    assert_xwing_public_key_size(key_xwing)

    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"xwing-ec-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
