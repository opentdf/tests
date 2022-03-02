import argparse
import json
import logging
import os
import sys

from opentdf import TDFClient, NanoTDFClient, OIDCCredentials, LogLevel

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def encrypt_file(
    client,
    oidc_endpoint,
    kas,
    client_id,
    client_secret,
    org_name,
    nano,
    pt_file,
    ct_file,
    attributes,
):
    logger.info(
        "KAS: %s, OIDC: %s, Client id: %s, Client secret: %s, Org Name: %s, Nano: %s",
        oidc_endpoint,
        kas,
        client_id,
        client_secret,
        org_name,
        str(nano),
    )
    client.enable_console_logging(LogLevel.Info)

    for attribute in attributes:
        client.add_data_attribute(attribute)

    client.encrypt_file(pt_file, ct_file)
    logger.info("Encrypting with data attributes: %s", attributes)
    logger.info("Encrypting file ")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--kasEndpoint", help="KAS endpoint")
    parser.add_argument("--oidcEndpoint", help="OIDC endpoint")
    parser.add_argument("--auth", help="ORGANIZATION_NAME:CLIENT_ID:CLIENT_SECRET")
    parser.add_argument("--ctfile", help="output file name")
    parser.add_argument("--ptfile", help="input file name")
    parser.add_argument("--attributes", help="data attributes to encrypt with")
    parser.add_argument("--nano", help="use nano tdf", action="store_true")

    args = parser.parse_args()
    auth = args.auth.split(":")

    attributes = args.attributes.split(",") if args.attributes else []

    oidc_creds = OIDCCredentials()
    oidc_creds.set_client_credentials(
        client_id=auth[1],
        client_secret=auth[2],
        organization_name=auth[0],
        oidc_endpoint=args.oidcEndpoint,
    )

    client = (
        NanoTDFClient(oidc_credentials=oidc_creds, kas_url=args.kasEndpoint)
        if args.nano
        else TDFClient(oidc_credentials=oidc_creds, kas_url=args.kasEndpoint)
    )

    encrypt_file(
        client,
        args.kasEndpoint,
        args.oidcEndpoint,
        auth[1],
        auth[2],
        auth[0],
        args.nano,
        args.ptfile,
        args.ctfile,
        attributes,
    )


if __name__ == "__main__":
    main()
