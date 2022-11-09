import os
import sys
import logging
from opentdf import TDFClient, OIDCCredentials, LogLevel, TDFStorageType

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

CLIENT_ID = "tdf-client"
CLIENT_SECRET = "123-456"
OIDC_ENDPOINT = "http://localhost:65432"
KAS_URL = "http://localhost:65432/api/kas"
REALM = "tdf"

def main():
    function, source, target = sys.argv[1:4]

    oidc_creds = OIDCCredentials()
    oidc_creds.set_client_credentials_client_secret(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        organization_name=REALM,
        oidc_endpoint=OIDC_ENDPOINT,
    )
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
