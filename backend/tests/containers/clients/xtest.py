#!/usr/bin/env python3

# Evaluate several

import argparse
import filecmp
import logging
import os
import random
import shutil
import string
import subprocess

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

tmp_dir = "tmp/"

SDK_PATHS = {"py_encrypt": "py/encrypt.py", "py_decrypt": "py/decrypt.py"}

KAS_ENDPOINT = os.getenv("KAS_ENDPOINT", "http://host.docker.internal:65432/kas")
OIDC_ENDPOINT = os.getenv("OIDC_ENDPOINT", "http://host.docker.internal:65432/keycloak")
ORGANIZATION_NAME = "tdf"
CLIENT_ID = "tdf-client"
CLIENT_SECRET = "123-456"


def encrypt_web(ct_file, rt_file, attributes=None):
    c = [
        "npx",
        "@opentdf/cli",
        "--log-level",
        "DEBUG",
        "--kasEndpoint",
        KAS_ENDPOINT,
        "--oidcEndpoint",
        OIDC_ENDPOINT,
        "--auth",
        f"{ORGANIZATION_NAME}:{CLIENT_ID}:{CLIENT_SECRET}",
        "--output",
        rt_file,
    ]
    if attributes:
        c += ["--attributes", ",".join(attributes)]
    c += ["encrypt", ct_file]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def decrypt_web(ct_file, rt_file):
    c = [
        "npx",
        "@opentdf/cli",
        "--log-level",
        "DEBUG",
        "--kasEndpoint",
        KAS_ENDPOINT,
        "--oidcEndpoint",
        OIDC_ENDPOINT,
        "--auth",
        f"{ORGANIZATION_NAME}:{CLIENT_ID}:{CLIENT_SECRET}",
        "--output",
        rt_file,
        "decrypt",
        ct_file,
    ]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def encrypt_py_nano(ct_file, rt_file, attributes=None):
    encrypt_py(ct_file, rt_file, attributes=attributes, nano=True)


def decrypt_py_nano(ct_file, rt_file):
    decrypt_py(ct_file, rt_file, nano=True)


def encrypt_py(pt_file, ct_file, nano=False, attributes=None):
    c = [
        "python3",
        SDK_PATHS["py_encrypt"],
        "--kasEndpoint",
        KAS_ENDPOINT,
        "--oidcEndpoint",
        OIDC_ENDPOINT,
        "--auth",
        f"{ORGANIZATION_NAME}:{CLIENT_ID}:{CLIENT_SECRET}",
        "--ctfile",
        ct_file,
        "--ptfile",
        pt_file,
    ]
    if attributes:
        c += ["--attributes", ",".join(attributes)]
    if nano:
        c.append("--nano")
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def decrypt_py(ct_file, rt_file, nano=False):
    c = [
        "python3",
        SDK_PATHS["py_decrypt"],
        "--kasEndpoint",
        KAS_ENDPOINT,
        "--oidcEndpoint",
        OIDC_ENDPOINT,
        "--auth",
        f"{ORGANIZATION_NAME}:{CLIENT_ID}:{CLIENT_SECRET}",
        "--rtfile",
        rt_file,
        "--ctfile",
        ct_file,
    ]
    if nano:
        c.append("--nano")
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def setup():
    teardown()
    os.makedirs(tmp_dir)


def teardown():
    dirs = [tmp_dir]
    for thedir in dirs:
        if os.path.isdir(thedir):
            shutil.rmtree(thedir)


def main():
    parser = argparse.ArgumentParser(description="Cross-test various TDF libraries.")
    parser.add_argument(
        "--large",
        help="Use a 5 GiB File; doesn't work with nano sdks",
        action="store_true",
    )
    parser.add_argument(
        "--no-teardown", action="store_true", help="don't delete temp files"
    )
    args = parser.parse_args()

    tdf3_sdks_to_encrypt = set([encrypt_py])
    tdf3_sdks_to_decrypt = set([decrypt_py])

    nano_sdks_to_encrypt = set([encrypt_web, encrypt_py_nano])
    nano_sdks_to_decrypt = set([decrypt_web, decrypt_py_nano])

    logger.info("--- main")
    setup()

    pt_file = gen_pt(large=args.large)
    nano_pt_file = pt_file if not args.large else gen_pt(large=False)
    failed = []
    try:
        logger.info("TDF3 TESTS:")
        failed += run_cli_tests(tdf3_sdks_to_encrypt, tdf3_sdks_to_decrypt, pt_file)
        logger.info("NANO TESTS:")
        failed += run_cli_tests(
            nano_sdks_to_encrypt, nano_sdks_to_decrypt, nano_pt_file
        )
    finally:
        if not args.no_teardown:
            teardown()
    if failed:
        raise Exception(f"tests {failed} FAILED. See output for details.")


def run_cli_tests(sdks_encrypt, sdks_decrypt, pt_file):
    logger.info("--- run_cli_tests %s => %s", sdks_encrypt, sdks_decrypt)
    failed = []

    serial = 0
    for x in sdks_encrypt:
        for y in sdks_decrypt:
            try:
                test_cross_roundtrip(x, y, serial, pt_file)
            except Exception as e:
                logger.error("Exception with pass %s => %s", x, y, exc_info=True)
                failed += [f"{x}=>{y}"]
            serial += 1
    return failed


# Test a roundtrip across the two referenced sdks.
# Returns True if test succeeded, false otherwise.
def test_cross_roundtrip(encrypt_sdk, decrypt_sdk, serial, pt_file):
    logger.info(
        "--- Begin Test #%s: Roundtrip encrypt(%s) --> decrypt(%s)",
        serial,
        encrypt_sdk,
        decrypt_sdk,
    )

    # Generate plaintext and files
    ct_file, rt_file = gen_files(serial)

    # Do the roundtrip.
    logger.info("Encrypt %s", encrypt_sdk)
    encrypt_sdk(pt_file, ct_file)
    logger.info("Decrypt %s", decrypt_sdk)
    decrypt_sdk(ct_file, rt_file)

    # Verify the roundtripped result is the same as our initial plantext.
    if not filecmp.cmp(pt_file, rt_file):
        raise Exception(
            "Test #%s: FAILED due to rt mismatch\n\texpected: %s\n\tactual: %s)"
            % (serial, pt, rt)
        )
    logger.info("Test #%s, (%s->%s): Succeeded!", serial, encrypt_sdk, decrypt_sdk)


def gen_pt(*, large):
    pt_file = "%stest-plain-%s.txt" % (tmp_dir, "large" if large else "small")
    length = (5 * 2 ** 30) if large else 128
    with open(pt_file, "w") as f:
        for i in range(0, length, 16):
            f.write("{:15,d}\n".format(i))
    return pt_file


def gen_files(serial):
    ct_file = "%stest-%s.tdf" % (tmp_dir, serial)  # ciphertext (TDF)
    rt_file = "%stest-%s.untdf" % (tmp_dir, serial)  # roundtrip (plaintext)

    return ct_file, rt_file


def random_string():
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(128)
    )


if __name__ == "__main__":
    main()
