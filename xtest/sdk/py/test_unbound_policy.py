import json
import logging
import os
import sys
import zipfile

from opentdf import TDFClient, OIDCCredentials, LogLevel, TDFStorageType

OIDC_ENDPONT = "http://localhost:65432/"
KAS_URL = "http://localhost:65432/api/kas"
OIDC_CONFIGURATION_URL = "http://localhost:65432/auth/realms/tdf/.well-known/openid-configuration"

def extract_policy_binding(zip_file_path):
    with open(zip_file_path, "r") as manifest:
            manifest_data = json.load(manifest)
            return manifest_data['encryptionInformation']['keyAccess'][0]['policyBinding']

def update_policy_binding(zip_file_path, new_policy_binding):
    with open(zip_file_path, "r") as manifest:
            manifest_data = json.load(manifest)
            manifest_data['encryptionInformation']['keyAccess'][0]['policyBinding'] = new_policy_binding

    with open(zip_file_path, "w") as manifest:
            json.dump(manifest_data, manifest)

def main():
    # Create OIDC credentials object
    oidc_creds = OIDCCredentials(OIDC_CONFIGURATION_URL)
    oidc_creds.set_client_id_and_client_secret(client_id="tdf-client",
                                               client_secret="123-456")

    client = TDFClient(oidc_credentials=oidc_creds,
                       kas_url=KAS_URL)
    client.enable_console_logging(LogLevel.Debug)
    cwd = os.getcwd()
    sample_txt = os.path.join(cwd, "sample.txt")
    with open(sample_txt, 'w') as file:
        file.write("Virtru")

    sampleTxtStorage = TDFStorageType()
    sampleTxtStorage.set_tdf_storage_file_type(sample_txt)
    tdf_no_policy = os.path.join(cwd, "sample_nopolicy.txt.tdf")

    client.encrypt_file(sampleTxtStorage, tdf_no_policy)

    client.add_data_attribute("https://example.com/attr/Classification/value/M", KAS_URL)
    tdf_with_policy = os.path.join(cwd, "sample_policy.txt.tdf")
    client.encrypt_file(sampleTxtStorage, tdf_with_policy)

    # Unzip the first zip file
    tdf_nopolicy_folder = os.path.join(cwd, "no_policy")
    with zipfile.ZipFile(tdf_no_policy, 'r') as zip_ref:
        zip_ref.extractall(tdf_nopolicy_folder)
        logging.info("Unzipped 1st tdf file: %s", tdf_no_policy)

    # Unzip the second zip file
    tdf_with_policy_folder = os.path.join(cwd, "with_policy")
    with zipfile.ZipFile(tdf_with_policy, 'r') as zip_ref:
        zip_ref.extractall(tdf_with_policy_folder)
        logging.info("Unzipped 2nd tdf file: %s", tdf_with_policy)

    # Get the policy binding from the second zip file
    fullpath = os.path.join(tdf_with_policy_folder, '0.manifest.json')
    policy_binding = extract_policy_binding(fullpath)

    # Update the policy binding in the first zip file
    fullpath = os.path.join(tdf_nopolicy_folder, '0.manifest.json')
    update_policy_binding(fullpath, policy_binding)
    logging.info("Updated policy binding in file: %s", fullpath)

    # Zip the updated files
    updated_tdf_file = "updated_file.tdf"
    with zipfile.ZipFile(updated_tdf_file, 'w') as zip_ref:
        for folder_name, subfolders, filenames in os.walk(tdf_nopolicy_folder):
            for filename in filenames:
                file_path = os.path.join(folder_name, filename)
                zip_ref.write(file_path, os.path.relpath(file_path, tdf_nopolicy_folder))
                logging.info("Added file to zip: %s", file_path)


    sampleTdfStorage = TDFStorageType()
    sampleTdfStorage.set_tdf_storage_file_type(os.path.join(cwd, updated_tdf_file))
    try:
        client.decrypt_file(sampleTdfStorage, os.path.join(cwd, "sample_policy.txt"))
        if os.path.exists(os.path.join(cwd, "sample_policy.txt")):
            logging.error("Decryption was successful, but it was not expected due to a broken policy.")
            sys.exit(1)
        else:
            logging.error("Broken policy ignored")
            sys.exit(0)
    except Exception as e:
        error_message = f"An error occurred: {e}"
        if "[403] Error: [Invalid Binding]" in str(e):
            logging.warning("Expected - Invalid binding error occurred: %s", e)
            print("Invalid binding error occurred.")
        else:
            print("Unexpected error: %s" % sys.exc_info()[0])
            raise

if __name__ == "__main__":
    main()
