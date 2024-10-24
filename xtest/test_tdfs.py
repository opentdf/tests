import filecmp
import os
import subprocess

import pytest

import nano
import tdfs


cipherTexts = {}
counter = 0


def doEncryptWith(
    pt_file: str, encrypt_sdk: str, container: str, tmp_dir: str, use_ecdsa: bool
) -> str:
    global counter
    counter = (counter or 0) + 1
    c = counter
    container_id = f"{encrypt_sdk}-{container}"
    if container_id in cipherTexts:
        return cipherTexts[container_id]
    ct_file = f"{tmp_dir}test-{encrypt_sdk}-{c}.{container}"
    tdfs.encrypt(
        encrypt_sdk,
        pt_file,
        ct_file,
        mime_type="text/plain",
        fmt=container,
        use_ecdsa_binding=use_ecdsa,
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


def test_tdf_with_unbound_policy(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir):
    ct_file = doEncryptWith(pt_file, encrypt_sdk, "ztdf", tmp_dir, False)
    assert os.path.isfile(ct_file)
    b_file = tdfs.update_manifest("unbound_policy", ct_file, breakBinding)
    fname = os.path.basename(b_file).split(".")[0]
    rt_file = f"{tmp_dir}test-{fname}.untdf"
    try:
        tdfs.decrypt(decrypt_sdk, b_file, rt_file, "ztdf")
        assert False, "decrypt succeeded unexpectedly"
    except subprocess.CalledProcessError as exc:
        assert b"wrap" in exc.output
