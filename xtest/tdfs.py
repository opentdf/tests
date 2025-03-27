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

focus_type = Literal[sdk_type, "all"]

container_type = Literal[
    "nano",
    "nano-with-ecdsa",
    "ztdf",
    "ztdf-ecwrap",
]

feature_type = Literal[
    "assertions",
    "assertion_verification",
    "autoconfigure",
    "ecwrap",
    "hexless",
    "nano_ecdsa",
    "ns_grants",
]

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
    policyBinding: str | PolicyBinding
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
    sig: bytes


class IntegritySegment(BaseModel):
    hash: bytes
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
    assertions: list[tdfassertions.Assertion] | None = []


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


# Create a modified variant of a TDF by manipulating its payload
def update_payload(
    scenario_name: str, tdf_file: str, payload_change: Callable[[bytes], bytes]
) -> str:
    tmp_dir = os.path.dirname(tdf_file)
    fname = os.path.basename(tdf_file).split(".")[0]
    unzipped_dir = os.path.join(tmp_dir, f"{fname}-{scenario_name}-unzipped")
    with zipfile.ZipFile(tdf_file, "r") as zipped:
        zipped.extractall(unzipped_dir)
    with open(os.path.join(unzipped_dir, "0.payload"), "rb") as payload_file:
        payload_data = payload_file.read()
    new_payload_data = payload_change(payload_data)
    with open(os.path.join(unzipped_dir, "0.payload"), "wb") as payload_file:
        payload_file.write(new_payload_data)
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


def fmt_env(env: dict[str, str]) -> str:
    a: list[str] = []
    for k, v in env.items():
        a.append(f"{k}='{v}'")
    return " ".join(a)


class SDK:
    sdk: sdk_type
    def __init__(self, sdk: sdk_type, version: str = "main"):
        self.sdk = sdk
        self.path = f"sdk/{sdk}/dist/{version}/cli.sh" 
        self.version = version
        if not os.path.isfile(self.path):
            raise FileNotFoundError(f"SDK executable not found at path: {self.path}")

    def __str__(self) -> str:
        return f"{self.sdk}@{self.version}"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SDK):
            return NotImplemented
        return self.sdk == other.sdk and self.version == other.version

    def __hash__(self) -> int:
        return hash((self.sdk, self.version))

    def encrypt(
        self,
        pt_file: str,
        ct_file: str,
        mime_type: str = "application/octet-stream",
        fmt: container_type = "nano",
        attr_values: list[str] | None = None,
        assert_value: str = "",
        use_ecdsa_binding: bool = False,
        ecwrap: bool = False,
    ):
        c = [
            self.path,
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

        local_env: dict[str, str] = {}
        if fmt == "nano":
            if use_ecdsa_binding:
                local_env |= {"USE_ECDSA_BINDING": "true"}
            else:
                local_env |= {"USE_ECDSA_BINDING": "false"}
        if ecwrap:
            local_env |= {"ECWRAP": "true"}
        logger.debug(f"enc [{' '.join([fmt_env(local_env)]+ c)}]")
        env = dict(os.environ)
        env |= local_env
        subprocess.check_call(c, env=env)

    def decrypt(
        self,
        ct_file: str,
        rt_file: str,
        fmt: container_type = "nano",
        assert_keys: str = "",
        verify_assertions: bool = True,
        ecwrap: bool = False,
        expect_error: bool = False,
    ):
        c = [
            self.path,
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
        local_env: dict[str, str] = {}
        if ecwrap:
            local_env |= {"ECWRAP": "true"}
        if not verify_assertions:
            local_env |= {"VERIFY_ASSERTIONS": "false"}
        logger.info(f"dec [{' '.join([fmt_env(local_env)] + c)}]")
        env = dict(os.environ)
        env |= local_env
        if expect_error:
            subprocess.check_output(c, stderr=subprocess.STDOUT, env=env)
        else:
            subprocess.check_call(c, env=env)

    def supports(self, feature: feature_type) -> bool:
        match (feature, self.sdk):
            case ("autoconfigure", ("go" | "java")):
                return True
            case ("nano_ecdsa", "go"):
                return True
            case ("ns_grants", ("go" | "java")):
                return True
            case _:
                pass

        c = [
            self.path,
            "supports",
            feature,
        ]
        logger.info(f"sup [{' '.join(c)}]")
        try:
            subprocess.check_call(c)
        except subprocess.CalledProcessError:
            return False
        return True
