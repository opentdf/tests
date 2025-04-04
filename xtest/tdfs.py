import json
import jsonschema
import base64
import logging
import os
import re
import subprocess
import zipfile

import pytest

import assertions as tdfassertions


from collections.abc import Callable
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


class PlatformFeatureSet(BaseModel):
    version: str | None = None
    semver: tuple[int, int, int] | None = None
    features: set[feature_type] = set(
        ["assertions", "assertion_verification", "autoconfigure"]
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        v = os.getenv("PLATFORM_VERSION")
        if not v:
            print("PLATFORM_VERSION environment variable is not set or is empty.")
            return

        ver_match = _version_re.match(v)
        if not ver_match:
            print(f"PLATFORM_VERSION '{v}' does not match the expected format.")
            return
        major, minor, patch, _, _ = ver_match.groups()

        self.semver = (int(major), int(minor), int(patch))

        # TODO: Test bulk rewrap
        # if self.semver >= (0, 4, 40):
        #     self.features.add("bulk_rewrap")

        # While announced in 0.4.39, that version had the wrong salt
        if self.semver >= (0, 4, 40):
            self.features.add("ecwrap")

        # Included in SDK 0.3.27, service 0.4.39
        if self.semver >= (0, 4, 39):
            self.features.add("hexless")

        if self.semver >= (0, 4, 23):
            self.features.add("nano_ecdsa")

        if self.semver >= (0, 4, 19):
            self.features.add("ns_grants")
        print(f"PLATFORM_VERSION '{v}' supports [{', '.join(self.features)}]")


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


_version_re = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9a-zA-Z.-]+))?(?:\+([0-9a-zA-Z.-]+))?$"
)
_partial_version_re = re.compile(
    r"^(\d+)(?:\.(\d+)(?:\.(\d+))?)?(?:-([0-9a-zA-Z.-]*))?(?:\+([0-9a-zA-Z.-]*))?$"
)


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


def simple_container(container: container_type) -> container_type:
    if container == "nano-with-ecdsa":
        return "nano"
    if container == "ztdf-ecwrap":
        return "ztdf"
    return container


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

    def __repr__(self) -> str:
        return f"SDK(sdk={self.sdk!r}, version={self.version!r})"

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
        container: container_type = "nano",
        attr_values: list[str] | None = None,
        assert_value: str = "",
    ):
        use_ecdsa = container == "nano-with-ecdsa"
        use_ecwrap = container == "ztdf-ecwrap"
        fmt = simple_container(container)
        c = [
            self.path,
            "encrypt",
            pt_file,
            ct_file,
            fmt,
        ]

        local_env: dict[str, str] = {}
        if mime_type:
            local_env |= {"XT_WITH_MIME_TYPE": mime_type}

        if attr_values:
            local_env |= {"XT_WITH_ATTRIBUTES": ",".join(attr_values)}

        if assert_value:
            local_env |= {"XT_WITH_ASSERTIONS": assert_value}

        if fmt == "nano":
            if use_ecdsa:
                local_env |= {"XT_WITH_ECDSA_BINDING": "true"}
            else:
                local_env |= {"XT_WITH_ECDSA_BINDING": "false"}
        if use_ecwrap:
            local_env |= {"XT_WITH_ECWRAP": "true"}
        logger.debug(f"enc [{' '.join([fmt_env(local_env)]+ c)}]")
        env = dict(os.environ)
        env |= local_env
        subprocess.check_call(c, env=env)

    def decrypt(
        self,
        ct_file: str,
        rt_file: str,
        container: container_type = "nano",
        assert_keys: str = "",
        verify_assertions: bool = True,
        ecwrap: bool = False,
        expect_error: bool = False,
    ):
        fmt = simple_container(container)

        c = [
            self.path,
            "decrypt",
            ct_file,
            rt_file,
            fmt,
        ]

        local_env: dict[str, str] = {}
        if assert_keys:
            local_env |= {"XT_WITH_ASSERTION_VERIFICATION_KEYS": assert_keys}
        if ecwrap:
            local_env |= {"XT_WITH_ECWRAP": "true"}
        if not verify_assertions:
            local_env |= {"XT_WITH_VERIFY_ASSERTIONS": "false"}
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


def all_versions_of(sdk: sdk_type) -> list[SDK]:
    versions: list[SDK] = []
    sdk_path = os.path.join("sdk", sdk, "dist")
    for version in os.listdir(sdk_path):
        if os.path.isdir(os.path.join(sdk_path, version)):
            versions.append(SDK(sdk, version))
    return versions


def skip_if_unsupported(sdk: SDK, *features: feature_type):
    pfs = PlatformFeatureSet()
    for feature in features:
        if not sdk.supports(feature):
            pytest.skip(f"{sdk} sdk doesn't yet support [{feature}]")
        if feature not in pfs.features:
            pytest.skip(
                f"platform service {pfs.version} doesn't yet support [{feature}]"
            )


def skip_hexless_skew(encrypt_sdk: SDK, decrypt_sdk: SDK):
    if encrypt_sdk.supports("hexless") and not decrypt_sdk.supports("hexless"):
        pytest.skip(
            f"{decrypt_sdk} sdk doesn't yet support [hexless], but {encrypt_sdk} does"
        )
