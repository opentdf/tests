#!/usr/bin/env python3

import argparse
import filecmp
import json
import logging
import os
import random
import re
import requests
import shutil
import string
import subprocess
import base64

SDK_PATHS = ["sdk/js/node/cli.sh"]

all_sdks = set(SDK_PATHS)

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

tmp_dir = "tmp/"

isExist = os.path.exists(tmp_dir)

if not isExist:
  os.makedirs(tmp_dir)
  print("The fresh tmp directory is created!")


def main():
    parser = argparse.ArgumentParser(description="Cross-test various TDF libraries.")
    parser.add_argument("-S", "--sdks", nargs="+", choices=SDK_PATHS, help="SDK variant")
    parser.add_argument("-E", "--sdks-encrypt", nargs="+", choices=SDK_PATHS, help="SDK variant to use to encrypt")
    parser.add_argument("-D", "--sdks-decrypt", nargs="+", choices=SDK_PATHS, help="SDK variant to use to decrypt")
    parser.add_argument(
        "--large", help="Use a 5 GiB File; doesn't work with nano sdks", action="store_true"
    )
    args = parser.parse_args()

    sdks = set(args.sdks) if args.sdks else all_sdks
    sdks_to_encrypt = set(args.sdks_encrypt) if args.sdks_encrypt else sdks
    sdks_to_decrypt = set(args.sdks_decrypt) if args.sdks_decrypt else sdks

    logger.info("--- main")

    pt_file = gen_pt(large=args.large)
    if sdks_to_decrypt or sdks_to_encrypt:
        run_cli_tests(sdks_to_encrypt, sdks_to_decrypt, pt_file, attrtest)


def run_cli_tests(sdks_encrypt, sdks_decrypt, pt_file, attrtest):
    if not sdks_encrypt or not sdks_decrypt:
        return
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
    ct_file, rt_file, mf_file = gen_files(serial)
    logger.info(
        "--- Gen Files %s, %s, %s",
        ct_file,
        rt_file,
        mf_file
    )

    # Do the roundtrip.
    logger.info("Encrypt %s", encrypt_sdk)
    encrypt(encrypt_sdk, pt_file, ct_file, mime_type="text/plain")
    logger.info("Decrypt %s", decrypt_sdk)
    decrypt(decrypt_sdk, ct_file, rt_file)

    # Verify the roundtripped result is the same as our initial plantext.
    if not filecmp.cmp(pt_file, rt_file):
        raise Exception(
            "Test #%s: FAILED due to rt mismatch\n\texpected: %s\n\tactual: %s)"
            % (serial, pt_file, rt_file)
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
    ct = "%stest-%s.tdf" % (tmp_dir, serial)  # ciphertext (TDF)
    rt = "%stest-%s.untdf" % (tmp_dir, serial)  # roundtrip (plaintext)
    mf = "%stest-%s.manifest" % (tmp_dir, serial)  # roundtrip (manifest json)

    # Create files with "open" func
    ct_file = open(ct, "w+")
    rt_file = open(rt, "w+")
    mf_file = open(mf, "w+")

    # Close files after they are created
    ct_file.close()
    rt_file.close()
    mf_file.close()

    return ct, rt, mf


def encrypt(sdk, pt_file, ct_file, mime_type="application/octet-stream"):
    c = [sdk, "encrypt", pt_file, ct_file, "--mimeType", mime_type]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def decrypt(sdk, ct_file, rt_file):
    c = [sdk, "decrypt", ct_file, rt_file]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def manifest(sdk, ct_file, rt_file):
    c = [sdk, "manifest", ct_file, rt_file]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)
    with open(rt_file) as json_file:
        return json.load(json_file)


if __name__ == "__main__":
    main()
