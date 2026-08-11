import base64
import filecmp
import random
import re
import string
import subprocess
from pathlib import Path

import pytest

import tdfs
from abac import Attribute
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory

dspx1153Fails = []

try:
    dspx1153Fails = [
        tdfs.SDK("go", "v0.15.0"),
    ]
except FileNotFoundError:
    dspx1153Fails = []

#### BASIC ROUNDTRIP TESTS


def test_tdf_roundtrip(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if container == "ztdf" and decrypt_sdk in dspx1153Fails:
        pytest.skip(f"DSPX-1153 SDK [{decrypt_sdk}] has a bug with payload tampering")
    pfs = tdfs.get_platform_features()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)

    target_mode = tdfs.select_target_version(encrypt_sdk, decrypt_sdk)
    # Pin the RSA attribute so a base_key set by another module can't change
    # which mechanism wraps the KAO out from under the assertions below.
    ct_file = encrypted_tdf(
        encrypt_sdk,
        container=container,
        target_mode=target_mode,
        attr_values=attribute_default_rsa.value_fqns,
    )

    manifest = tdfs.manifest(ct_file)
    assert manifest.payload.isEncrypted
    assert len(manifest.encryptionInformation.keyAccess) == 1
    kao = manifest.encryptionInformation.keyAccess[0]
    assert kao.type == "wrapped"
    assert kao.ephemeralPublicKey is None
    if target_mode == "4.2.2" or (
        target_mode is None and not encrypt_sdk.supports("hexless")
    ):
        looks_like_422(manifest)
    else:
        looks_like_430(manifest)

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)

    # Mark timestamp before decrypt for audit log correlation
    mark = audit_logs.mark("before_decrypt")

    decrypt_sdk.decrypt(ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)

    # Verify rewrap was logged in audit logs
    audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)


def test_ec_wrapped_kao_roundtrip(
    attribute_with_ec_key: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    kas_url_km2: str,
    in_focus: set[tdfs.SDK],
    encrypted_tdf: EncryptFactory,
):
    """Roundtrip a TDF whose KAO is EC-wrapped, selected via the attribute's key.

    The wrapping mechanism is chosen by policy -- the attribute value is mapped
    to an ec:secp256r1 managed key -- rather than by a client-side override, so
    this covers the same ground the old ``ztdf-ecwrap`` container did without
    conflating the KAO wrap key with the rewrap session key (see
    ``test_pqc.py::test_session_key_roundtrip`` for the latter).

    Because key selection now runs through the policy service, this needs
    ``key_management`` + ``autoconfigure``; the retired client-side flag worked
    on platform builds predating both.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "autoconfigure")
    encrypt_sdk.skip_if_unsupported("key_management", "autoconfigure")
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_with_ec_key

    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attr.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    kao = manifest.encryptionInformation.keyAccess[0]
    assert kao.type == "ec-wrapped"
    assert kao.ephemeralPublicKey is not None
    assert kao.kid in set(key_ids)
    assert kao.url == kas_url_km2

    tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_tdf_spec_target_422(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if "hexaflexible" not in pfs.features:
        pytest.skip(f"Hexaflexible is not supported in platform {pfs.version}")
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("hexaflexible"):
        pytest.skip(
            f"Encrypt SDK {encrypt_sdk} doesn't support targeting container format 4.2.2"
        )

    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode="4.2.2",
        attr_values=attribute_default_rsa.value_fqns,
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_tdf_spec_target_430(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("hexaflexible"):
        pytest.skip(
            f"Encrypt SDK {encrypt_sdk} doesn't support targeting container format 4.3.0"
        )
    if not decrypt_sdk.supports("hexless"):
        pytest.skip(
            f"Decrypt SDK {decrypt_sdk} doesn't support hexless integrity information in container format 4.3.0"
        )

    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode="4.3.0",
        attr_values=attribute_default_rsa.value_fqns,
    )

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def looks_like_422(manifest: tdfs.Manifest):
    assert manifest.schemaVersion is None

    ii = manifest.encryptionInformation.integrityInformation
    # in 4.2.2, the root sig is hex encoded before base 64 encoding, and is twice the length
    binary_array = b64hexTobytes(ii.rootSignature.sig)
    match ii.rootSignature.alg:
        case "GMAC":
            assert len(binary_array) == 16
        case "HS256" | "" | None:
            assert len(binary_array) == 32
        case _:
            assert False, f"Unknown alg: {ii.rootSignature.alg}"

    for segment in ii.segments:
        hash = b64hexTobytes(segment.hash)
        match ii.segmentHashAlg:
            case "GMAC" | "":
                assert len(hash) == 16
            case "HS256" | "":
                assert len(hash) == 32
            case _:
                assert False, f"Unknown alg: {ii.segmentHashAlg}"


def b64hexTobytes(value: bytes) -> bytes:
    decoded = base64.b64decode(value, validate=True)
    maybe_hex = decoded.decode("ascii")
    assert maybe_hex.isalnum() and all(c in string.hexdigits for c in maybe_hex)
    binary_array = bytes.fromhex(maybe_hex)
    return binary_array


def b64Tobytes(value: bytes) -> bytes:
    decoded = base64.b64decode(value, validate=True)
    try:
        # In the unlikely event decode succeeds, at least make sure there are some non-hex-looking elememnts
        assert not all(c in string.hexdigits for c in decoded.decode("ascii"))
    except UnicodeDecodeError:
        # If decode fails (the expected behavior), we are good
        pass
    return decoded


def looks_like_430(manifest: tdfs.Manifest):
    assert manifest.schemaVersion == "4.3.0"

    ii = manifest.encryptionInformation.integrityInformation
    binary_array = b64Tobytes(ii.rootSignature.sig)
    match ii.rootSignature.alg:
        case "GMAC":
            assert len(binary_array) == 16
        case "HS256" | "":
            assert len(binary_array) == 32
        case _:
            assert False, f"Unknown alg: {ii.rootSignature.alg}"

    for segment in ii.segments:
        hash = b64Tobytes(segment.hash)
        match ii.segmentHashAlg:
            case "GMAC":
                assert len(hash) == 16
            case "HS256" | "":
                assert len(hash) == 32
            case _:
                assert False, f"Unknown alg: {ii.segmentHashAlg}"


#### MANIFEST VALIDITY TESTS


def test_manifest_validity(
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attribute_default_rsa.value_fqns,
    )

    tdfs.validate_manifest_schema(ct_file)


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
    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)

    decrypt_sdk.decrypt(
        ct_file,
        rt_file,
        "ztdf",
        assertion_verification_file_rs_and_hs_keys,
    )
    assert filecmp.cmp(pt_file, rt_file)


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


def change_last_three(byt: bytes) -> bytes:
    new_three = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=3)
    ).encode()
    if new_three == byt[-3:]:
        # catch the case where the random string is the same (v unlikely)
        return change_last_three(byt)
    return byt[:-3] + new_three


def change_policy(manifest: tdfs.Manifest) -> tdfs.Manifest:
    #  base64 decode policy from manifest.encryptionInformation.policy
    p = manifest.encryptionInformation.policy_object
    p.body.dataAttributes = []
    p.body.dissem = ["yves@dropp.er"]
    manifest.encryptionInformation.policy_object = p
    return manifest


def change_policy_binding(manifest: tdfs.Manifest) -> tdfs.Manifest:
    pb = manifest.encryptionInformation.keyAccess[0].policyBinding
    ## if the pb is str then json decode to tdfs.PolicyBinding
    if isinstance(pb, tdfs.PolicyBinding):
        hash = pb.hash
        altered_hash = base64.b64encode(change_last_three(base64.b64decode(hash)))
        pb.hash = str(altered_hash)
        manifest.encryptionInformation.keyAccess[0].policyBinding = pb
    else:
        altered_hash = base64.b64encode(change_last_three(base64.b64decode(pb)))
        manifest.encryptionInformation.keyAccess[0].policyBinding = str(altered_hash)

    return manifest


def change_root_signature(manifest: tdfs.Manifest) -> tdfs.Manifest:
    root_sig = manifest.encryptionInformation.integrityInformation.rootSignature.sig
    altered_sig = base64.b64encode(change_last_three(base64.b64decode(root_sig)))
    manifest.encryptionInformation.integrityInformation.rootSignature.sig = altered_sig
    return manifest


def change_segment_hash(manifest: tdfs.Manifest) -> tdfs.Manifest:
    assert manifest.encryptionInformation.integrityInformation.segments
    segments = manifest.encryptionInformation.integrityInformation.segments
    # choose a random segment
    index = random.randrange(len(segments))
    segment = segments[index]
    altered_hash = base64.b64encode(change_last_three(base64.b64decode(segment.hash)))
    segment.hash = altered_hash
    manifest.encryptionInformation.integrityInformation.segments[index] = segment
    return manifest


def change_encrypted_segment_size(manifest: tdfs.Manifest) -> tdfs.Manifest:
    assert manifest.encryptionInformation.integrityInformation.segments
    segments = manifest.encryptionInformation.integrityInformation.segments
    # choose a random segment
    index = random.randrange(len(segments))
    segment = segments[index]
    segment.encryptedSegmentSize = (segment.encryptedSegmentSize or 0) - 1
    manifest.encryptionInformation.integrityInformation.segments[index] = segment
    return manifest


def change_assertion_statement(manifest: tdfs.Manifest) -> tdfs.Manifest:
    assert manifest.assertions
    assertion = manifest.assertions[0]
    assertion.statement.value = "tampered"
    manifest.assertions[0] = assertion
    return manifest


def change_payload_end(payload_bytes: bytes) -> bytes:
    return change_last_three(payload_bytes)


def malicious_kao(manifest: tdfs.Manifest) -> tdfs.Manifest:
    assert manifest.encryptionInformation.keyAccess
    manifest.encryptionInformation.keyAccess[
        0
    ].url = "http://localhost:8585/malicious/kas"  # nothing running at 8585
    return manifest


### TAMPER TESTS


def assert_tamper_error(
    exc: subprocess.CalledProcessError, type: str, decrypt_sdk: tdfs.SDK
) -> None:
    btype = type.encode()
    assert btype in exc.output

    if not decrypt_sdk.supports("better-messages-2024"):
        assert re.search(
            b"integrity|signature|bad request", exc.output, re.IGNORECASE
        ), f"Unexpected error output: [{exc.output}]"
        return

    expected_error_oneof = [
        b"tamper",
    ]
    match type:
        case "root" | "signature":
            expected_error_oneof += [
                b"IntegrityError",
            ]
        case _:
            expected_error_oneof += [
                b"IntegrityError",
                b"integrity check",
            ]
    # Convert list of byte strings to regex pattern
    pattern = b"|".join(re.escape(err) for err in expected_error_oneof)
    assert re.search(pattern, exc.output, re.IGNORECASE), (
        f"Unexpected error output: [{exc.output}]"
    )


def assert_kas_request_error(
    exc: subprocess.CalledProcessError, decrypt_sdk: tdfs.SDK
) -> None:
    """Assert that a KAS request error was returned.

    Used for policy binding failures where KAS rejects the request (400).
    Accepts both the new error classification (KAS request error) and the
    legacy classification (tamper) for backward compatibility with older
    SDK versions.
    """
    expected_patterns = [
        # New classification: KAS request error
        b"KAS request error",
        b"rewrap request 400",
        b"bad request",
        b"InvalidArgument",
        # Legacy classification: tamper (older SDK versions)
        b"tamper",
        b"InvalidFileError",
        b"could not find policy in rewrap response",
    ]
    pattern = b"|".join(re.escape(p) for p in expected_patterns)
    assert re.search(pattern, exc.output, re.IGNORECASE), (
        f"Expected KAS request or tamper error, got: [{exc.output}]"
    )


## POLICY TAMPER TESTS


def test_tdf_with_unbound_policy(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("unbound_policy", ct_file, change_policy)
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)

    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_kas_request_error(exc, decrypt_sdk)


def test_tdf_with_altered_policy_binding(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "altered_policy_binding", ct_file, change_policy_binding
    )
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)

    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_kas_request_error(exc, decrypt_sdk)


## INTEGRITY TAMPER TESTS


def test_tdf_with_altered_root_sig(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("broken_root_sig", ct_file, change_root_signature)
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "root", decrypt_sdk)


def test_tdf_with_altered_seg_sig_wrong(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("broken_seg_sig", ct_file, change_segment_hash)
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(
            b_file, rt_file, "ztdf", expect_error=True, verify_assertions=False
        )
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "signature", decrypt_sdk)


## SEGMENT SIZE TAMPER TEST


def test_tdf_with_altered_enc_seg_size(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "broken_enc_seg_sig", ct_file, change_encrypted_segment_size
    )
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "", decrypt_sdk)


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


## PAYLOAD TAMPER TESTS


def test_tdf_altered_payload_end(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if decrypt_sdk in dspx1153Fails:
        pytest.skip(f"DSPX-1153 SDK [{decrypt_sdk}] has a bug with payload tampering")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = encrypted_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_payload("altered_payload_end", ct_file, change_payload_end)
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "segment", decrypt_sdk)


## KAO TAMPER TESTS


def test_tdf_with_malicious_kao(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not decrypt_sdk.supports("kasallowlist"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support an allowlist for kases")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("malicious_kao", ct_file, malicious_kao)
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)

    # Mark timestamp - note: this test may not generate a rewrap audit event
    # because the SDK should reject the malicious KAO before calling the KAS
    _mark = audit_logs.mark("before_malicious_kao_decrypt")

    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert re.search(
            b"allowlist|not allowed|disallowed KASes|AggregateError",
            exc.output,
            re.IGNORECASE | re.MULTILINE,
        ), f"Unexpected error output: [{exc.output}]"

    # Note: We don't assert on audit logs here because the SDK should reject
    # the malicious KAO client-side before making a rewrap request to the KAS
