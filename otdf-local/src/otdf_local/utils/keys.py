"""Cryptographic key generation utilities."""

import json
import os
import secrets
import subprocess
from pathlib import Path


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


def validate_kid(kid: str) -> bool:
    """Validate that the kid is a non-empty, less than 33 characters, and alphanumeric."""
    return 0 < len(kid) < 33 and kid.isalnum()


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


def generate_localhost_cert(key_dir: Path) -> tuple[Path, Path]:
    """Generate the TLS cert pair Keycloak mounts at /etc/x509/tls/.

    Mirrors the localhost cert flow in the platform's init-temp-keys.sh:
    self-signed CA → CSR with SAN → signed leaf cert. Keycloak rejects a
    plain self-signed leaf because it pins the SAN to localhost+127.0.0.1.
    """
    key_dir.mkdir(parents=True, exist_ok=True)
    ca_key = key_dir / "keycloak-ca-private.pem"
    ca_cert = key_dir / "keycloak-ca.pem"
    leaf_key = key_dir / "localhost.key"
    leaf_csr = key_dir / "localhost.req"
    leaf_cert = key_dir / "localhost.crt"
    san_conf = key_dir / "sanX509.conf"
    req_conf = key_dir / "req.conf"

    san_conf.write_text("subjectAltName=DNS:localhost,IP:127.0.0.1")
    req_conf.write_text(
        "[req]\n"
        "distinguished_name=req_distinguished_name\n"
        "[req_distinguished_name]\n"
        "[alt_names]\n"
        "DNS.1=localhost\n"
        "IP.1=127.0.0.1"
    )

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-newkey",
            "RSA:2048",
            "-subj",
            "/CN=ca",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_cert),
            "-days",
            "365",
        ],
        check=True,
        capture_output=True,
    )
    ca_key.chmod(0o600)
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(leaf_key),
            "-out",
            str(leaf_csr),
            "-batch",
            "-subj",
            "/CN=localhost",
            "-config",
            str(req_conf),
        ],
        check=True,
        capture_output=True,
    )
    leaf_key.chmod(0o600)
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(leaf_csr),
            "-CA",
            str(ca_cert),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(leaf_cert),
            "-days",
            "3650",
            "-sha256",
            "-extfile",
            str(san_conf),
        ],
        check=True,
        capture_output=True,
    )

    return leaf_key, leaf_cert


def generate_ca_jks(key_dir: Path, password: str = "password") -> Path:
    """Convert the keycloak CA into the JKS truststore Keycloak mounts.

    Uses keytool inside the keycloak/keycloak:25.0 image so we don't need a
    local JDK — docker is already a hard dependency for the test env.
    Requires generate_localhost_cert() to have run first.
    """
    ca_key = key_dir / "keycloak-ca-private.pem"
    ca_cert = key_dir / "keycloak-ca.pem"
    if not ca_key.exists() or not ca_cert.exists():
        raise FileNotFoundError(
            f"CA files missing in {key_dir}; call generate_localhost_cert() first"
        )
    p12 = key_dir / "ca.p12"
    jks = key_dir / "ca.jks"

    subprocess.run(
        [
            "openssl",
            "pkcs12",
            "-export",
            "-in",
            str(ca_cert),
            "-inkey",
            str(ca_key),
            "-out",
            str(p12),
            "-nodes",
            "-passout",
            f"pass:{password}",
        ],
        check=True,
        capture_output=True,
    )

    # keytool -importkeystore via the keycloak image (matches init-temp-keys.sh)
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{key_dir.resolve()}:/keys",
            "--entrypoint",
            "keytool",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "keycloak/keycloak:25.0",
            "-importkeystore",
            "-srckeystore",
            "/keys/ca.p12",
            "-srcstoretype",
            "PKCS12",
            "-destkeystore",
            "/keys/ca.jks",
            "-deststoretype",
            "JKS",
            "-srcstorepass",
            password,
            "-deststorepass",
            password,
            "-noprompt",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"keytool failed converting PKCS12 → JKS:\n{result.stderr}\n"
            "Ensure Docker is running and `keycloak/keycloak:25.0` is pullable."
        )
    return jks


def ensure_keys_exist(key_dir: Path, force: bool = False) -> bool:
    """Ensure all required keys exist, generating if needed.

    Generates the full bootstrap bundle the platform + Keycloak need:
    KAS RSA/EC keypairs, the localhost TLS cert pair, and the ca.jks
    truststore. PQC keys (ML-KEM, X-Wing) are not generated here — those
    are provisioned at test time via the key-management API.

    Args:
        key_dir: Directory for key storage
        force: If True, regenerate keys even if they exist

    Returns:
        True if any keys were generated, False if everything already existed
    """
    rsa_private = key_dir / "kas-private.pem"
    ec_private = key_dir / "kas-ec-private.pem"
    localhost_key = key_dir / "localhost.key"
    ca_jks = key_dir / "ca.jks"

    if (
        not force
        and rsa_private.exists()
        and ec_private.exists()
        and localhost_key.exists()
        and ca_jks.exists()
    ):
        return False

    if force or not rsa_private.exists():
        generate_rsa_keypair(key_dir, "kas")
    if force or not ec_private.exists():
        generate_ec_keypair(key_dir, "kas-ec")
    if force or not localhost_key.exists():
        generate_localhost_cert(key_dir)
    if force or not ca_jks.exists():
        generate_ca_jks(key_dir)
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
        if not validate_kid(kid):
            raise ValueError(f"Invalid kid in extra-keys.json: {kid}")
        alg = key_entry.get("alg", "")
        if not validate_alg(alg):
            raise ValueError(f"Invalid alg in extra-keys.json for kid {kid}: {alg}")
        private_key = key_entry.get("privateKey", "")

        cert = key_entry.get("cert", "")

        if not all([kid, alg, private_key, cert]):
            raise ValueError(
                f"Missing required fields in extra-keys.json for kid: {kid}"
            )

        # Write key files into the target directory (platform_dir for legacy
        # single-instance, or the per-instance keys dir for multi-instance).
        platform_dir.mkdir(parents=True, exist_ok=True)
        private_path = platform_dir / f"{kid}-private.pem"
        cert_path = platform_dir / f"{kid}-cert.pem"

        private_path.write_text(private_key)
        private_path.chmod(0o600)
        cert_path.write_text(cert)

        # Use absolute paths so the platform binary finds them regardless of
        # its working directory (worktree in multi-instance mode).
        keys_config.append(
            {
                "kid": kid,
                "alg": alg,
                "private": str(private_path.resolve()),
                "cert": str(cert_path.resolve()),
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
