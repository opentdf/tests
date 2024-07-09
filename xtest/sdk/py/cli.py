import os
import sys
import logging
from opentdf import TDFClient, NanoTDFClient, OIDCCredentials, LogLevel, TDFStorageType

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

CLIENT_ID = os.getenv("CLIENTID", "opentdf")
CLIENT_SECRET = os.getenv("CLIENTSECRET", "secret")
OIDC_ENDPOINT = os.getenv("KCHOST", "http://localhost:8888")
KAS_URL = os.getenv("KASHOST", "http://localhost:8080/kas")
REALM = os.getenv("REALM", "opentdf")

def main():
    function, source, target, nano = sys.argv[1:5]

    oidc_creds = OIDCCredentials()
    oidc_creds.set_client_credentials_client_secret(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        organization_name=REALM,
        oidc_endpoint=OIDC_ENDPOINT,
    )
    if nano.lower()=="true":
        client = NanoTDFClient(oidc_credentials=oidc_creds, kas_url=KAS_URL)
    else:
        client = TDFClient(oidc_credentials=oidc_creds, kas_url=KAS_URL)
    client.enable_console_logging(LogLevel.Info)

    if function == "encrypt":
        encrypt_file(client, source, target)
    elif function == "decrypt":
        decrypt_file(client, source, target)
    else:
        logger.error("Python -- invalid function type provided")
        sys.exit(1)

def encrypt_file(client, source, target):
    logger.info(f"Python -- Encrypting file {source} to {target}")
    sampleTxtStorage = TDFStorageType()
    sampleTxtStorage.set_tdf_storage_file_type(source)
    client.encrypt_file(sampleTxtStorage, target)

def decrypt_file(client, source, target):
    logger.info(f"Python -- Decrypting file {source} to {target}")
    sampleTdfStorage = TDFStorageType()
    sampleTdfStorage.set_tdf_storage_file_type(source)
    client.decrypt_file(sampleTdfStorage, target)

if __name__ == "__main__":
    main()
