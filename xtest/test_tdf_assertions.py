import base64
import filecmp
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

import assertions
import tdfs
from abac import Attribute
from fixtures.encryption import EncryptFactory
from test_tdfs import assert_tamper_error, looks_like_422

pytestmark = pytest.mark.core

#### MANIFEST VALIDITY TESTS


def test_manifest_validity_with_assertions(
    encrypt_sdk: tdfs.SDK,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_no_keys,
        attr_values=attribute_default_rsa.value_fqns,
    )

    tdfs.validate_manifest_schema(ct_file)
    assertions.assert_bound(
        tdfs.manifest_json(ct_file),
        assertions.load_assertions(assertion_file_no_keys),
    )


#### ASSERTION TESTS


def test_tdf_assertions_unkeyed(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    pfs = tdfs.get_platform_features()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_no_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    assertions.assert_bound(
        tdfs.manifest_json(ct_file),
        assertions.load_assertions(assertion_file_no_keys),
    )
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_tdf_assertions_with_keys(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    pfs = tdfs.get_platform_features()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    assertions.assert_bound(
        tdfs.manifest_json(ct_file),
        assertions.load_assertions(assertion_file_rs_and_hs_keys),
        assertions.load_verification_keys(assertion_verification_file_rs_and_hs_keys),
    )
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)

    decrypt_sdk.decrypt(
        ct_file,
        rt_file,
        "ztdf",
        assertion_verification_file_rs_and_hs_keys,
    )
    assert filecmp.cmp(pt_file, rt_file)


def _jws_segment(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def _embedded_rsa_header(
    signer: rsa.RSAPrivateKey, embedded: Literal["jwk", "x5c"]
) -> dict[str, object]:
    public = signer.public_key()
    if embedded == "jwk":
        numbers = public.public_numbers()

        def unsigned(value: int) -> str:
            data = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

        return {
            "alg": "RS256",
            "jwk": {
                "kty": "RSA",
                "n": unsigned(numbers.n),
                "e": unsigned(numbers.e),
                "use": "sig",
                "alg": "RS256",
            },
        }

    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "xtest assertion signer")]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(public)
        .serial_number(1)
        .not_valid_before(datetime(2020, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2040, 1, 1, tzinfo=UTC))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .sign(signer, hashes.SHA256())
    )
    return {
        "alg": "RS256",
        "x5c": [
            base64.b64encode(
                certificate.public_bytes(serialization.Encoding.DER)
            ).decode("ascii")
        ],
    }


def _signed_key_override_variant(
    ct_file: Path,
    variant: str,
    signer: rsa.RSAPrivateKey,
    embedded: Literal["jwk", "x5c"],
) -> Path:
    """Change a handling statement and bind it with the given signer's key."""

    def change(manifest: tdfs.Manifest) -> tdfs.Manifest:
        assert manifest.assertions is not None
        matches = [a for a in manifest.assertions if a.id == "assertion2"]
        assert len(matches) == 1, "writer must emit the keyed RS256 assertion"
        label = matches[0]
        assert isinstance(label.statement.value, str)
        statement = json.loads(label.statement.value)
        statement["ocl"]["cls"] = "UNCLASSIFIED"
        label.statement.value = json.dumps(
            statement, separators=(",", ":"), sort_keys=True
        )

        raw = manifest.model_dump(by_alias=True, exclude_unset=True)
        raw_label = next(a for a in raw["assertions"] if a["id"] == "assertion2")
        hash_hex = assertions.assertion_hash(raw_label)
        claims = {
            "assertionHash": hash_hex,
            "assertionSig": assertions.assertion_sig(raw, hash_hex),
        }
        signing_input = (
            _jws_segment(_embedded_rsa_header(signer, embedded))
            + "."
            + _jws_segment(claims)
        )
        signature = signer.sign(
            signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
        )
        token = (
            signing_input
            + "."
            + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
        )
        label.binding = assertions.Binding(method="jws", signature=token)
        return manifest

    result = tdfs.update_manifest(f"dspx4686-{variant}-{embedded}", ct_file, change)
    raw = tdfs.manifest_json(result)
    label = next(a for a in raw["assertions"] if a["id"] == "assertion2")
    jws = assertions.parse_jws(label["binding"]["signature"])
    hash_hex = assertions.assertion_hash(label)
    assert jws.claims == {
        "assertionHash": hash_hex,
        "assertionSig": assertions.assertion_sig(raw, hash_hex),
    }, "fixture binding must cover the altered statement and this payload"
    public_pem = signer.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    assertions.verify_jws_signature(
        jws, assertions.AssertionKey(alg="RS256", key=public_pem.decode("ascii"))
    )
    return result


@pytest.mark.parametrize("embedded", ["jwk", "x5c"])
def test_embedded_key_cannot_override_configured_key(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    rs256_keys: tuple[str, str],
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
    embedded: Literal["jwk", "x5c"],
) -> None:
    """DSPX-4686: an embedded signer cannot replace the per-ID verification key."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    decrypt_sdk.skip_if_unsupported(
        "assertion_verification", "assertion_selected_key_only"
    )

    configured = serialization.load_pem_private_key(
        rs256_keys[0].encode("ascii"), password=None
    )
    assert isinstance(configured, rsa.RSAPrivateKey)
    unrelated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert (
        configured.public_key().public_numbers()
        != unrelated.public_key().public_numbers()
    )

    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    control = _signed_key_override_variant(ct_file, "configured", configured, embedded)
    control_out = encrypted_tdf.rt_file(control, decrypt_sdk, "configured")
    decrypt_sdk.decrypt(
        control, control_out, "ztdf", assertion_verification_file_rs_and_hs_keys
    )
    assert filecmp.cmp(pt_file, control_out)

    forged = _signed_key_override_variant(ct_file, "unrelated", unrelated, embedded)
    forged_out = encrypted_tdf.rt_file(forged, decrypt_sdk, "unrelated")
    with pytest.raises(subprocess.CalledProcessError):
        decrypt_sdk.decrypt(
            forged,
            forged_out,
            "ztdf",
            assertion_verification_file_rs_and_hs_keys,
            expect_error=True,
        )


def test_tdf_assertions_422_format(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("hexaflexible"):
        pytest.skip(
            f"Encrypt SDK {encrypt_sdk} doesn't support targeting container format 4.2.2"
        )
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_rs_and_hs_keys,
        target_mode="4.2.2",
        attr_values=attribute_default_rsa.value_fqns,
    )
    looks_like_422(tdfs.manifest(ct_file))
    assertions.assert_bound(
        tdfs.manifest_json(ct_file),
        assertions.load_assertions(assertion_file_rs_and_hs_keys),
        assertions.load_verification_keys(assertion_verification_file_rs_and_hs_keys),
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)

    decrypt_sdk.decrypt(
        ct_file,
        rt_file,
        "ztdf",
        assertion_verification_file_rs_and_hs_keys,
    )
    assert filecmp.cmp(pt_file, rt_file)


#### TAMPER

## TAMPER FUNCTIONS


def change_assertion_statement(manifest: tdfs.Manifest) -> tdfs.Manifest:
    assert manifest.assertions
    assertion = manifest.assertions[0]
    assertion.statement.value = "tampered"
    manifest.assertions[0] = assertion
    return manifest


## ASSERTION TAMPER TESTS


def test_tdf_with_altered_assertion_statement(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_no_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "altered_assertion_statement", ct_file, change_assertion_statement
    )
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "assertion", decrypt_sdk)


def test_tdf_with_altered_assertion_with_keys(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "altered_assertion_statement", ct_file, change_assertion_statement
    )
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(
            b_file,
            rt_file,
            "ztdf",
            assertion_verification_file_rs_and_hs_keys,
            expect_error=True,
        )
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "assertion", decrypt_sdk)
