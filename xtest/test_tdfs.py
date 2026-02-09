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

cipherTexts: dict[str, Path] = {}
counter = 0

#### HELPERS


def do_encrypt_with(
    pt_file: Path,
    encrypt_sdk: tdfs.SDK,
    container: tdfs.container_type,
    tmp_dir: Path,
    az: str = "",
    scenario: str = "",
    target_mode: tdfs.container_version | None = None,
    attr_values: list[str] | None = None,
) -> Path:
    """
    Encrypt a file with the given SDK and container type, and return the path to the ciphertext file.

    Scenario is used to create a unique filename for the ciphertext file.

    If targetmode is set, asserts that the manifest is in the correct format for that target.

    If attr_values is provided, uses those attribute FQNs to ensure deterministic key selection.
    This prevents test flakiness when base_key is configured on the platform.
    """
    global counter
    counter = (counter or 0) + 1
    c = counter
    container_id = f"{encrypt_sdk}-{container}"
    if scenario != "":
        container_id += f"-{scenario}"
    if container_id in cipherTexts:
        return cipherTexts[container_id]
    ct_file = tmp_dir / f"test-{encrypt_sdk}-{scenario}{c}.{container}"

    use_ecwrap = container == "ztdf-ecwrap"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        mime_type="text/plain",
        container=container,
        attr_values=attr_values,
        assert_value=az,
        target_mode=target_mode,
    )

    assert ct_file.is_file()

    if tdfs.simple_container(container) == "ztdf":
        manifest = tdfs.manifest(ct_file)
        assert manifest.payload.isEncrypted
        assert len(manifest.encryptionInformation.keyAccess) == 1
        kao = manifest.encryptionInformation.keyAccess[0]
        if use_ecwrap:
            assert kao.type == "ec-wrapped"
            assert kao.ephemeralPublicKey is not None
        else:
            assert kao.type == "wrapped"
            assert kao.ephemeralPublicKey is None
        if target_mode == "4.2.2":
            looks_like_422(manifest)
        elif target_mode == "4.3.0":
            looks_like_430(manifest)
        elif not encrypt_sdk.supports("hexless"):
            looks_like_422(manifest)
        else:
            looks_like_430(manifest)
    else:
        assert False, f"Unknown container type: {container}"
    cipherTexts[container_id] = ct_file
    return ct_file


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
    tmp_dir: Path,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    attribute_default_rsa: Attribute,
):
    if container == "ztdf" and decrypt_sdk in dspx1153Fails:
        pytest.skip(f"DSPX-1153 SDK [{decrypt_sdk}] has a bug with payload tampering")
    pfs = tdfs.PlatformFeatureSet()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if container == "ztdf-ecwrap":
        if not encrypt_sdk.supports("ecwrap"):
            pytest.skip(f"{encrypt_sdk} sdk doesn't yet support ecwrap bindings")
        if "ecwrap" not in pfs.features:
            pytest.skip(
                f"{pfs.version} opentdf platform doesn't yet support ecwrap bindings"
            )
        # Unlike javascript, Java and Go don't support ecwrap if on older versions since they don't pass on the ephemeral public key
        if decrypt_sdk.sdk != "js" and not decrypt_sdk.supports("ecwrap"):
            pytest.skip(
                f"{decrypt_sdk} sdk doesn't support ecwrap bindings for decrypt"
            )

    target_mode = tdfs.select_target_version(encrypt_sdk, decrypt_sdk)
    # Use explicit RSA attribute when not using EC wrapping to avoid base_key interference
    attr_values = None if container == "ztdf-ecwrap" else attribute_default_rsa.value_fqns
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        container,
        tmp_dir,
        target_mode=target_mode,
        attr_values=attr_values,
    )

    fname = ct_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"

    # Mark timestamp before decrypt for audit log correlation
    mark = audit_logs.mark("before_decrypt")

    decrypt_sdk.decrypt(ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)

    # Verify rewrap was logged in audit logs
    audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)

    if (
        container.startswith("ztdf")
        and decrypt_sdk.supports("ecwrap")
        and "ecwrap" in pfs.features
    ):
        ert_file = tmp_dir / f"{fname}-ecrewrap.untdf"
        ec_mark = audit_logs.mark("before_ecwrap_decrypt")
        decrypt_sdk.decrypt(ct_file, ert_file, container, ecwrap=True)
        assert filecmp.cmp(pt_file, ert_file)
        # Verify ecwrap rewrap was also logged
        audit_logs.assert_rewrap_success(min_count=1, since_mark=ec_mark)


def test_tdf_spec_target_422(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if "hexaflexible" not in pfs.features:
        pytest.skip(f"Hexaflexible is not supported in platform {pfs.version}")
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("hexaflexible"):
        pytest.skip(
            f"Encrypt SDK {encrypt_sdk} doesn't support targeting container format 4.2.2"
        )

    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="target-422",
        target_mode="4.2.2",
        attr_values=attribute_default_rsa.value_fqns,
    )

    fname = ct_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
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
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        attr_values=attribute_default_rsa.value_fqns,
    )

    tdfs.validate_manifest_schema(ct_file)


def test_manifest_validity_with_assertions(
    encrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=assertion_file_no_keys,
        attr_values=attribute_default_rsa.value_fqns,
    )

    tdfs.validate_manifest_schema(ct_file)


#### ASSERTION TESTS


def test_tdf_assertions_unkeyed(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    pfs = tdfs.PlatformFeatureSet()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=assertion_file_no_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    fname = ct_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_tdf_assertions_with_keys(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    pfs = tdfs.PlatformFeatureSet()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions-keys-roundtrip",
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    fname = ct_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"

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
    tmp_dir: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("hexaflexible"):
        pytest.skip(
            f"Encrypt SDK {encrypt_sdk} doesn't support targeting container format 4.2.2"
        )
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions-422-keys-roundtrip",
        az=assertion_file_rs_and_hs_keys,
        target_mode="4.2.2",
        attr_values=attribute_default_rsa.value_fqns,
    )

    fname = ct_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"

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
        b"could not find policy in rewrap response",  # For older versions of go sdk, we get "InvalidFileError" instead of "tamper".
    ]
    match type:
        case "wrap":
            expected_error_oneof += [
                b"InvalidFileError",
            ]
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


## POLICY TAMPER TESTS


def test_tdf_with_unbound_policy(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    attribute_default_rsa: Attribute,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("unbound_policy", ct_file, change_policy)
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"

    # Mark timestamp before tampered decrypt for audit log correlation
    # mark = audit_logs.mark("before_tampered_decrypt")

    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "wrap", decrypt_sdk)

    # Verify rewrap failure was logged (policy binding mismatch)
    # FIXME: Audit logs are not present on failed bindings
    # audit_logs.assert_rewrap_error(min_count=1, since_mark=mark)


def test_tdf_with_altered_policy_binding(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    attribute_default_rsa: Attribute,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "altered_policy_binding", ct_file, change_policy_binding
    )
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"

    # Mark timestamp before tampered decrypt for audit log correlation
    # mark = audit_logs.mark("before_tampered_decrypt")

    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "wrap", decrypt_sdk)

    # Verify rewrap failure was logged (policy binding mismatch)
    # FIXME: Audit logs are not present on failed bindings
    # audit_logs.assert_rewrap_error(min_count=1, since_mark=mark)


## INTEGRITY TAMPER TESTS


def test_tdf_with_altered_root_sig(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("broken_root_sig", ct_file, change_root_signature)
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "root", decrypt_sdk)


def test_tdf_with_altered_seg_sig_wrong(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("broken_seg_sig", ct_file, change_segment_hash)
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
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
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "broken_enc_seg_sig", ct_file, change_encrypted_segment_size
    )
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "", decrypt_sdk)


## ASSERTION TAMPER TESTS


def test_tdf_with_altered_assertion_statement(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=assertion_file_no_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "altered_assertion_statement", ct_file, change_assertion_statement
    )
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "assertion", decrypt_sdk)


def test_tdf_with_altered_assertion_with_keys(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions-keys-roundtrip-altered",
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest(
        "altered_assertion_statement", ct_file, change_assertion_statement
    )
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
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
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if decrypt_sdk in dspx1153Fails:
        pytest.skip(f"DSPX-1153 SDK [{decrypt_sdk}] has a bug with payload tampering")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_payload("altered_payload_end", ct_file, change_payload_end)
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"
    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert_tamper_error(exc, "segment", decrypt_sdk)


## KAO TAMPER TESTS


def test_tdf_with_malicious_kao(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    attribute_default_rsa: Attribute,
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not decrypt_sdk.supports("kasallowlist"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support an allowlist for kases")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_manifest("malicious_kao", ct_file, malicious_kao)
    fname = b_file.stem
    rt_file = tmp_dir / f"{fname}.untdf"

    # Mark timestamp - note: this test may not generate a rewrap audit event
    # because the SDK should reject the malicious KAO before calling the KAS
    _mark = audit_logs.mark("before_malicious_kao_decrypt")

    try:
        decrypt_sdk.decrypt(b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert re.search(
            b"allowlist|not allowed|disallowed KASes",
            exc.output,
            re.IGNORECASE | re.MULTILINE,
        ), f"Unexpected error output: [{exc.output}]"

    # Note: We don't assert on audit logs here because the SDK should reject
    # the malicious KAO client-side before making a rewrap request to the KAS
