"""Tests for hybrid post-quantum/traditional KEM.

These tests verify that TDF encryption and decryption work correctly when
X-Wing and NIST approved hybrid managed keys are assigned to attributes via the policy service.
"""

import base64
import filecmp
from pathlib import Path

import pytest

import tdfs
from abac import Attribute, KasKey
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory
from tdfs import KeyAccessObject

# Rewrap session-key algorithms, as passed to SDK.decrypt(session_key_algorithm=...)
# / the CLI wrappers, mapped to the features that must be present to try them.
# RSA is every SDK's default and needs no gate; EC rides on the existing "ecwrap"
# feature, which also covers the corrected HKDF salt.
SESSION_KEY_FEATURES: dict[str, tuple[tdfs.feature_type, ...]] = {
    "rsa:2048": (),
    "ec:secp256r1": ("ecwrap",),
    "mlkem:768": ("session-key-mlkem",),
    "mlkem:1024": ("session-key-mlkem",),
}

# X-Wing KEM sizes per draft-connolly-cfrg-xwing-kem-10
XWING_ENCAPSULATION_KEY_SIZE = 1216  # public key, bytes
XWING_CIPHERTEXT_SIZE = 1120  # KEM ciphertext (wrappedKey), bytes

# Pure ML-KEM sizes per FIPS 203 §8.
MLKEM768_ENCAPSULATION_KEY_SIZE = 1184
MLKEM768_CIPHERTEXT_SIZE = 1088
MLKEM1024_ENCAPSULATION_KEY_SIZE = 1568
MLKEM1024_CIPHERTEXT_SIZE = 1568


def _b64_decoded_len(s: str) -> int:
    """Return the byte length of a base64-encoded string."""
    return len(base64.b64decode(s))


def _pem_decoded_len(pem: str) -> int:
    """Return the byte length of the DER payload inside a PEM block."""
    lines = [ln for ln in pem.strip().splitlines() if not ln.startswith("-----")]
    return len(base64.b64decode("".join(lines)))


def assert_xwing_kao_sizes(kao: KeyAccessObject):
    """Assert that an X-Wing KAO has correctly sized wrappedKey.

    The wrappedKey is an ASN.1 DER structure containing the X-Wing KEM
    ciphertext (1120 bytes) plus an AES-GCM encrypted DEK (~60 bytes)
    and ASN.1 framing overhead, so it must be larger than the raw
    ciphertext alone.  hybrid-wrapped KAOs do not use ephemeralPublicKey.
    """
    wrapped_len = _b64_decoded_len(kao.wrappedKey)
    assert wrapped_len > XWING_CIPHERTEXT_SIZE, (
        f"X-Wing wrappedKey should be > {XWING_CIPHERTEXT_SIZE} bytes, got {wrapped_len}"
    )
    assert kao.ephemeralPublicKey is None, (
        "hybrid-wrapped X-Wing KAO should not have ephemeralPublicKey"
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
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt and decrypt with an X-Wing managed key."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure", "mechanism-xwing")
    encrypt_sdk.skip_if_unsupported(
        "key_management", "autoconfigure", "mechanism-xwing"
    )
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_pqc_hybrid_format_skew(encrypt_sdk)

    attr, key_ids = attribute_with_xwing_key

    ct_file = encrypted_tdf(
        encrypt_sdk,
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

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_xwing_with_ec_roundtrip(
    attribute_with_xwing_and_ec_keys: tuple[Attribute, list[str]],
    key_xwing: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    kas_url_km1: str,
    kas_url_km2: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt and decrypt with both X-Wing and EC keys (multi-mechanism)."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure", "mechanism-xwing")
    encrypt_sdk.skip_if_unsupported(
        "key_management", "autoconfigure", "mechanism-xwing"
    )
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_pqc_hybrid_format_skew(encrypt_sdk)

    attr, key_ids = attribute_with_xwing_and_ec_keys

    ct_file = encrypted_tdf(
        encrypt_sdk,
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
    xwing_kao = next(
        kao for kao in manifest.encryptionInformation.keyAccess if kao.kid == xwing_kid
    )
    assert xwing_kao is not None, (
        f"X-Wing KAO with kid={xwing_kid} not found in manifest"
    )

    assert_xwing_kao_sizes(xwing_kao)
    assert_xwing_public_key_size(key_xwing)

    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_secpmlkem_3_roundtrip(
    attribute_with_secpmlkem_3_key: tuple[Attribute, list[str]],
    key_secpmlkem_3: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt and decrypt with an X-Wing managed key."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure", "mechanism-secpmlkem")
    encrypt_sdk.skip_if_unsupported(
        "key_management", "autoconfigure", "mechanism-secpmlkem"
    )
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_pqc_hybrid_format_skew(encrypt_sdk)

    attr, key_ids = attribute_with_secpmlkem_3_key

    ct_file = encrypted_tdf(
        encrypt_sdk,
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

    # Verify NIST curve compatible MLKEM hybrid sizes in the KAO and registered public key
    kao = manifest.encryptionInformation.keyAccess[0]
    wrapped_len = _b64_decoded_len(kao.wrappedKey)
    assert wrapped_len > XWING_CIPHERTEXT_SIZE, (
        f"wrappedKey should be larger than {XWING_CIPHERTEXT_SIZE} bytes, got {wrapped_len}"
    )
    pem = key_secpmlkem_3.key.public_key_ctx.pem
    der_len = _pem_decoded_len(pem)
    assert der_len >= XWING_ENCAPSULATION_KEY_SIZE, (
        f"public key DER should be >= {XWING_ENCAPSULATION_KEY_SIZE} bytes, got {der_len}"
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def _assert_mlkem_kao(
    kao: KeyAccessObject,
    expected_kids: set[str],
    expected_url: str,
    min_ciphertext_size: int,
) -> None:
    assert kao.kid in expected_kids
    assert kao.url == expected_url
    # PR #3537 currently emits the legacy "wrapped" type for pure ML-KEM. Some
    # roadmap notes mention "mlkem-wrapped"; accept either so the test records
    # which one ships without breaking on a naming change.
    assert kao.type in {"wrapped", "mlkem-wrapped"}, (
        f"unexpected KAO type for ML-KEM: {kao.type!r}"
    )
    wrapped_len = _b64_decoded_len(kao.wrappedKey)
    assert wrapped_len > min_ciphertext_size, (
        f"wrappedKey should exceed raw ML-KEM ciphertext ({min_ciphertext_size}), got {wrapped_len}"
    )


def test_secpmlkem_5_roundtrip(
    attribute_with_secpmlkem_5_key: tuple[Attribute, list[str]],
    key_secpmlkem_5: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt and decrypt with an X-Wing managed key."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure", "mechanism-secpmlkem")
    encrypt_sdk.skip_if_unsupported(
        "key_management", "autoconfigure", "mechanism-secpmlkem"
    )
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_pqc_hybrid_format_skew(encrypt_sdk)

    attr, key_ids = attribute_with_secpmlkem_5_key

    ct_file = encrypted_tdf(
        encrypt_sdk,
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

    # Verify NIST curve compatible MLKEM hybrid sizes in the KAO and registered public key
    kao = manifest.encryptionInformation.keyAccess[0]
    wrapped_len = _b64_decoded_len(kao.wrappedKey)
    assert wrapped_len > XWING_CIPHERTEXT_SIZE, (
        f"wrappedKey should be larger than {XWING_CIPHERTEXT_SIZE} bytes, got {wrapped_len}"
    )
    pem = key_secpmlkem_5.key.public_key_ctx.pem
    der_len = _pem_decoded_len(pem)
    assert der_len >= XWING_ENCAPSULATION_KEY_SIZE, (
        f"public key DER should be >= {XWING_ENCAPSULATION_KEY_SIZE} bytes, got {der_len}"
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_mlkem_768_roundtrip(
    attribute_with_mlkem_768_key: tuple[Attribute, list[str]],
    key_mlkem_768: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt with a pure ML-KEM-768 managed key, then attempt decrypt.

    The decrypt SDK is intentionally NOT pre-skipped on `mechanism-mlkem` so
    we can observe whether SDKs lacking explicit pure-mlkem support can still
    process the new ``mlkem-wrapped`` KAO type.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure", "mechanism-mlkem")
    encrypt_sdk.skip_if_unsupported(
        "key_management", "autoconfigure", "mechanism-mlkem"
    )
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_with_mlkem_768_key

    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    _assert_mlkem_kao(
        manifest.encryptionInformation.keyAccess[0],
        expected_kids=set(key_ids),
        expected_url=kas_url_km1,
        min_ciphertext_size=MLKEM768_CIPHERTEXT_SIZE,
    )
    der_len = _pem_decoded_len(key_mlkem_768.key.public_key_ctx.pem)
    assert der_len >= MLKEM768_ENCAPSULATION_KEY_SIZE, (
        f"public key DER should be >= {MLKEM768_ENCAPSULATION_KEY_SIZE} bytes, got {der_len}"
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


@pytest.mark.parametrize("session_key_algorithm", list(SESSION_KEY_FEATURES))
def test_session_key_roundtrip(
    session_key_algorithm: str,
    attribute_default_rsa: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
    audit_logs: AuditLogAsserter,
):
    """Rewrap with an explicitly-requested client-generated ephemeral session key.

    The session key is the ephemeral key the KAS wraps its rewrap response back
    to. It is a separate axis from the TDF's own KAO wrapping mechanism, so
    every case here encrypts against a plain RSA-wrapped attribute key: a
    failure can then only be attributed to the session-key channel, not to
    KAS-managed mechanism support (covered by the mechanism-* tests above).

    A successful decrypt alone doesn't prove KAS honored the request -- it
    would also succeed if the SDK silently fell back to its default and KAS
    answered in kind. So each case asserts on KAS's rewrap audit log, which
    records the parsed clientPublicKey's type (eventMetaData.sessionKeyType)
    independently of anything the client reports about itself.

    rsa:2048 is included even though it is every SDK's default, because it is
    requested *explicitly* here -- ordinary roundtrip tests can't pin a
    session_key_type without becoming brittle to a future default change.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip(f"Not in focus: encrypt={encrypt_sdk}, decrypt={decrypt_sdk}")
    pfs = tdfs.get_platform_features()
    required = SESSION_KEY_FEATURES[session_key_algorithm]
    pfs.skip_if_unsupported(*required)
    decrypt_sdk.skip_if_unsupported(*required)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attribute_default_rsa.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].type == "wrapped"

    mark = audit_logs.mark("before_decrypt")
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk, variant=session_key_algorithm)
    decrypt_sdk.decrypt(
        ct_file, rt_file, "ztdf", session_key_algorithm=session_key_algorithm
    )
    assert filecmp.cmp(pt_file, rt_file, shallow=False)

    audit_logs.assert_rewrap_session_key_type(session_key_algorithm, since_mark=mark)


def test_mlkem_1024_roundtrip(
    attribute_with_mlkem_1024_key: tuple[Attribute, list[str]],
    key_mlkem_1024: KasKey,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Encrypt with a pure ML-KEM-1024 managed key, then attempt decrypt.

    See ``test_mlkem_768_roundtrip`` for the decrypt-SDK skip rationale.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure", "mechanism-mlkem")
    encrypt_sdk.skip_if_unsupported(
        "key_management", "autoconfigure", "mechanism-mlkem"
    )
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_with_mlkem_1024_key

    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    _assert_mlkem_kao(
        manifest.encryptionInformation.keyAccess[0],
        expected_kids=set(key_ids),
        expected_url=kas_url_km1,
        min_ciphertext_size=MLKEM1024_CIPHERTEXT_SIZE,
    )
    der_len = _pem_decoded_len(key_mlkem_1024.key.public_key_ctx.pem)
    assert der_len >= MLKEM1024_ENCAPSULATION_KEY_SIZE, (
        f"public key DER should be >= {MLKEM1024_ENCAPSULATION_KEY_SIZE} bytes, got {der_len}"
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
