import filecmp
import logging
import subprocess

cipherTexts = {}
counter = 0
logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def encrypt(sdk, pt_file, ct_file, mime_type="application/octet-stream", nano=False):
    c = [
        sdk,
        "encrypt",
        pt_file,
        ct_file,
        "nano" if nano else "ztdf",
        "--mimeType",
        mime_type,
    ]
    subprocess.check_call(c)


def decrypt(sdk, ct_file, rt_file, nano=False):
    c = [
        sdk,
        "decrypt",
        ct_file,
        rt_file,
        "nano" if nano else "ztdf",
    ]
    subprocess.check_call(c)


def test_ztdf(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir):
    global counter
    counter = (counter or 0) + 1
    c = counter
    if encrypt_sdk not in cipherTexts:
        ct_file = f"{tmp_dir}test-{c}.ntdf"
        encrypt(encrypt_sdk, pt_file, ct_file, mime_type="text/plain", nano=True)
        cipherTexts[encrypt_sdk] = ct_file
    rt_file = f"{tmp_dir}test-{c}.untdf"
    decrypt(decrypt_sdk, cipherTexts[encrypt_sdk], rt_file, nano=True)
    assert filecmp.cmp(pt_file, rt_file)
