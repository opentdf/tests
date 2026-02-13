"""Cryptographic key generation utilities."""

import json
import secrets
import subprocess
from pathlib import Path


def generate_root_key() -> str:
    """Generate a random 256-bit root key as hex string."""
    return secrets.token_hex(32)


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
        xtest_root: Root directory of xtest (contains xtest/extra-keys.json)
        platform_dir: Platform source directory

    Returns:
        List of key configurations to add to cryptoProvider.standard.keys
    """
    extra_keys_file = xtest_root / "xtest" / "extra-keys.json"
    if not extra_keys_file.exists():
        return []

    with open(extra_keys_file) as f:
        extra_keys = json.load(f)

    keys_config = []
    for key_entry in extra_keys:
        kid = key_entry.get("kid", "")
        alg = key_entry.get("alg", "")
        private_key = key_entry.get("privateKey", "")
        cert = key_entry.get("cert", "")

        if not all([kid, alg, private_key, cert]):
            continue

        # Map algorithm to platform format
        if alg == "rsa:2048":
            platform_alg = "rsa:2048"
        elif alg == "ec:secp256r1":
            platform_alg = "ec:secp256r1"
        else:
            continue

        # Write key files to platform directory
        private_path = platform_dir / f"{kid}-private.pem"
        cert_path = platform_dir / f"{kid}-cert.pem"

        private_path.write_text(private_key)
        cert_path.write_text(cert)

        keys_config.append(
            {
                "kid": kid,
                "alg": platform_alg,
                "private": f"{kid}-private.pem",
                "cert": f"{kid}-cert.pem",
            }
        )

    return keys_config


def get_golden_keyring_entries() -> list[dict]:
    """Get keyring entries for golden keys.

    Returns:
        List of keyring entries to add to services.kas.keyring
    """
    return [
        {"kid": "golden-r1", "alg": "rsa:2048", "legacy": True},
    ]
