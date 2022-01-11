#!/usr/bin/env python3

# Evaluate several

import argparse
import filecmp
import json
import logging
import os
import random
import shutil
import string
import subprocess
import base64

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

tmp_dir = "tmp/"

KAS_ENDPOINT = os.getenv("KAS_ENDPOINT", "http://host.docker.internal:65432/kas")
OIDC_ENDPOINT = os.getenv("OIDC_ENDPOINT", "http://host.docker.internal:65432/keycloak")
ORGANIZATION_NAME = "tdf"
CLIENT_ID = "tdf-client"
CLIENT_SECRET = "123-456"

def encrypt_web(ct_file, rt_file, attributes=None):
    c = ["npx", "@opentdf/cli", "--kasEndpoint", KAS_ENDPOINT, 
    "--oidcEndpoint", OIDC_ENDPOINT,
    "--auth", f"{ORGANIZATION_NAME}:{CLIENT_ID}:{CLIENT_SECRET}",
    "--output", rt_file]
    if attributes:
      c += ["--attributes", ",".join(attributes)]
    c += ["encrypt", ct_file]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def decrypt_web(ct_file, rt_file):
    c = ["npx", "@opentdf/cli", "--kasEndpoint", KAS_ENDPOINT, 
    "--oidcEndpoint", OIDC_ENDPOINT,
    "--auth", f"{ORGANIZATION_NAME}:{CLIENT_ID}:{CLIENT_SECRET}",
    "--output", rt_file,
    "decrypt", ct_file]
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
        "--large", help="Use a 5 GiB File; doesn't work with nano sdks", action="store_true"
    )
    parser.add_argument("--no-teardown", action="store_true", help="don't delete temp files")
    args = parser.parse_args()

    sdks_to_encrypt = set([encrypt_web])
    sdks_to_decrypt = set([decrypt_web])

    logger.info("--- main")
    setup()

    pt_file = gen_pt(large=args.large)
    try:
        run_cli_tests(sdks_to_encrypt, sdks_to_decrypt, pt_file)
    finally:
        if not args.no_teardown:
            teardown()


def run_cli_tests(sdks_encrypt, sdks_decrypt, pt_file):
    logger.info("--- run_cli_tests %s => %s", sdks_encrypt, sdks_decrypt)
    fail = []

    serial = 0
    for x in sdks_encrypt:
        for y in sdks_decrypt:
            try:
                test_cross_roundtrip(x, y, serial, pt_file)
            except Exception as e:
                logger.error("Exception with pass %s => %s", x, y, exc_info=True)
                fail += [f"{x}=>{y}"]
            serial += 1
    if fail:
        raise Exception(f"TDF3 tests {fail} FAILED. See output for details.")
    else:
        logger.info("All tests succeeded!")


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
    length = (5 * 2**30) if large else 128
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
