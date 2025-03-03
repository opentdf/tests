import filecmp
import os
import subprocess
import base64
import string
import random

import pytest

import nano
import tdfs


cipherTexts: dict[str, str] = {}
counter = 0

#### HELPERS


def skip_hexless_skew(encrypt_sdk: tdfs.sdk_type, decrypt_sdk: tdfs.sdk_type):
    if tdfs.supports(encrypt_sdk, "hexless") and not tdfs.supports(
        decrypt_sdk, "hexless"
    ):
        pytest.skip(
            f"{decrypt_sdk} sdk doesn't yet support [hexless], but {encrypt_sdk} does"
        )


def simple_container(container: tdfs.container_type) -> tdfs.container_type:
    if container == "nano-with-ecdsa":
        return "nano"
    if container == "ztdf-ecwrap":
        return "ztdf"
    return container


def do_encrypt_with(
    pt_file: str,
    encrypt_sdk: tdfs.sdk_type,
    container: tdfs.container_type,
    tmp_dir: str,
    az: str = "",
    scenario: str = "",
) -> str:
    global counter
    counter = (counter or 0) + 1
    c = counter
    container_id = f"{encrypt_sdk}-{container}"
    if scenario != "":
        container_id += f"-{scenario}"
    if container_id in cipherTexts:
        return cipherTexts[container_id]
    ct_file = f"{tmp_dir}test-{encrypt_sdk}-{scenario}{c}.{container}"

    use_ecdsa = container == "nano-with-ecdsa"
    use_ecwrap = container == "ztdf-ecwrap"
    fmt = simple_container(container)
    tdfs.encrypt(
        encrypt_sdk,
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt=fmt,
        use_ecdsa_binding=use_ecdsa,
        assert_value=az,
        ecwrap=use_ecwrap,
    )
    if fmt == "ztdf":
        manifest = tdfs.manifest(ct_file)
        assert manifest.payload.isEncrypted
        if use_ecwrap:
            assert manifest.encryptionInformation.keyAccess[0].type == "ec-wrapped"
        else:
            assert manifest.encryptionInformation.keyAccess[0].type == "wrapped"
    elif fmt == "nano":
        with open(ct_file, "rb") as f:
            envelope = nano.parse(f.read())
            assert envelope.header.version.version == 12
            assert envelope.header.binding_mode.use_ecdsa_binding == use_ecdsa
            if envelope.header.kas.kid is not None:
                # from xtest/platform/opentdf.yaml
                expected_kid = b"ec1" + b"\0" * 5
                assert envelope.header.kas.kid == expected_kid
    else:
        assert False, f"Unknown container type: {container}"
    cipherTexts[container_id] = ct_file
    return ct_file


#### BASIC ROUNDTRIP TESTS


def test_tdf_roundtrip(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    container: tdfs.container_type,
    in_focus: set[tdfs.sdk_type],
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if container == "nano-with-ecdsa":
        if not tdfs.supports(encrypt_sdk, "nano_ecdsa"):
            pytest.skip(
                f"{encrypt_sdk} sdk doesn't yet support ecdsa bindings for nanotdfs"
            )
    if container == "ztdf-ecwrap":
        if not tdfs.supports(encrypt_sdk, "ecwrap"):
            pytest.skip(f"{encrypt_sdk} sdk doesn't yet support ecwrap bindings")

    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        container,
        tmp_dir,
    )
    assert os.path.isfile(ct_file)
    fname = os.path.basename(ct_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)

    if container.startswith("ztdf") and tdfs.supports(decrypt_sdk, "ecwrap"):
        ert_file = f"{tmp_dir}test-{fname}-ecrewrap.untdf"
        tdfs.decrypt(decrypt_sdk, ct_file, ert_file, container, ecwrap=True)
        assert filecmp.cmp(pt_file, ert_file)


#### MANIFEST VALIDITY TESTS


def test_manifest_validity(
    encrypt_sdk: tdfs.sdk_type, pt_file: str, tmp_dir: str, in_focus: bool
):
    if not in_focus:
        pytest.skip("Not in focus")
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    tdfs.validate_manifest_schema(ct_file)


def test_manifest_validity_with_assertions(
    encrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    assertion_file_no_keys: str,
    in_focus: bool,
):
    if not in_focus:
        pytest.skip("Not in focus")
    if not tdfs.supports(encrypt_sdk, "assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=assertion_file_no_keys,
    )
    assert os.path.isfile(ct_file)
    tdfs.validate_manifest_schema(ct_file)


#### ASSERTION TESTS


def test_tdf_assertions_unkeyed(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.sdk_type],
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not tdfs.supports(encrypt_sdk, "assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not tdfs.supports(decrypt_sdk, "assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=assertion_file_no_keys,
    )
    assert os.path.isfile(ct_file)
    fname = os.path.basename(ct_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_tdf_assertions_with_keys(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.sdk_type],
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not tdfs.supports(encrypt_sdk, "assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not tdfs.supports(decrypt_sdk, "assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions-keys-roundtrip",
        az=assertion_file_rs_and_hs_keys,
    )
    assert os.path.isfile(ct_file)
    fname = os.path.basename(ct_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"

    tdfs.decrypt(
        decrypt_sdk,
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


### TAMPER TESTS

## POLICY TAMPER TESTS


def test_tdf_with_unbound_policy(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    in_focus: bool,
) -> None:
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("unbound_policy", ct_file, change_policy)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"wrap" in exc.output
        assert b"tamper" in exc.output or b"InvalidFileError" in exc.output


def test_tdf_with_altered_policy_binding(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    in_focus: bool,
) -> None:
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest(
        "altered_policy_binding", ct_file, change_policy_binding
    )
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"wrap" in exc.output
        assert b"tamper" in exc.output or b"InvalidFileError" in exc.output


## INTEGRITY TAMPER TESTS


def test_tdf_with_altered_root_sig(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    in_focus: bool,
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("broken_root_sig", ct_file, change_root_signature)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"root" in exc.output
        assert b"tamper" in exc.output or b"IntegrityError" in exc.output


def test_tdf_with_altered_seg_sig_wrong(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    in_focus: bool,
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("broken_seg_sig", ct_file, change_segment_hash)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"signature" in exc.output
        assert b"tamper" in exc.output or b"IntegrityError" in exc.output


## SEGMENT SIZE TAMPER TEST


def test_tdf_with_altered_enc_seg_size(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    in_focus: bool,
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest(
        "broken_enc_seg_sig", ct_file, change_encrypted_segment_size
    )
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert (
            b"tamper" in exc.output
            or b"IntegrityError" in exc.output
            or b"integrity check" in exc.output
        )


## ASSERTION TAMPER TESTS


def test_tdf_with_altered_assertion_statement(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    assertion_file_no_keys: str,
    in_focus: set[tdfs.sdk_type],
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not tdfs.supports(encrypt_sdk, "assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not tdfs.supports(decrypt_sdk, "assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=assertion_file_no_keys,
    )
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest(
        "altered_assertion_statement", ct_file, change_assertion_statement
    )
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"assertion" in exc.output
        assert b"tamper" in exc.output or b"IntegrityError" in exc.output


def test_tdf_with_altered_assertion_with_keys(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[tdfs.sdk_type],
):
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if not tdfs.supports(encrypt_sdk, "assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not tdfs.supports(decrypt_sdk, "assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions-keys-roundtrip",
        az=assertion_file_rs_and_hs_keys,
    )
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest(
        "altered_assertion_statement", ct_file, change_assertion_statement
    )
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(
            decrypt_sdk,
            b_file,
            rt_file,
            "ztdf",
            assertion_verification_file_rs_and_hs_keys,
            expect_error=True,
        )
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"assertion" in exc.output
        assert (
            b"tamper" in exc.output
            or b"IntegrityError" in exc.output
            or b"integrity check" in exc.output
        )


## PAYLOAD TAMPER TESTS


def test_tdf_altered_payload_end(
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    pt_file: str,
    tmp_dir: str,
    in_focus: bool,
) -> None:
    if not in_focus:
        pytest.skip("Not in focus")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_payload("altered_payload_end", ct_file, change_payload_end)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf", expect_error=True)
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"segment" in exc.output
        assert (
            b"tamper" in exc.output
            or b"InvalidFileError" in exc.output
            or b"integrity check" in exc.output
        )
