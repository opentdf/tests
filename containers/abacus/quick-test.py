import sys
from tdf3sdk import NanoTDFClient, LogLevel

SERVER = "https://etheria.local/eas"
# encrypt the file and apply the policy on tdf file and also decrypt.
try:
    # Create a client
    client = NanoTDFClient(
        eas_url=SERVER,
        user="CN=bob_5678",
        clientKeyFileName="./certs/client-bob.key",
        clientCertFileName="./certs/client-bob.crt",
        sdkConsumerCertAuthority="./certs/ca.crt",
    )
    client.enable_console_logging(LogLevel.Info)

    #################################################
    # Data API
    #################################################
    plain_text = "Hello world!!"
    tdf_data = client.encrypt_string(plain_text)
    decrypted_plain_text = client.decrypt_string(tdf_data)
    if plain_text == decrypted_plain_text.decode("ascii"):
        print("TDF Encrypt/Decrypt is successful!!")
    else:
        print("Error: TDF Encrypt/Decrypt failed!!")
except:
    print("Unexpected error: %s" % sys.exc_info()[0])
    raise
