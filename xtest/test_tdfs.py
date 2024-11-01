import assertions
import filecmp
import os
import subprocess
import base64
import string
import random

import pytest

import nano
import tdfs


cipherTexts = {}
counter = 0


def doEncryptWith(
    pt_file: str,
    encrypt_sdk: str,
    container: str,
    tmp_dir: str,
    use_ecdsa: bool = False,
    az: list[assertions.Assertion] = [],
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
    tdfs.encrypt(
        encrypt_sdk,
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt=container,
        use_ecdsa_binding=use_ecdsa,
        assert_value=az,
    )
    if container == "ztdf":
        manifest = tdfs.manifest(ct_file)
        assert manifest.payload.isEncrypted
    elif container == "nano":
        with open(ct_file, "rb") as f:
            envelope = nano.parse(f.read())
            assert envelope.header.version.version == 12
            assert envelope.header.binding_mode.use_ecdsa_binding == use_ecdsa
            if envelope.header.kas.kid is not None:
                # from xtest/platform/opentdf.yaml
                expected_kid = b"ec1" + b"\0" * 5
                assert envelope.header.kas.kid == expected_kid
    cipherTexts[container_id] = ct_file
    return ct_file


def test_tdf(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, container):
    use_ecdsa = False
    if container == "nano-with-ecdsa":
        if not tdfs.supports(encrypt_sdk, "nano_ecdsa"):
            pytest.skip(
                f"{encrypt_sdk} sdk doesn't yet support ecdsa bindings for nanotdfs"
            )
        container = "nano"
        use_ecdsa = True
    ct_file = doEncryptWith(pt_file, encrypt_sdk, container, tmp_dir, use_ecdsa)
    assert os.path.isfile(ct_file)
    fname = os.path.basename(ct_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)


def breakBinding(manifest: tdfs.Manifest) -> tdfs.Manifest:
    #  base64 decode policy from manifest.encryptionInformation.policy
    p = manifest.encryptionInformation.policy_object
    p.body.dataAttributes = []
    p.body.dissem = ["yves@dropp.er"]
    manifest.encryptionInformation.policy_object = p
    return manifest


def changeLastThree(byt: bytes) -> bytes:
    new_three = "".join(random.choices(string.ascii_lowercase + string.digits, k=3))
    if new_three == byt[-3:]:
        # catch the case where the random string is the same (v unlikely)
        return changeLastThree(byt)
    return byt[:-3] + new_three.encode()


def breakRootSignature(manifest: tdfs.Manifest) -> tdfs.Manifest:
    rootSig = manifest.encryptionInformation.integrityInformation.rootSignature.sig
    alteredSig = base64.b64encode(changeLastThree(base64.b64decode(rootSig)))
    manifest.encryptionInformation.integrityInformation.rootSignature.sig = alteredSig
    return manifest


def breakSegmentSignature(manifest: tdfs.Manifest) -> tdfs.Manifest:
    segments = manifest.encryptionInformation.integrityInformation.segments
    # choose a random segment
    index = random.randrange(len(segments))
    segment = segments[index]
    alteredHash = base64.b64encode(changeLastThree(base64.b64decode(segment.hash)))
    segment.hash = alteredHash
    manifest.encryptionInformation.integrityInformation.segments[index] = segment
    return manifest


def test_tdf_with_unbound_policy(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir):
    ct_file = doEncryptWith(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("unbound_policy", ct_file, breakBinding)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf")
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"wrap" in exc.output
        # assert b"tamper" in exc.output


def test_tdf_with_altered_root_sig(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir):
    ct_file = doEncryptWith(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("broken_root_sig", ct_file, breakRootSignature)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf")
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"root" in exc.output
        assert (b"tamper" in exc.output or b"IntegrityError" in exc.output)


def test_tdf_with_altered_seg_sig(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir):
    ct_file = doEncryptWith(pt_file, encrypt_sdk, "ztdf", tmp_dir)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("broken_seg_sig", ct_file, breakSegmentSignature)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf")
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"signature" in exc.output
        assert (b"tamper" in exc.output or b"IntegrityError" in exc.output)


def test_tdf_assertions(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir):
    if not tdfs.supports(encrypt_sdk, "assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not tdfs.supports(decrypt_sdk, "assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = doEncryptWith(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_dir,
        scenario="assertions",
        az=[
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
            ),
        ],
    )
    assert os.path.isfile(ct_file)
    fname = os.path.basename(ct_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
