import json
import assertions as tdfassertions
import base64
from collections.abc import Callable
import logging
import os
import subprocess
import zipfile
import jsonschema

from pydantic import BaseModel
from typing import Literal

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


sdk_type = Literal["go", "java", "js"]

feature_type = Literal["assertions", "autoconfigure", "nano_ecdsa", "ns_grants"]

sdk_paths: dict[sdk_type, str] = {
    "go": "sdk/go/cli.sh",
    "java": "sdk/java/cli.sh",
    "js": "sdk/js/cli/cli.sh",
}


class DataAttribute(BaseModel):
    attribute: str
    isDefault: bool | None = None
    displayName: str | None = None
    pubKey: str
    kasUrl: str
    schemaVersion: str | None = None


class PolicyBody(BaseModel):
    dataAttributes: list[DataAttribute] | None = None
    dissem: list[str] | None = None


class Policy(BaseModel):
    uuid: str
    body: PolicyBody


class PolicyBinding(BaseModel):
    alg: str
    hash: str


class KeyAccessObject(BaseModel):
    type: str
    url: str
    protocol: str
    wrappedKey: str
    policyBinding: PolicyBinding | str
    encryptedMetadata: str | None = None
    kid: str | None = None
    sid: str | None = None
    tdf_spec_version: str | None = None


class EncryptionMethod(BaseModel):
    algorithm: str
    iv: str | None = None
    isStreamable: bool | None = False


class IntegritySignature(BaseModel):
    alg: str | None = "HS256"
    sig: str


class IntegritySegment(BaseModel):
    hash: str
    segmentSize: int | None = None
    encryptedSegmentSize: int | None = None


class Integrity(BaseModel):
    rootSignature: IntegritySignature
    segmentHashAlg: str
    segmentSizeDefault: int | None = 0
    encryptedSegmentSizeDefault: int | None = 0
    segments: list[IntegritySegment] | None = None


class PayloadReference(BaseModel):
    type: str
    url: str
    protocol: str
    isEncrypted: bool
    mimeType: str | None = None
    tdf_spec_version: str | None = None


class EncryptionInformation(BaseModel):
    type: str
    policy: str
    keyAccess: list[KeyAccessObject]
    method: EncryptionMethod
    integrityInformation: Integrity

    @property
    def policy_object(self) -> Policy:
        b = base64.b64decode(self.policy)
        return Policy.model_validate_json(b)

    @policy_object.setter
    def policy_object(self, value: Policy):
        b = value.model_dump_json().encode()
        self.policy = base64.b64encode(b).decode()


class Manifest(BaseModel):
    encryptionInformation: EncryptionInformation
    payload: PayloadReference
    assertions: list[tdfassertions.Assertion] | None = None


def manifest(tdf_file: str) -> Manifest:
    with zipfile.ZipFile(tdf_file, "r") as tdfz:
        with tdfz.open("0.manifest.json") as manifestEntry:
            return Manifest.model_validate_json(manifestEntry.read())


# Create a modified variant of a TDF by manipulating its manifest
def update_manifest(
    scenario_name: str, tdf_file: str, manifest_change: Callable[[Manifest], Manifest]
) -> str:
    # get the parent directory of the tdf file
    tmp_dir = os.path.dirname(tdf_file)
    fname = os.path.basename(tdf_file).split(".")[0]
    unzipped_dir = os.path.join(tmp_dir, f"{fname}-{scenario_name}-unzipped")
    with zipfile.ZipFile(tdf_file, "r") as zipped:
        zipped.extractall(unzipped_dir)
    with open(os.path.join(unzipped_dir, "0.manifest.json"), "r") as manifest_file:
        manifest_data = Manifest.model_validate_json(manifest_file.read())
    new_manifest_data = manifest_change(manifest_data)
    with open(os.path.join(unzipped_dir, "0.manifest.json"), "w") as manifest_file:
        manifest_file.write(new_manifest_data.model_dump_json())
    outfile = os.path.join(tmp_dir, f"{fname}-{scenario_name}.tdf")
    with zipfile.ZipFile(outfile, "w") as zipped:
        for folder_name, _, filenames in os.walk(unzipped_dir):
            for filename in filenames:
                file_path = os.path.join(folder_name, filename)
                zipped.write(file_path, os.path.relpath(file_path, unzipped_dir))
    return outfile


def validate_manifest_schema(tdf_file: str):
    ## Unzip the tdf
    tmp_dir = os.path.dirname(tdf_file)
    fname = os.path.basename(tdf_file).split(".")[0]
    unzipped_dir = os.path.join(tmp_dir, f"{fname}-manifest-validation-unzipped")
    with zipfile.ZipFile(tdf_file, "r") as zipped:
        zipped.extractall(unzipped_dir)

    ## Get the schema file
    schema_file_path = os.getenv("SCHEMA_FILE")
    if not schema_file_path:
        raise ValueError("SCHEMA_FILE environment variable is not set or is empty.")
    elif not os.path.isfile(schema_file_path):
        raise FileNotFoundError(f"Schema file '{schema_file_path}' not found.")
    with open(schema_file_path, "r") as schema_file:
        schema = json.load(schema_file)

    ## Get the manifest file
    with open(os.path.join(unzipped_dir, "0.manifest.json"), "r") as manifest_file:
        manifest = json.load(manifest_file)

    ## Validate
    jsonschema.validate(instance=manifest, schema=schema)


def encrypt(
    sdk,
    pt_file,
    ct_file,
    mime_type="application/octet-stream",
    fmt="nano",
    attr_values: list[str] | None = None,
    assert_value="",
    use_ecdsa_binding=False,
):
    c = [
        sdk_paths[sdk],
        "encrypt",
        pt_file,
        ct_file,
        fmt,
        mime_type,
    ]
    if attr_values:
        c += [",".join(attr_values)]
    if assert_value:
        if not attr_values:
            c += [""]
        c += [assert_value]
    logger.debug(f"enc [{' '.join(c)}]")

    # Copy the current environment
    env = dict(os.environ)
    if fmt == "nano":
        if use_ecdsa_binding:
            env |= {"USE_ECDSA_BINDING": "true"}
        else:
            env |= {"USE_ECDSA_BINDING": "false"}
    subprocess.check_call(c, env=env)


def decrypt(
    sdk,
    ct_file,
    rt_file,
    fmt="nano",
    assert_keys: str = "",
):
    c = [
        sdk_paths[sdk],
        "decrypt",
        ct_file,
        rt_file,
        fmt,
    ]
    if assert_keys:
        # empty args for mimetype, attrs, and assertions
        c += [
            "",
            "",
            "",
            assert_keys,
        ]
    logger.info(f"dec [{' '.join(c)}]")
    subprocess.check_output(c, stderr=subprocess.STDOUT)


def supports(sdk: sdk_type, feature: feature_type) -> bool:
    match (feature, sdk):
        case ("autoconfigure", ("go" | "java")):
            return True
        case ("nano_ecdsa", "go"):
            return True
        case ("ns_grants", ("go" | "java")):
            return True

    c = [
        sdk_paths[sdk],
        "supports",
        feature,
    ]
    logger.info(f"sup [{' '.join(c)}]")
    try:
        subprocess.check_call(c)
    except subprocess.CalledProcessError:
        return False
    return True
