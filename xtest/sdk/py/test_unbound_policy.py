import json
import os
import zipfile
from opentdf import TDFClient, NanoTDFClient, OIDCCredentials, LogLevel, TDFStorageType

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
    try:
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

    # Unzip the second zip file
        tdf_with_policy_folder = os.path.join(cwd, "with_policy")
        with zipfile.ZipFile(tdf_with_policy, 'r') as zip_ref:
            zip_ref.extractall(tdf_with_policy_folder)

    # Get the policy binding from the second zip file
        fullpath = os.path.join(tdf_with_policy_folder, '0.manifest.json')
        policy_binding = extract_policy_binding(fullpath)

    # Update the policy binding in the first zip file
        fullpath = os.path.join(tdf_nopolicy_folder, '0.manifest.json')
        update_policy_binding(fullpath, policy_binding)

    # Zip the updated files
        updated_tdf_file = "updated_file.tdf"
        with zipfile.ZipFile(updated_tdf_file, 'w') as zip_ref:
            for folder_name, subfolders, filenames in os.walk(tdf_nopolicy_folder):
                for filename in filenames:
                    file_path = os.path.join(folder_name, filename)
                    zip_ref.write(file_path, os.path.relpath(file_path, tdf_nopolicy_folder))


        sampleTdfStorage = TDFStorageType()
        sampleTdfStorage.set_tdf_storage_file_type(os.path.join(cwd, updated_tdf_file))
        client.decrypt_file(sampleTdfStorage, os.path.join(cwd, "sample_policy.txt"))

    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)

if __name__ == "__main__":
    main()
