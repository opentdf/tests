import logging
import subprocess
import zipfile

from pydantic import BaseModel

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


sdk_paths = {
    "go": "sdk/go/cli.sh",
    "java": "sdk/java/cli.sh",
    "js": "sdk/js/cli/cli.sh",
}


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


class Manifest(BaseModel):
    encryptionInformation: EncryptionInformation
    payload: PayloadReference


def manifest(tdf_file: str) -> Manifest:
    with zipfile.ZipFile(tdf_file, "r") as tdfz:
        with tdfz.open("0.manifest.json") as manifestEntry:
            return Manifest.model_validate_json(manifestEntry.read())


def encrypt(
    sdk,
    pt_file,
    ct_file,
    mime_type="application/octet-stream",
    fmt="nano",
    attr_values=[],
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
    logger.debug(f"enc [{' '.join(c)}]")
    subprocess.check_call(c)


def decrypt(sdk, ct_file, rt_file, fmt="nano"):
    c = [
        sdk_paths[sdk],
        "decrypt",
        ct_file,
        rt_file,
        fmt,
    ]
    logger.info(f"dec [{' '.join(c)}]")
    subprocess.check_call(c)
