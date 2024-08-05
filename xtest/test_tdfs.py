import filecmp
import logging
import subprocess
import os

cipherTexts = {}
counter = 0
logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

sdk_paths = {
    "go": "sdk/go/cli.sh",
    "java": "sdk/java/cli.sh",
    "js": "sdk/js/cli/cli.sh",
    "py": "sdk/py/cli.sh",
}

def encrypt(sdk, pt_file, ct_file, mime_type="application/octet-stream", fmt="nano"):
    c = [
        sdk_paths[sdk],
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
        sdk_paths[sdk],
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
        ct_file = f"{tmp_dir}test-{encrypt_sdk}-{c}.{container}"
        encrypt(encrypt_sdk, pt_file, ct_file, mime_type="text/plain", fmt=container)
        cipherTexts[container_id] = ct_file
    ct_file = cipherTexts[container_id]
    assert os.path.isfile(ct_file)
    rt_file = f"{tmp_dir}test-{c}.untdf"
    decrypt(decrypt_sdk, ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)
