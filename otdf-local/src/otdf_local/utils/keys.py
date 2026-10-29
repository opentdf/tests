"""Cryptographic key generation utilities."""

import json
import os
import re
import secrets
import subprocess
from pathlib import Path

from otdf_local.utils.console import print_warning


def generate_root_key() -> str:
    """Generate a random 256-bit root key as hex string."""
    return secrets.token_hex(32)


def validate_alg(alg: str) -> bool:
    """Validate that the alg is a supported crypto mechanism."""
    supported_algs = {
        "ec:secp256r1",
        "ec:secp384r1",
        "ec:secp521r1",
        "rsa:2048",
        "rsa:4096",
    }
    return alg in supported_algs


# kids name files in the platform dir, so no `/`, `.`, or leading `-`.
_KID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")


def validate_kid(kid: str) -> bool:
    """Validate that the kid is 1-32 of `[A-Za-z0-9_-]`, starting alphanumeric."""
    return _KID_PATTERN.fullmatch(kid) is not None


def generate_rsa_keypair(key_dir: Path, name: str = "kas") -> tuple[Path, Path]:
    """Generate an RSA keypair for KAS.

    Args:
        key_dir: Directory to store keys
        name: Base name for key files

    Returns:
        Tuple of (private_key_path, public_key_path)
    """
    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = key_dir / f"{name}-private.pem"
    public_key = key_dir / f"{name}-cert.pem"

    # Generate private key
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-out",
            str(private_key),
            "-pkeyopt",
            "rsa_keygen_bits:2048",
        ],
        check=True,
        capture_output=True,
    )
    private_key.chmod(0o600)

    # Generate self-signed certificate
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-x509",
            "-key",
            str(private_key),
            "-out",
            str(public_key),
            "-days",
            "365",
            "-subj",
            "/CN=kas/O=OpenTDF",
        ],
        check=True,
        capture_output=True,
    )

    return private_key, public_key


def generate_ec_keypair(key_dir: Path, name: str = "kas-ec") -> tuple[Path, Path]:
    """Generate an EC keypair for KAS.

    Args:
        key_dir: Directory to store keys
        name: Base name for key files

    Returns:
        Tuple of (private_key_path, public_key_path)
    """
    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = key_dir / f"{name}-private.pem"
    public_key = key_dir / f"{name}-cert.pem"

    # Generate EC private key
    subprocess.run(
        [
            "openssl",
            "ecparam",
            "-name",
            "prime256v1",
            "-genkey",
            "-noout",
            "-out",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )
    private_key.chmod(0o600)

    # Generate self-signed certificate
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-x509",
            "-key",
            str(private_key),
            "-out",
            str(public_key),
            "-days",
            "365",
            "-subj",
            "/CN=kas-ec/O=OpenTDF",
        ],
        check=True,
        capture_output=True,
    )

    return private_key, public_key


def ensure_keys_exist(key_dir: Path, force: bool = False) -> bool:
    """Ensure all required keys exist, generating if needed.

    Args:
        key_dir: Directory for key storage
        force: If True, regenerate keys even if they exist

    Returns:
        True if keys were generated, False if they already existed
    """
    rsa_private = key_dir / "kas-private.pem"
    ec_private = key_dir / "kas-ec-private.pem"

    if not force and rsa_private.exists() and ec_private.exists():
        return False

    generate_rsa_keypair(key_dir, "kas")
    generate_ec_keypair(key_dir, "kas-ec")
    return True


def setup_golden_keys(
    xtest_root: Path,
    platform_dir: Path,
) -> list[dict]:
    """Extract and install golden keys for legacy TDF decryption.

    Reads extra-keys.json from the xtest directory and copies the key files
    to the platform directory for use by the platform service.

    Args:
        xtest_root: The xtest directory (contains extra-keys.json)
        platform_dir: Platform source directory

    Returns:
        List of key configurations to add to cryptoProvider.standard.keys
    """
    extra_keys_file = xtest_root / "extra-keys.json"
    if not extra_keys_file.exists():
        # Not an error -- a bare xtest_root has no fixtures -- but without
        # golden keys test_legacy.py fails much later, as "cipher: message
        # authentication failed", with nothing pointing back here.
        print_warning(
            f"No {extra_keys_file}; golden keys not configured, so legacy "
            "golden TDFs will not decrypt."
        )
        return []

    # Every entry is validated before any file is written, so a bad entry
    # leaves no partial set of key files behind.
    entries = _read_extra_keys(extra_keys_file)

    keys_config = []
    for kid, alg, private_key, cert in entries:
        private_path = platform_dir / f"{kid}-private.pem"
        cert_path = platform_dir / f"{kid}-cert.pem"

        _write_owner_only(private_path, private_key)
        cert_path.write_text(cert, encoding="utf-8")

        keys_config.append(
            {
                "kid": kid,
                "alg": alg,
                "private": f"{kid}-private.pem",
                "cert": f"{kid}-cert.pem",
            }
        )

    return keys_config


_EXTRA_KEY_FIELDS = ("kid", "alg", "privateKey", "cert")


def _read_extra_keys(path: Path) -> list[tuple[str, str, str, str]]:
    """The (kid, alg, privateKey, cert) of each entry in `path`.

    Every problem is a ValueError naming the file, which is what
    `PlatformService._preflight` reports as a start error.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e
    if not isinstance(raw, list):
        raise ValueError(f"{path} must hold a JSON array of keys")

    entries = []
    # Case-folded: on a case-insensitive filesystem (macOS by default),
    # `Golden-r1` and `golden-r1` would write the same key files.
    seen_kids: set[str] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: entry {i} is not a JSON object")
        missing = [
            field
            for field in _EXTRA_KEY_FIELDS
            if not isinstance(entry.get(field), str) or not entry[field]
        ]
        if missing:
            raise ValueError(
                f"{path}: entry {i} needs non-empty string {', '.join(missing)}"
            )
        kid, alg, private_key, cert = (entry[field] for field in _EXTRA_KEY_FIELDS)
        if not validate_kid(kid):
            raise ValueError(f"{path}: invalid kid {kid!r}")
        if not validate_alg(alg):
            raise ValueError(f"{path}: invalid alg {alg!r} for kid {kid}")
        if kid.casefold() in seen_kids:
            raise ValueError(
                f"{path}: kid {kid!r} repeats an earlier kid (ignoring case)"
            )
        seen_kids.add(kid.casefold())
        entries.append((kid, alg, private_key, cert))
    return entries


def _write_owner_only(path: Path, content: str) -> None:
    """Write `path` so that only its owner can ever read the content."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        # The mode above applies only on creation; an existing file keeps its
        # own, so narrow it before any content goes in.
        os.fchmod(f.fileno(), 0o600)
        f.write(content)


def get_golden_keyring_entries() -> list[dict]:
    """Get keyring entries for golden keys.

    Returns:
        List of keyring entries to add to services.kas.keyring
    """
    return [
        {"kid": "golden-r1", "alg": "rsa:2048", "legacy": True},
    ]
