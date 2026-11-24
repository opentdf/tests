"""Static TDF corpus: sidecar parsing, per-SDK verdict resolution, decrypt helpers.

Pure and offline: no platform or SDK imports, so the units tier can use it.
"""

import contextlib
import hashlib
import os
import re
import signal
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

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
    with out.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if digest == expected_sha256:
        return "decrypt"
    return "wrong-plaintext"


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
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
