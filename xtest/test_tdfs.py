import filecmp
import logging
import subprocess

cipherTexts = {}
counter = 0
logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def encrypt(sdk, pt_file, ct_file, mime_type="application/octet-stream", fmt="nano"):
    c = [
        sdk,
        "encrypt",
        pt_file,
        ct_file,
        fmt,
        "--mimeType",
        mime_type,
    ]
    subprocess.check_call(c)


def decrypt(sdk, ct_file, rt_file, fmt="nano"):
    c = [
        sdk,
        "decrypt",
        ct_file,
        rt_file,
        fmt,
    ]
    subprocess.check_call(c)


def test_ztdf(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, container):
    global counter
    counter = (counter or 0) + 1
    c = counter
    container_id = f"{encrypt_sdk}-{container}"
    if container_id not in cipherTexts:
        ct_file = f"{tmp_dir}test-{c}.{container}"
        encrypt(encrypt_sdk, pt_file, ct_file, mime_type="text/plain", fmt=container)
        cipherTexts[container_id] = ct_file
    rt_file = f"{tmp_dir}test-{c}.untdf"
    decrypt(decrypt_sdk, cipherTexts[container_id], rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)
