import filecmp
import os

import pytest

import nano
import tdfs


cipherTexts = {}
counter = 0


def test_tdf(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, container):
    global counter
    counter = (counter or 0) + 1
    c = counter
    use_ecdsa = False
    if container == "nano-with-ecdsa":
        if not tdfs.supports(encrypt_sdk, "nano_ecdsa"):
            pytest.skip(
                f"{encrypt_sdk} sdk doesn't yet support ecdsa bindings for nanotdfs"
            )
        container = "nano"
        use_ecdsa = True
    container_id = f"{encrypt_sdk}-{container}"
    if container_id not in cipherTexts:
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
    ct_file = cipherTexts[container_id]
    assert os.path.isfile(ct_file)
    rt_file = f"{tmp_dir}test-{c}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)
