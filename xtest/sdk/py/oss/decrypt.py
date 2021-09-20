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

    with open("config-oss.json") as config_file:
        config = json.load(config_file)

    tier = config[stage]
    eas = tier.get("entityObjectEndpoint", None) or tier.get("easEndpoint", None)
    for s in ["/v1/entity_object", "/api/entityobject"]:
        if eas.endswith(s):
            eas = eas[: -len(s)]
            break
    decrypt_file(source, target, owner, eas)


def decrypt_file(source, target, owner, eas):
    ca = os.environ.get("TDF3_CERT_AUTHORITY", "")
    if ca:
        client_path = os.environ.get("CERT_CLIENT_BASE", "/xtest/client")
        logger.info(
            "Source: {}, Target: {}, owner: {}, eas: {}, ca: {}, client_path: {}".format(
                source, target, owner, eas, ca, client_path
            )
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
    client.decrypt_file(source, target)


if __name__ == "__main__":
    main()
