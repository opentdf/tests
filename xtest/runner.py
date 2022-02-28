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

SDK_PATHS = [
    "sdk/js/node/cli.sh",
    "sdk/js/web/cli.sh",
    # "sdk/py/oss/cli.sh",
    # "sdk/py/nanotdf/cli.sh",
    # "sdk/java/oss/cli.sh",
]
all_sdks = set(SDK_PATHS)

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

tmp_dir = "tmp/"


def main():
    parser = argparse.ArgumentParser(description="Cross-test various TDF libraries.")
    # parser.add_argument("-o", "--owner", help="User ID for resource owner", required=True)
    parser.add_argument("-S", "--sdks", nargs="+", choices=SDK_PATHS, help="SDK variant")
    parser.add_argument("-E", "--sdks-encrypt", nargs="+", choices=SDK_PATHS, help="SDK variant to use to encrypt")
    parser.add_argument("-D", "--sdks-decrypt", nargs="+", choices=SDK_PATHS, help="SDK variant to use to decrypt")
    parser.add_argument("--no-teardown", action="store_true", help="don't delete temp files")
    parser.add_argument(
        "-s",
        "--stage",
        help="vpc stage, as found in the appropriat config JSON file",
        required=True,
    )
    parser.add_argument(
        "--crud", help="Update and delete users and attributes", action="store_true"
    )
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
    # owner = args.owner
    stage = args.stage
    crud = args.crud
    attrtest = args.attrtest

    logger.info("--- main")
    # setup(crud, stage, owner)
    # if crud:
    #     logger.info("--- main - crud")
    #     with open("config-oss.json") as config_file:
    #         config = json.load(config_file)
    #     create_users_and_attributes(
    #         attributeEndpoint=config[stage]["attributeEndpoint"],
    #         owner=owner,
    #         userEndpoint=config[stage]["userEndpoint"],
    #     )

    pt_file = gen_pt(large=args.large)
    try:
        # TODO(PLAT-533) Support xtest browser and non browser
        if sdks_to_decrypt or sdks_to_encrypt:
            run_cli_tests(sdks_to_encrypt, sdks_to_decrypt, stage, pt_file, attrtest)
            # run_cli_tests(sdks_to_encrypt, sdks_to_decrypt, owner, stage, pt_file, attrtest)
    finally:
        if not args.no_teardown:
            teardown(crud, stage)


# def run_cli_tests(sdks_encrypt, sdks_decrypt, owner, stage, pt_file, attrtest):
def run_cli_tests(sdks_encrypt, sdks_decrypt, stage, pt_file, attrtest):
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
                    test_cross_roundtrip_with_attributes(
                        x, y, owner, stage, serial, pt_file
                    )
                else:
                  # test_cross_roundtrip(x, y, owner, stage, serial, pt_file)
                    test_cross_roundtrip(x, y, stage, serial, pt_file)
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
# def test_cross_roundtrip(encrypt_sdk, decrypt_sdk, owner, stage, serial, pt_file):
def test_cross_roundtrip(encrypt_sdk, decrypt_sdk, stage, serial, pt_file):
    logger.info(
        "--- Begin Test #%s: Roundtrip encrypt(%s) --> decrypt(%s)",
        serial,
        encrypt_sdk,
        decrypt_sdk,
    )

    # Generate plaintext and files
    ct_file, rt_file, mf_file = gen_files(serial)

    # Do the roundtrip.
    logger.info("Encrypt %s", encrypt_sdk)
    encrypt(encrypt_sdk, stage, pt_file, ct_file, mime_type="text/plain")
    logger.info("Decrypt %s", decrypt_sdk)
    decrypt(decrypt_sdk, stage, ct_file, rt_file)
    # TODO(PLAT-532) Support manifest in OSS
    # m = manifest(decrypt_sdk, owner, stage, ct_file, mf_file)

    # Verify the roundtripped result is the same as our initial plantext.
    if not filecmp.cmp(pt_file, rt_file):
        raise Exception(
            "Test #%s: FAILED due to rt mismatch\n\texpected: %s\n\tactual: %s)"
            % (serial, pt, rt)
        )
    # TODO(PLAT-532) Support manifest in OSS
    # if m:
    #     assert m["payload"]["mimeType"] == "text/plain"
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
        ct_file, rt_file, mf_file = gen_files(
            serial, attr_type=attr_type
        )

        # Do the roundtrip.
        encrypt(
            encrypt_sdk, owner, stage, pt_file, ct_file, mime_type="text/plain", attributes=attr_type
        )

        try:
            decrypt(decrypt_sdk, owner, stage, ct_file, rt_file)
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


def gen_files(serial, attr_type=""):
    ct_file = "%stest-%s.tdf" % (tmp_dir, serial)  # ciphertext (TDF)
    rt_file = "%stest-%s.untdf" % (tmp_dir, serial)  # roundtrip (plaintext)
    mf_file = "%stest-%s.manifest" % (tmp_dir, serial)  # roundtrip (manifest json)

    return ct_file, rt_file, mf_file


def random_string():
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(128)
    )


def encrypt(sdk, stage, pt_file, ct_file, mime_type="application/octet-stream", attributes=""):
    if attributes:
        c = [
            sdk,
            stage,
            "encrypt",
            pt_file,
            ct_file,
            "--mimeType",
            mime_type,
            "--attrs",
            attributes,
        ]
    else:
        c = [sdk, stage, "encrypt", pt_file, ct_file, "--mimeType", mime_type]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def decrypt(sdk, stage, ct_file, rt_file):
    c = [sdk, stage, "decrypt", ct_file, rt_file]
    logger.info("Invoking subprocess: %s", " ".join(c))
    subprocess.check_call(c)


def manifest(sdk, owner, stage, ct_file, rt_file):
    c = [sdk, owner, stage, "manifest", ct_file, rt_file]
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
    # b = {
    #     "name": "Bob",
    #     "userId": "bob_test_5678",
    #     "email": "bobTest@example.com",
    #     "attributes": [
    #         attributes['frenchTest']['attribute'],
    #         attributes['germanTest']['attribute'],
    #         attributes['italianTest']['attribute'],
    #     ]
    # }
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


def delete_users_and_attributes(*, attributeEndpoint, userEndpoint, owner):
    # there is no DELETE for attributes in openAPI
    pass


def setup(crud, stage):
    teardown(crud, stage)
    os.makedirs(tmp_dir)


def teardown(crud, stage):
    dirs = [tmp_dir]

    # for thedir in dirs:
    #     if os.path.isdir(thedir):
    #         shutil.rmtree(thedir)
    # if crud:
    #     with open("config-oss.json") as config_file:
    #         config = json.load(config_file)
    #     # delete_users_and_attributes(
    #     #     attributeEndpoint=config[stage]["attributeEndpoint"],
    #     #     owner=owner,
    #     #     userEndpoint=config[stage]["userEndpoint"],
    #     # )
    # jar_files = [f for f in os.listdir("sdk/java") if f.endswith(".jar")]
    # for f in jar_files:
    #     os.remove(os.path.join("sdk/java", f))


if __name__ == "__main__":
    main()