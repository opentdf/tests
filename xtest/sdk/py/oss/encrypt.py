import json
import logging
import os
import sys

from tdf3sdk import TDF3Client, LogLevel

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def main():
    stage, source, target, owner = sys.argv[1:5]
    attributes = sys.argv[8] if sys.argv[7] == "--attrs" else ""

    with open("config-oss.json") as config_file:
        config = json.load(config_file)

    tier = config[stage]
    eas = tier.get("entityObjectEndpoint", None) or tier.get("easEndpoint", None)
    for s in ["/v1/entity_object", "/api/entityobject"]:
        if eas.endswith(s):
            eas = eas[: -len(s)]
            break
    if attributes:
        # based on alice_1234 - assuming she is owner
        iterations = {
            "No Attributes": [],
            "Success Attributes": [
                "http://example.com/attr/language/value/urduTest",
                "http://example.com/attr/language/value/frenchTest",
            ],
            "Failing Attributes": [
                "http://example.com/attr/language/value/urduTest",
                "http://example.com/attr/language/value/germanTest",
            ],
        }
        encrypt_attrs = iterations[attributes]
    else:
        encrypt_attrs = []

    encrypt_file(source, target, owner, eas, encrypt_attrs)


def encrypt_file(source, target, owner, eas, attrs):
    ca = os.environ.get("TDF3_CERT_AUTHORITY", "")
    if ca:
        client_path = os.environ.get("CERT_CLIENT_BASE", "/xtest/client")
        logger.info(
            "Source: %s, Target: %s, owner: %s, eas: %s, ca: %s, client_path: %s",
            source,
            target,
            owner,
            eas,
            ca,
            client_path,
        )
        client = TDF3Client(
            backend_url=eas,
            user=owner,
            client_key_filename=client_path + ".key",
            client_cert_filename=client_path + ".crt",
            sdk_consumer_certauthority=ca,
            use_oidc=False,
        )
    else:
        logger.info(
            "Source: %s, Target: %s, owner: %s, eas: %s", source, target, owner, eas
        )
        client = TDF3Client(eas_url=eas, user=owner)

    client.enable_console_logging(LogLevel.Info)
    logger.info("Encrypting with data attributes: %s", attrs)
    client.with_data_attributes(attrs)
    client.encrypt_file(source, target)


if __name__ == "__main__":
    main()
