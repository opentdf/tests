"""Static TDF corpus: sidecar parsing, per-SDK verdict resolution, decrypt helpers.

Pure and offline: no platform or SDK imports, so the units tier can use it.
"""

import base64
import contextlib
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

Semver = tuple[int, int, int]
Verdict = Literal["decrypt", "reject"]
Outcome = Literal["decrypt", "reject", "wrong-plaintext"]

CORPUS_DIR = Path(__file__).parent / "corpus"
PREFIXES: tuple[str, ...] = (
    "golden-",
    "sdk-",
    "tamper-",
    "zip-legal-",
    "zip-adversarial-",
    "synthetic-",
)

SIDECAR_SUFFIX = ".expect.toml"
NON_FIXTURES = {"README.md", "kas-keys.json"}
TOP_LEVEL_KEYS = {
    "expect",
    "format",
    "strict",
    "must_contain",
    "must_not_contain",
    "note",
    "verify_crypto",
    "key",
    "share_keys",
    "assertion_keys",
}
SDK_NAMES = ("go", "java", "js")
SDK_TABLE_KEYS = {"plaintext_sha256", "note", *SDK_NAMES}
VERDICTS = ("decrypt", "reject")
BOUND_KEYS = ("since", "before", "platform_since", "platform_before")
ENTRY_KEYS = {"verdict", *BOUND_KEYS}

_sha256_re = re.compile(r"[0-9a-f]{64}")
_semver_re = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _parse_semver(version: str) -> Semver | None:
    m = _semver_re.fullmatch(version)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


@dataclass(frozen=True)
class Bounded:
    verdict: Verdict
    since: Semver | None
    before: Semver | None
    platform_since: Semver | None
    platform_before: Semver | None


@dataclass(frozen=True)
class SdkTable:
    plaintext_sha256: str | None
    note: str | None
    verdicts: dict[Literal["go", "java", "js"], list[Bounded]]


@dataclass(frozen=True)
class Sidecar:
    fixture: Path
    raw: dict[str, Any]
    sdk: SdkTable | None


class SidecarError(ValueError):
    pass


def _parse_entry(path: Path, sdk: str, entry: object) -> Bounded:
    where = f"{path}: [sdk] {sdk}"
    if not isinstance(entry, dict) or "verdict" not in entry:
        raise SidecarError(f"{where}: entry must be a table with 'verdict'")
    for key in entry:
        if key not in ENTRY_KEYS:
            raise SidecarError(f"{where}: unknown key {key!r}")
    verdict = entry["verdict"]
    if verdict not in VERDICTS:
        raise SidecarError(f"{where}: bad verdict {verdict!r}")
    bounds: dict[str, Semver | None] = {}
    for key in BOUND_KEYS:
        raw = entry.get(key)
        if raw is None:
            bounds[key] = None
            continue
        parsed = _parse_semver(raw) if isinstance(raw, str) else None
        if parsed is None:
            raise SidecarError(f"{where}: malformed bound {key}={raw!r}")
        bounds[key] = parsed
    for lo, hi in (("since", "before"), ("platform_since", "platform_before")):
        lo_v, hi_v = bounds[lo], bounds[hi]
        if lo_v is not None and hi_v is not None and lo_v >= hi_v:
            raise SidecarError(f"{where}: {lo} must be less than {hi}")
    return Bounded(cast(Verdict, verdict), **bounds)


def _parse_verdicts(path: Path, sdk: str, value: object) -> list[Bounded]:
    if isinstance(value, str):
        if value not in VERDICTS:
            raise SidecarError(f"{path}: [sdk] {sdk}: bad verdict {value!r}")
        return [Bounded(cast(Verdict, value), None, None, None, None)]
    if not isinstance(value, list) or not value:
        raise SidecarError(f"{path}: [sdk] {sdk}: expected a verdict or a list")
    entries = [_parse_entry(path, sdk, e) for e in value]
    for i, entry in enumerate(entries):
        unbounded = all(getattr(entry, k) is None for k in BOUND_KEYS)
        if unbounded and i != len(entries) - 1:
            raise SidecarError(
                f"{path}: [sdk] {sdk}: only the last entry may be unbounded;"
                f" entry {i} shadows the rest"
            )
        if not unbounded and i == len(entries) - 1:
            raise SidecarError(f"{path}: [sdk] {sdk}: last entry must be unbounded")
    return entries


def _parse_sdk_table(path: Path, raw: object) -> SdkTable:
    if not isinstance(raw, dict):
        raise SidecarError(f"{path}: 'sdk' must be a table")
    for key in raw:
        if key not in SDK_TABLE_KEYS:
            raise SidecarError(f"{path}: unknown [sdk] key {key!r}")
    for name in SDK_NAMES:
        if name not in raw:
            raise SidecarError(f"{path}: [sdk] is missing {name!r}")
    verdicts = {name: _parse_verdicts(path, name, raw[name]) for name in SDK_NAMES}
    digest = raw.get("plaintext_sha256")
    if digest is not None and not (
        isinstance(digest, str) and _sha256_re.fullmatch(digest)
    ):
        raise SidecarError(
            f"{path}: [sdk] plaintext_sha256 must be 64 lowercase hex characters"
        )
    note = raw.get("note")
    if note is not None and not isinstance(note, str):
        raise SidecarError(f"{path}: [sdk] note must be a string")
    if digest is None and any(
        e.verdict == "decrypt" for entries in verdicts.values() for e in entries
    ):
        raise SidecarError(
            f"{path}: [sdk] plaintext_sha256 is required when any verdict is decrypt"
        )
    return SdkTable(
        plaintext_sha256=digest,
        note=note,
        verdicts=cast(dict[Literal["go", "java", "js"], list[Bounded]], verdicts),
    )


def load_sidecar(path: Path) -> Sidecar:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise SidecarError(f"{path}: invalid TOML: {e}") from e
    for key in data:
        if key != "sdk" and key not in TOP_LEVEL_KEYS:
            raise SidecarError(f"{path}: unknown key {key!r}")
    for key, value in data.items():
        if key == "sdk":
            continue
        if isinstance(value, dict) or (
            isinstance(value, list) and any(isinstance(v, dict) for v in value)
        ):
            raise SidecarError(
                f"{path}: {key!r} must not be a table; [sdk] is the only one"
            )
    if "sdk" in data and list(data)[-1] != "sdk":
        raise SidecarError(f"{path}: [sdk] must come after all top-level keys")
    sdk = _parse_sdk_table(path, data["sdk"]) if "sdk" in data else None
    raw = {k: v for k, v in data.items() if k != "sdk"}
    name = path.name.removesuffix(SIDECAR_SUFFIX)
    return Sidecar(fixture=path.with_name(name), raw=raw, sdk=sdk)


class CorpusKey(TypedDict):
    kid: str
    alg: str
    privateKey: str
    cert: str
    kas: Literal["km1", "km2"]


def kas_keys(root: Path = CORPUS_DIR) -> dict[str, CorpusKey]:
    """The stable KAS keys the corpus is encrypted to, keyed by kid."""
    entries = json.loads((root / "kas-keys.json").read_text())
    return {e["kid"]: cast(CorpusKey, e) for e in entries}


def fixtures(root: Path = CORPUS_DIR) -> list[Path]:
    return sorted(
        p
        for p in root.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.name not in NON_FIXTURES
        and not p.name.endswith(SIDECAR_SUFFIX)
    )


def _matches(e: Bounded, sdk_v: Semver | None, plat_v: Semver | None) -> bool:
    # An unresolved version is a branch build: newer than any bound, so
    # lower bounds hold and upper bounds do not.
    if sdk_v is None:
        if e.before is not None:
            return False
    else:
        if e.since is not None and sdk_v < e.since:
            return False
        if e.before is not None and sdk_v >= e.before:
            return False
    if plat_v is None:
        if e.platform_before is not None:
            return False
    else:
        if e.platform_since is not None and plat_v < e.platform_since:
            return False
        if e.platform_before is not None and plat_v >= e.platform_before:
            return False
    return True


def resolve_verdict(
    table: SdkTable,
    sdk: str,
    sdk_semver: Semver | None,
    platform_version: Semver | None,
) -> Verdict:
    if sdk not in SDK_NAMES:
        raise ValueError(f"unknown sdk {sdk!r}; expected one of {SDK_NAMES}")
    for entry in table.verdicts[cast(Literal["go", "java", "js"], sdk)]:
        if _matches(entry, sdk_semver, platform_version):
            return entry.verdict
    raise SidecarError(f"no verdict entry matches sdk {sdk}")


def platform_semver() -> Semver | None:
    tag = os.environ.get("PLATFORM_TAG")
    if tag:
        return _parse_semver(tag)
    return _parse_semver(os.environ.get("PLATFORM_VERSION", ""))


def classify_outcome(
    returncode: int, out: Path, expected_sha256: str | None
) -> Outcome:
    if returncode != 0:
        return "reject"
    if not out.is_file():
        return "wrong-plaintext"
    if expected_sha256 is None:
        return "decrypt"
    if output_sha256(out) == expected_sha256:
        return "decrypt"
    return "wrong-plaintext"


def output_sha256(out: Path) -> str | None:
    """Hex SHA-256 of the decrypt output file, or None when there is none."""
    if not out.is_file():
        return None
    with out.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def make_record(
    *,
    fixture: str,
    sdk: str,
    version: str,
    outcome: str,
    out: Path,
    sdk_semver: Semver | None = None,
    stderr_tail: str = "",
) -> dict[str, Any]:
    """One record-mode JSONL row. output_sha256 lets a later step check the bytes."""
    plat = platform_semver()
    return {
        "fixture": fixture,
        "sdk": sdk,
        "version": version,
        "sdk_semver": list(sdk_semver) if sdk_semver else None,
        "platform_tag": os.environ.get("PLATFORM_TAG"),
        "platform_version": os.environ.get("PLATFORM_VERSION"),
        "platform_semver": list(plat) if plat else None,
        "outcome": outcome,
        "output_sha256": output_sha256(out),
        "stderr_tail": stderr_tail,
    }


class DecryptHung(Exception):
    pass


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    # Signals only the session that start_new_session=True created for proc.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)  # NOSONAR


def run_decrypt(
    cmd: list[str], env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[bytes]:
    """Run a decrypt CLI; on timeout kill its whole process group."""
    proc = subprocess.Popen(
        cmd,
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        proc.communicate()
        raise DecryptHung(f"decrypt timed out after {timeout}s: {cmd}") from None
    except BaseException:
        _kill_group(proc)
        proc.communicate()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def read_manifest(fixture: Path) -> dict[str, Any] | None:
    """The TDF manifest, or None when the file is not a ZIP with a readable one."""
    try:
        with zipfile.ZipFile(fixture) as z:
            m = json.loads(z.read("0.manifest.json"))
    except OSError, KeyError, ValueError, zipfile.BadZipFile, NotImplementedError:
        return None
    return m if isinstance(m, dict) else None


def required_features(
    manifest: dict[str, Any] | None, keys: dict[str, CorpusKey]
) -> list[str]:
    """Feature names a decrypt of this manifest needs from the SDK and platform."""
    if manifest is None:
        return []
    need: list[str] = []
    enc = manifest.get("encryptionInformation")
    kaos = enc.get("keyAccess", []) if isinstance(enc, dict) else []
    for kao in kaos if isinstance(kaos, list) else []:
        if not isinstance(kao, dict):
            continue
        match kao.get("type"):
            case "ec-wrapped":
                need.append("ecwrap")
            case "mlkem-wrapped":
                need.append("mechanism-mlkem")
            case "hybrid-wrapped":
                alg = keys.get(str(kao.get("kid")), {}).get("alg", "")
                if alg == "hpqt:xwing":
                    need.append("mechanism-xwing")
                elif alg.startswith("hpqt:secp"):
                    need.append("mechanism-secpmlkem")
    return list(dict.fromkeys(need))


def _policy(manifest: dict[str, Any] | None) -> dict[str, Any]:
    try:
        enc = (manifest or {})["encryptionInformation"]
        policy = json.loads(base64.b64decode(enc["policy"]))
    except KeyError, TypeError, ValueError:
        return {}
    return policy if isinstance(policy, dict) else {}


def has_data_attributes(manifest: dict[str, Any] | None) -> bool:
    """True when the manifest's policy names data attributes."""
    try:
        return bool(_policy(manifest)["body"]["dataAttributes"])
    except KeyError, TypeError:
        return False


def policy_uuid(manifest: dict[str, Any] | None) -> str | None:
    """The manifest's policy UUID, which KAS records in its rewrap audit events."""
    uuid = _policy(manifest).get("uuid")
    return uuid if isinstance(uuid, str) else None


def assertion_verification_keys(
    raw: dict[str, Any], manifest: dict[str, Any] | None, root: Path = CORPUS_DIR
) -> dict[str, Any] | None:
    """The CLI verification-keys JSON built from a sidecar's assertion_keys.

    An entry ``id=path`` keys that assertion id; a bare path keys every assertion
    in the manifest. None when no keys are listed or no assertion id is known.
    """
    entries: list[tuple[str | None, str]] = []
    for v in raw.get("assertion_keys", []):
        aid, sep, path = v.partition("=")
        entries.append((aid, path) if sep else (None, v))
    ids: list[str] = []
    if manifest is not None:
        ids = [a["id"] for a in manifest.get("assertions") or [] if "id" in a]
    out: dict[str, dict[str, str]] = {}
    for aid, path in entries:
        pem = (root / path).read_text()
        pub = serialization.load_pem_public_key(pem.encode())
        alg = "RS256" if isinstance(pub, rsa.RSAPublicKey) else "ES256"
        for i in [aid] if aid else ids:
            out.setdefault(i, {"alg": alg, "key": pem})
    return {"keys": out} if out else None


def append_record(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line; safe against concurrent xdist workers."""
    line = (json.dumps(record, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line)
    finally:
        os.close(fd)
