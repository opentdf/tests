import base64
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, TypeIs, get_args

import jsonschema
import pytest
from pydantic import BaseModel

import assertions as tdfassertions

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


def _km1_log_path() -> Path | None:
    """Return km1's log file path from env or auto-discovery, or None if absent."""
    if p := os.getenv("KAS_KM1_LOG_FILE"):
        return Path(p)
    platform_dir = os.getenv("PLATFORM_DIR", "../../platform")
    candidate = Path(platform_dir) / "logs" / "kas-km1.log"
    return candidate if candidate.exists() else None


def _algs_from_km1_log() -> set[str]:
    """Scan km1's startup log to extract the set of configured key algorithms.

    Prefers the INFO 'kas trust mechanisms initialized' summary; falls back to
    the DEBUG 'kas config loaded' keyring dump.
    """
    log = _km1_log_path()
    if not log or not log.exists():
        logger.debug("km1 log not found (path=%s); no algs from log", log)
        return set()
    algs: set[str] = set()
    try:
        with log.open() as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    entry.get("msg") == "kas trust mechanisms initialized"
                    and "mechanisms" in entry
                ):
                    return set(entry["mechanisms"])
                if entry.get("msg") == "kas config loaded" and "config" in entry:
                    for k in entry["config"].get("keyring", []):
                        if alg := k.get("alg"):
                            algs.add(alg)
    except Exception:
        logger.debug("failed reading km1 log %s", log, exc_info=True)
    return algs


def _fetch_well_known() -> dict[str, Any] | None:
    """Fetch the platform's /.well-known/opentdf-configuration. Returns None on error."""
    base = os.getenv("PLATFORMURL", "http://localhost:8080")
    url = f"{base.rstrip('/')}/.well-known/opentdf-configuration"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read())
    except Exception:
        logger.exception("Failed to fetch well-known configuration", exc_info=True)
        return None


def _kas_supports_algorithm(algorithm: str) -> bool:
    """HTTP fallback: probe km1 KAS for a specific algorithm when log is unavailable."""
    # PQ managed keys live on km1, not the main platform KAS (KASURL/PLATFORMURL).
    kasurl = os.getenv(
        "KASURL5",
        os.getenv("KASURL", os.getenv("PLATFORMURL", "http://localhost:8585")),
    )
    parsed = urllib.parse.urlparse(kasurl)
    base = f"{parsed.scheme}://{parsed.netloc}"
    url = f"{base}/kas.AccessService/PublicKey"
    data = json.dumps({"algorithm": algorithm}).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        logger.debug("KAS algorithm probe for %s at %s failed: %s", algorithm, url, e)
        return False


sdk_type = Literal["go", "java", "js"]


def is_sdk_type(val: str) -> TypeIs[sdk_type]:
    return val in get_args(sdk_type)


focus_type = Literal[sdk_type, "all"]

container_type = Literal[
    "ztdf",
    "ztdf-ecwrap",
]

feature_type = Literal[
    "assertions",
    "assertion_verification",
    "attribute_traversal",
    "audit_logging",
    "autoconfigure",
    "better-messages-2024",
    "bulk_rewrap",
    "connectrpc",
    # DPoP (RFC 9449): sender-constrained access tokens. SDK signs a DPoP proof
    # JWT per request; KAS validates the proof and binds the access token to
    # the proof's JWK thumbprint (cnf.jkt).
    "dpop",
    # Server-issued DPoP-Nonce challenge flow (RFC 9449 §8). Gated separately
    # because SDKs can support `dpop` without yet implementing the 401-retry
    # required by nonce mode (e.g. java-sdk's deferred 401-retry).
    "dpop_nonce_challenge",
    "ecwrap",
    "hexless",
    "hexaflexible",
    "kasallowlist",
    # Allow and respect assigning specific keys (kas url + key id) to attributes,
    # including splitting with multiple keys on the same kas (sdk feature),
    # and explicit management of the KAS keys through the policy service (otdfctl+service feature).
    "key_management",
    # Support for encrypting with RSA-4096 managed keys.
    "mechanism-rsa-4096",
    # Support for encrypting with EC curves secp384r1 and secp521r1 managed keys.
    "mechanism-ec-curves-384-521",
    # Support for encrypting with X-Wing hybrid post-quantum/traditional KEM.
    "mechanism-xwing",
    # Support for encrypting with hybrid post-quantum/traditional KEM with NIST Elliptic Curves.
    "mechanism-secpmlkem",
    # Support for pure (non-hybrid) ML-KEM key wrapping: mlkem:768 and mlkem:1024.
    "mechanism-mlkem",
    "ns_grants",
    "obligations",
]

container_version = Literal["4.2.2", "4.3.0"]

policy_type = Literal["plaintext", "encrypted"]
"""How policy (data attributes) should be bound within the output container on encrypt."""


class PlatformFeatureSet(BaseModel):
    version: str | None = None
    semver: tuple[int, int, int] | None = None
    features: set[feature_type] = {
        "assertions",
        "assertion_verification",
        "autoconfigure",
        "better-messages-2024",
    }

    def __init__(self, **kwargs: dict[str, Any]):
        super().__init__(**kwargs)
        v = os.getenv("PLATFORM_VERSION")
        if not v:
            print("PLATFORM_VERSION unset or empty; defaulting to 0.9.0")
            v = "0.9.0"

        self.version = v
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
            self.features.add("hexaflexible")

        if self.semver >= (0, 4, 19):
            self.features.add("ns_grants")

        if self.semver >= (0, 4, 28):
            self.features.add("connectrpc")

        if self.semver >= (0, 6, 0):
            self.features.add("key_management")

        # Audit logging was added in platform v0.10.0
        # Version 0.9.0 and earlier do not emit audit logs
        if self.semver >= (0, 10, 0):
            self.features.add("audit_logging")

        # Included in service v0.11.0, (Golang SDK v0.10.0, Web-SDK v0.5.0, Java SDK n/a)
        if self.semver >= (0, 11, 0):
            self.features.add("obligations")

        # Included in platform v0.12.0
        if self.semver >= (0, 12, 0):
            self.features.add("attribute_traversal")
        # In ocrypto < 0.10.0, there was a bug that hardcoded to P256 on uncompressing the EC public key,
        # even if the key was actually P384 or P521. This was fixed in ocrypto 0.10.0, so we can only support EC
        # wrapping with those curves on platforms v0.13.0 and later.
        if self.semver >= (0, 13, 0):
            self.features.add("mechanism-ec-curves-384-521")

        # PQ/T KEM support (xwing, secp+ML-KEM hybrids, pure ML-KEM): read km1's
        # startup log rather than guessing by version, since release targets shift
        # and a platform may have keys configured without a finalized version bump.
        # Falls back to HTTP probe if the log file is unavailable.
        # Only attempt on platforms new enough to plausibly have PQ support.
        if self.semver is None or self.semver >= (0, 13, 0):
            algs = _algs_from_km1_log()
            if not algs:
                algs = {
                    a
                    for a in ("hpqt:xwing", "hpqt:secp256r1-mlkem768", "mlkem:768")
                    if _kas_supports_algorithm(a)
                }
            if "hpqt:xwing" in algs:
                self.features.add("mechanism-xwing")
            if any(a.startswith("hpqt:secp") for a in algs):
                self.features.add("mechanism-secpmlkem")
            if any(a.startswith("mlkem:") for a in algs):
                self.features.add("mechanism-mlkem")

        # DPoP capabilities via well-known. Branch builds report stale semver
        # so we probe the live endpoint instead of gating by version.
        wk = _fetch_well_known()
        if wk:
            algs = wk.get("dpop_signing_alg_values_supported")
            if isinstance(algs, list) and algs:
                self.features.add("dpop")
            if wk.get("dpop_nonce_required") is True:
                self.features.add("dpop_nonce_challenge")

        print(f"PLATFORM_VERSION '{v}' supports [{', '.join(self.features)}]")

    def skip_if_unsupported(self, *features: feature_type):
        """Skip the current test if any of the given features are unsupported."""
        missing = [f for f in features if f not in self.features]
        if missing:
            pytest.skip(
                f"platform service {self.version} doesn't yet support {missing}"
            )


_cached_pfs: PlatformFeatureSet | None = None


def get_platform_features() -> PlatformFeatureSet:
    """Return a cached PlatformFeatureSet singleton."""
    global _cached_pfs
    if _cached_pfs is None:
        _cached_pfs = PlatformFeatureSet()
    return _cached_pfs


class DataAttribute(BaseModel):
    attribute: str
    isDefault: bool | None = None
    displayName: str | None = None
    pubKey: str | None = None
    kasUrl: str | None = None
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
    ephemeralPublicKey: str | None = None
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
    segments: list[IntegritySegment] = []


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
    schemaVersion: str | None = None


_version_re = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9a-zA-Z.-]+))?(?:\+([0-9a-zA-Z.-]+))?$"
)
_partial_version_re = re.compile(
    r"^(\d+)(?:\.(\d+)(?:\.(\d+))?)?(?:-([0-9a-zA-Z.-]*))?(?:\+([0-9a-zA-Z.-]*))?$"
)


def manifest(tdf_file: Path) -> Manifest:
    with zipfile.ZipFile(tdf_file, "r") as tdfz:
        with tdfz.open("0.manifest.json") as manifestEntry:
            return Manifest.model_validate_json(manifestEntry.read())


# Create a modified variant of a TDF by manipulating its manifest
def update_manifest(
    scenario_name: str, tdf_file: Path, manifest_change: Callable[[Manifest], Manifest]
) -> Path:
    # get the parent directory of the tdf file
    tmp_dir = tdf_file.parent
    fname = tdf_file.stem
    unzipped_dir = tmp_dir / f"{fname}-{scenario_name}-unzipped"
    with zipfile.ZipFile(tdf_file, "r") as zipped:
        zipped.extractall(unzipped_dir)
    with (unzipped_dir / "0.manifest.json").open("r") as manifest_file:
        manifest_data = Manifest.model_validate_json(manifest_file.read())
    new_manifest_data = manifest_change(manifest_data)
    with (unzipped_dir / "0.manifest.json").open("w") as manifest_file:
        manifest_file.write(new_manifest_data.model_dump_json(by_alias=True))
    outfile = tmp_dir / f"{fname}-{scenario_name}.tdf"
    with zipfile.ZipFile(outfile, "w") as zipped:
        for folder_name, _, filenames in os.walk(unzipped_dir):
            folder = Path(folder_name)
            for filename in filenames:
                file_path = folder / filename
                zipped.write(file_path, file_path.relative_to(unzipped_dir))
    # Cleanup the unzipped directory; its contents are now stored as outfile
    shutil.rmtree(unzipped_dir, ignore_errors=True)
    return outfile


# Create a modified variant of a TDF by manipulating its payload
def update_payload(
    scenario_name: str, tdf_file: Path, payload_change: Callable[[bytes], bytes]
) -> Path:
    tmp_dir = tdf_file.parent
    fname = tdf_file.stem
    unzipped_dir = tmp_dir / f"{fname}-{scenario_name}-unzipped"
    with zipfile.ZipFile(tdf_file, "r") as zipped:
        zipped.extractall(unzipped_dir)
    with (unzipped_dir / "0.payload").open("rb") as payload_file:
        payload_data = payload_file.read()
    new_payload_data = payload_change(payload_data)
    with (unzipped_dir / "0.payload").open("wb") as payload_file:
        payload_file.write(new_payload_data)
    outfile = tmp_dir / f"{fname}-{scenario_name}.tdf"
    with zipfile.ZipFile(outfile, "w") as zipped:
        for folder_name, _, filenames in os.walk(unzipped_dir):
            for filename in filenames:
                file_path = Path(folder_name) / filename
                zipped.write(file_path, file_path.relative_to(unzipped_dir))
    # Cleanup the unzipped directory; its contents are now stored as outfile
    shutil.rmtree(unzipped_dir, ignore_errors=True)
    return outfile


def validate_manifest_schema(tdf_file: Path):
    ## Get the schema file
    schema_file_path = os.getenv("SCHEMA_FILE")
    if not schema_file_path:
        raise ValueError("SCHEMA_FILE environment variable is not set or is empty.")
    elif not os.path.isfile(schema_file_path):
        raise FileNotFoundError(f"Schema file '{schema_file_path}' not found.")
    with open(schema_file_path) as schema_file:
        schema = json.load(schema_file)

    ## Load the manifest file directly from the zipfile
    with zipfile.ZipFile(tdf_file, "r") as zipped:
        with zipped.open("0.manifest.json") as manifest_file:
            manifest = json.load(manifest_file)

    ## Validate
    jsonschema.validate(instance=manifest, schema=schema)


def fmt_env(env: dict[str, str]) -> str:
    a: list[str] = []
    for k, v in env.items():
        a.append(f"{k}='{v}'")
    return " ".join(a)


def simple_container(container: container_type) -> container_type:
    if container == "ztdf-ecwrap":
        return "ztdf"
    return container


class SDK:
    sdk: sdk_type
    version: str
    _supports: dict[feature_type, bool]

    def __init__(self, sdk: sdk_type, version: str = "main"):
        self.sdk = sdk
        self.path = f"sdk/{sdk}/dist/{version}/cli.sh"
        self._supports = {}
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

    def is_released(self) -> bool:
        return bool(
            re.fullmatch(
                r"(?:sdk/)?v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", self.version
            )
        )

    def encrypt(
        self,
        pt_file: Path,
        ct_file: Path,
        mime_type: str = "application/octet-stream",
        container: container_type = "ztdf",
        attr_values: list[str] | None = None,
        assert_value: str = "",
        policy_mode: str = "encrypted",
        target_mode: container_version | None = None,
    ):
        use_ecwrap = container == "ztdf-ecwrap"
        fmt = simple_container(container)
        c = [
            self.path,
            "encrypt",
            str(pt_file),
            str(ct_file),
            fmt,
        ]

        local_env: dict[str, str] = {}
        if mime_type:
            local_env |= {"XT_WITH_MIME_TYPE": mime_type}

        if attr_values:
            local_env |= {"XT_WITH_ATTRIBUTES": ",".join(attr_values)}

        if assert_value:
            local_env |= {"XT_WITH_ASSERTIONS": assert_value}

        if fmt == "ztdf" and target_mode:
            local_env |= {"XT_WITH_TARGET_MODE": target_mode}

        if use_ecwrap:
            local_env |= {"XT_WITH_ECWRAP": "true"}
        logger.debug(f"enc [{' '.join([fmt_env(local_env)] + c)}]")
        env = dict(os.environ)
        env |= local_env
        result = subprocess.run(c, env=env, capture_output=True)
        if result.returncode != 0:
            if result.stdout:
                logger.error("enc stdout: %s", result.stdout.decode(errors="replace"))
            if result.stderr:
                logger.error("enc stderr: %s", result.stderr.decode(errors="replace"))
            raise subprocess.CalledProcessError(
                result.returncode, c, output=result.stdout, stderr=result.stderr
            )

    def decrypt(
        self,
        ct_file: Path,
        rt_file: Path,
        container: container_type = "ztdf",
        assert_keys: str = "",
        verify_assertions: bool = True,
        ecwrap: bool = False,
        expect_error: bool = False,
        kasallowlist: str = "",
        ignore_kas_allowlist: bool = False,
    ):
        fmt = simple_container(container)

        c = [
            self.path,
            "decrypt",
            str(ct_file),
            str(rt_file),
            fmt,
        ]

        local_env: dict[str, str] = {}
        if assert_keys:
            local_env |= {"XT_WITH_ASSERTION_VERIFICATION_KEYS": assert_keys}
        if ecwrap:
            local_env |= {"XT_WITH_ECWRAP": "true"}
        if not verify_assertions:
            local_env |= {"XT_WITH_VERIFY_ASSERTIONS": "false"}
        if kasallowlist:
            local_env |= {"XT_WITH_KAS_ALLOWLIST": kasallowlist}
        if ignore_kas_allowlist:
            local_env |= {"XT_WITH_IGNORE_KAS_ALLOWLIST": "true"}
        logger.info(f"dec [{' '.join([fmt_env(local_env)] + c)}]")
        env = dict(os.environ)
        env |= local_env
        if expect_error:
            subprocess.check_output(c, stderr=subprocess.STDOUT, env=env)
        else:
            result = subprocess.run(c, env=env, capture_output=True)
            if result.returncode != 0:
                if result.stdout:
                    logger.error(
                        "dec stdout: %s", result.stdout.decode(errors="replace")
                    )
                if result.stderr:
                    logger.error(
                        "dec stderr: %s", result.stderr.decode(errors="replace")
                    )
                raise subprocess.CalledProcessError(
                    result.returncode, c, output=result.stdout, stderr=result.stderr
                )

    def supports(self, feature: feature_type) -> bool:
        if feature in self._supports:
            return self._supports[feature]
        self._supports[feature] = self._uncached_supports(feature)
        return self._supports[feature]

    def skip_if_unsupported(self, *features: feature_type):
        for feature in features:
            if not self.supports(feature):
                pytest.skip(f"{self} sdk doesn't yet support [{feature}]")

    def _uncached_supports(self, feature: feature_type) -> bool:
        match (feature, self.sdk):
            case ("key_management", "js") if self.version == "v0.2.0":
                # JS SDK v0.2.0 incorrectly reports support for key_management.
                return False
            case ("autoconfigure", ("go" | "java")):
                return True
            case ("better-messages-2024", ("js" | "java")):
                return True
            case ("ns_grants", ("go" | "java")):
                return True
            case ("mechanism-rsa-4096", "go"):
                return True
            case ("mechanism-ec-curves-384-521", "go"):
                return True
            case ("mechanism-ec-curves-384-521", "js"):
                return False
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
    sdk_path = os.path.join("sdk", sdk, "dist")
    if not os.path.isdir(sdk_path):
        return []
    return [
        SDK(sdk, version)
        for version in os.listdir(sdk_path)
        if os.path.isdir(os.path.join(sdk_path, version))
    ]


def parse_sdk_spec(spec: str) -> list[SDK]:
    """Parse an SDK specifier into SDK objects.

    Supports:
    - "go" or "go@*" → all versions in sdk/go/dist/
    - "go@main" or "go@v0.18.0" → only that specific version
    """
    if "@" in spec:
        sdk_type_val, version = spec.split("@", 1)
        if not is_sdk_type(sdk_type_val):
            raise ValueError(f"Unknown SDK type: {sdk_type_val!r}")
        if version == "*":
            return all_versions_of(sdk_type_val)
        return [SDK(sdk_type_val, version)]
    if not is_sdk_type(spec):
        raise ValueError(f"Unknown SDK type: {spec!r}")
    return all_versions_of(spec)


def skip_if_unsupported(sdk: SDK, *features: feature_type):
    pfs = get_platform_features()
    pfs.skip_if_unsupported(*features)
    sdk.skip_if_unsupported(*features)


def skip_hexless_skew(encrypt_sdk: SDK, decrypt_sdk: SDK):
    if encrypt_sdk.supports("hexaflexible"):
        return
    if encrypt_sdk.supports("hexless") and not decrypt_sdk.supports("hexless"):
        pytest.skip(
            f"{decrypt_sdk} sdk doesn't yet support [hexless], but {encrypt_sdk} does"
        )


def skip_connectrpc_skew(encrypt_sdk: SDK, decrypt_sdk: SDK, pfs: PlatformFeatureSet):
    return False


def _parse_semver(version: str) -> tuple[int, int, int] | None:
    """Parse a version string (with optional 'v' prefix) into (major, minor, patch)."""
    m = _version_re.match(version.lstrip("v"))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _otdfctl_semver() -> tuple[int, int, int] | None:
    """Parse otdfctl version from OTDFCTL_HEADS; None if unresolvable (main, dev, etc.)."""
    oh = os.environ.get("OTDFCTL_HEADS", "[]")
    try:
        heads = json.loads(oh)
    except json.JSONDecodeError:
        return None
    if not heads:
        return None
    return _parse_semver(str(heads[0]))


# go SDK ≤ this version used pre-ocrypto-0.13.0 hybrid KEM format (non-conformant).
_PQC_HYBRID_FORMAT_CUTOFF = (0, 33, 0)


def skip_pqc_hybrid_format_skew(encrypt_sdk: SDK | None = None) -> None:
    """Skip if the encrypt SDK or otdfctl predates the lib/ocrypto v0.13.0 hybrid-KEM format.

    Two independent sources of format incompatibility:
    - otdfctl ≤ 0.33.0: registers hybrid KAS keys in old non-conformant format.
    - go encrypt SDK ≤ 0.33.0: produces hybrid KEM ciphertexts (wrappedKey) in old format.
    Either causes opaque crypto failures when paired with a platform that has hybrid PQC
    support enabled (new-format KAS); skip early with a clear message instead.
    """
    pfs = get_platform_features()
    if (
        "mechanism-xwing" not in pfs.features
        and "mechanism-secpmlkem" not in pfs.features
    ):
        return
    otdfctl_ver = _otdfctl_semver()
    if otdfctl_ver is not None and otdfctl_ver <= _PQC_HYBRID_FORMAT_CUTOFF:
        pytest.skip(
            f"otdfctl v{'.'.join(map(str, otdfctl_ver))} predates lib/ocrypto v0.13.0; "
            "hybrid key material format is incompatible with this platform"
        )
    if (
        encrypt_sdk is not None
        and encrypt_sdk.sdk == "go"
        and encrypt_sdk.is_released()
    ):
        sdk_ver = _parse_semver(encrypt_sdk.version)
        if sdk_ver is not None and sdk_ver <= _PQC_HYBRID_FORMAT_CUTOFF:
            pytest.skip(
                f"{encrypt_sdk} predates lib/ocrypto v0.13.0; "
                "hybrid KEM ciphertext format is incompatible with this platform"
            )


def select_target_version(
    encrypt_sdk: SDK, decrypt_sdk: SDK
) -> container_version | None:
    if encrypt_sdk.supports("hexaflexible") and not decrypt_sdk.supports("hexless"):
        return "4.2.2"
    if encrypt_sdk.supports("hexaflexible") and decrypt_sdk.supports("hexless"):
        return "4.3.0"
    return None
