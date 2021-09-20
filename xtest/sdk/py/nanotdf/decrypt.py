import json
import logging
import os
import sys

from tdf3sdk import NanoTDFClient, LogLevel

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
    logger.info(
        "Source: %s, Target: %s, owner: %s, eas: %s", source, target, owner, eas
    )
    nanotdf_client = NanoTDFClient(eas_url=eas, user=owner)
    nanotdf_client.enable_console_logging(LogLevel.Info)
    nanotdf_client.decrypt_file(source, target)


if __name__ == "__main__":
    main()
