#!/usr/bin/env python3

# Evaluate several

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
  # Create a new directory because it does not exist
  os.makedirs(tmp_dir)
  print("The new directory is created!")


def main():
    parser = argparse.ArgumentParser(description="Cross-test various TDF libraries.")
    parser.add_argument("-S", "--sdks", nargs="+", choices=SDK_PATHS, help="SDK variant")
    parser.add_argument("-E", "--sdks-encrypt", nargs="+", choices=SDK_PATHS, help="SDK variant to use to encrypt")
    parser.add_argument("-D", "--sdks-decrypt", nargs="+", choices=SDK_PATHS, help="SDK variant to use to decrypt")
    parser.add_argument("--no-teardown", action="store_true", help="don't delete temp files")
    parser.add_argument(
        "--attrtest", help="Testing with attributes - requires crud", action="store_true"
    )
    parser.add_argument(
        "--large", help="Use a 5 GiB File; doesn't work with nano sdks", action="store_true"
    )
    args = parser.parse_args()

    sdks = set(args.sdks) if args.sdks else all_sdks
    sdks_to_encrypt = set(args.sdks_encrypt) if args.sdks_encrypt else sdks
    sdks_to_decrypt = set(args.sdks_decrypt) if args.sdks_decrypt else sdks
    attrtest = args.attrtest

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
                # TODO: Parallelize when these start taking a lot of time.
                if attrtest:
                    test_cross_roundtrip_with_attributes(x, y, serial, pt_file)
                else:
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


# Test a roundtrip across the two referenced sdks with attributes.
# Returns True if test succeeded, false otherwise.
def test_cross_roundtrip_with_attributes(encrypt_sdk, decrypt_sdk, serial, pt_file):
    logger.info(
        "Test #%s: Roundtrip encrypt(%s) --> decrypt(%s) with attributes",
        serial,
        encrypt_sdk,
        decrypt_sdk,
    )

    iterations = {
        "No Attributes": [],
        "Success Attributes": [
            "http://example.com/attr/language/value/urdu1",
            "http://example.com/attr/language/value/french1",
        ],
        "Failing Attributes": [
            "http://example.com/attr/language/value/urdu1",
            "http://example.com/attr/language/value/german1",
        ],
    }

    for attr_type, attrs in iterations.items():
        # Generate the string and files
        ct_file, rt_file, mf_file = gen_files(serial, attr_type=attr_type)

        # Do the roundtrip.
        encrypt(encrypt_sdk, pt_file, ct_file, mime_type="text/plain", attributes=attr_type)

        try:
            decrypt(decrypt_sdk, ct_file, rt_file)
            if attr_type == "Failing Attributes":
                raise Exception(
                    "Test #%s with %s: FAILED -- Decryption successful when expected to fail"
                    % (serial, attr_type)
                )
            # TODO(PLAT-532) Support manifest in OSS
            m = (
                manifest(decrypt_sdk, ct_file, mf_file)
                if "osssdk/py/oss/cli.sh" != decrypt_sdk
                else {}
            )

            # Verify the roundtripped result is the same as our initial plantext.
            if not filecmp.cmp(pt_file, rt_file):
                raise Exception(
                    "Test #%s (%s->%s) with %s: FAILED due to rt mismatch\n\texpected: %s\n\tactual: %s)",
                    serial,
                    encrypt_sdk,
                    decrypt_sdk,
                    attr_type,
                    pt,
                    rt,
                )

            # py-oss does not have ability to add mimetype?
            if m and "sdk/py/oss/cli.sh" != encrypt_sdk:
                assert m["payload"]["mimeType"] == "text/plain"

            # verify data attributes are in the manifest
            if m:
                policy_decoded = base64.b64decode(
                    m["encryptionInformation"]["policy"].encode("ascii")
                ).decode("ascii")
                policy = json.loads(policy_decoded)
                attribute_objects = policy["body"]["dataAttributes"]
                decrypt_attrs = []
                for attribute_obj in attribute_objects:
                    decrypt_attrs += [attribute_obj["attribute"]]
                assert set(attrs).issubset(
                    decrypt_attrs
                ), "Manifest must include data attributes added on encrypt"

            logger.info(
                "Test #%s, (%s->%s) with %s: Succeeded!",
                serial,
                encrypt_sdk,
                decrypt_sdk,
                attr_type,
            )

        except Exception as e:
            if attr_type != "Failing Attributes":
                raise Exception(
                    "Test #%s, (%s->%s) with %s: FAILED -- Decryption unsuccessful",
                    serial,
                    encrypt_sdk,
                    decrypt_sdk,
                    attr_type,
                ) from e
            else:
                logger.info(
                    "Test #%s, (%s->%s) with %s: Succeeded!",
                    serial,
                    encrypt_sdk,
                    decrypt_sdk,
                    attr_type,
                )


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


def random_string():
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(128)
    )


def encrypt(sdk, pt_file, ct_file, mime_type="application/octet-stream", attributes=""):
    if attributes:
        c = [
            sdk,
            "encrypt",
            pt_file,
            ct_file,
            "--mimeType",
            mime_type,
            "--attrs",
            attributes,
        ]
    else:
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


def create_users_and_attributes(*, attributeEndpoint, userEndpoint, owner):
    langs = [
        "frenchTest",
        "germanTest",
        "italianTest",
        "japaneseTest",
        "urduTest",
    ]
    attribute_uris = ["http://example.com/attr/language/value/" + l for l in langs]

    ca_file = os.environ.get("TDF3_CERT_AUTHORITY", "")
    if not ca_file:
        auth = {"verify": False}
    else:
        cn = re.sub(r".*CN=([^,]+).*", r"\1", owner)
        cert_path = os.environ.get("CERT_CLIENT_BASE", cn or "client")
        auth = {"verify": ca_file, "cert": (cert_path + ".crt", cert_path + ".key")}
        logger.info("runner auth: %s", auth)

    attribute_response = requests.post(
        attributeEndpoint,
        json=attribute_uris,
        **auth,
    )
    if attribute_response.status_code >= 300:
        raise Exception(
            "Unexpected error {}\n\t{}".format(
                attribute_response.status_code, attribute_response.content
            )
        )
    canonicalized_attributes = attribute_response.json()
    logger.debug("canonicalized_attributes: %s", canonicalized_attributes)
    attributes = dict(zip(langs, canonicalized_attributes))
    u = {
        "userId": owner,
        "name": "Alice",
        "email": "Alice_test@example.com",
        "attributes": [
            attributes["frenchTest"]["attribute"],
            attributes["japaneseTest"]["attribute"],
            attributes["urduTest"]["attribute"],
        ],
    }
    user_response = requests.post(
        userEndpoint,
        json=u,
        **auth,
    )
    if user_response.status_code != 201:
        raise Exception(
            "Unexpected error {}\n\t{}".format(
                user_response.status_code, user_response.content
            )
        )


if __name__ == "__main__":
    main()