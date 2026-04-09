"""Cryptographic key generation utilities."""

import json
import logging
import os
import platform
import secrets
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


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


_KEYCLOAK_KEY_FILES = [
    "keycloak-ca.pem",
    "keycloak-ca-private.pem",
    "localhost.crt",
    "localhost.key",
    "sampleuser.crt",
    "sampleuser.key",
    "ca.p12",
    "ca.jks",
]


def generate_ca_keypair(keys_dir: Path) -> tuple[Path, Path]:
    """Generate a self-signed CA keypair for Keycloak TLS.

    Args:
        keys_dir: Directory to store keys

    Returns:
        Tuple of (ca_private_key_path, ca_cert_path)
    """
    keys_dir.mkdir(parents=True, exist_ok=True)
    ca_key = keys_dir / "keycloak-ca-private.pem"
    ca_cert = keys_dir / "keycloak-ca.pem"

    subprocess.run(
        [
            "openssl", "req", "-x509", "-nodes",
            "-newkey", "RSA:2048",
            "-subj", "/CN=ca",
            "-keyout", str(ca_key),
            "-out", str(ca_cert),
            "-days", "365",
        ],
        check=True,
        capture_output=True,
    )
    ca_key.chmod(0o600)

    return ca_key, ca_cert


def generate_localhost_cert(keys_dir: Path) -> tuple[Path, Path]:
    """Generate a localhost certificate signed by the CA.

    Creates a server cert with SAN DNS:localhost,IP:127.0.0.1
    suitable for Keycloak HTTPS.

    Args:
        keys_dir: Directory containing CA keys and to store output

    Returns:
        Tuple of (key_path, cert_path)
    """
    ca_key = keys_dir / "keycloak-ca-private.pem"
    ca_cert = keys_dir / "keycloak-ca.pem"
    server_key = keys_dir / "localhost.key"
    server_cert = keys_dir / "localhost.crt"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        csr_path = tmp / "localhost.req"
        san_conf = tmp / "sanX509.conf"
        req_conf = tmp / "req.conf"

        san_conf.write_text("subjectAltName=DNS:localhost,IP:127.0.0.1")
        req_conf.write_text(
            "[req]\n"
            "distinguished_name=req_distinguished_name\n"
            "[req_distinguished_name]\n"
            "[alt_names]\n"
            "DNS.1=localhost\n"
            "IP.1=127.0.0.1\n"
        )

        # Generate CSR + key
        subprocess.run(
            [
                "openssl", "req", "-new", "-nodes",
                "-newkey", "rsa:2048",
                "-keyout", str(server_key),
                "-out", str(csr_path),
                "-batch",
                "-subj", "/CN=localhost",
                "-config", str(req_conf),
            ],
            check=True,
            capture_output=True,
        )
        server_key.chmod(0o600)

        # Sign with CA
        subprocess.run(
            [
                "openssl", "x509", "-req",
                "-in", str(csr_path),
                "-CA", str(ca_cert),
                "-CAkey", str(ca_key),
                "-CAcreateserial",
                "-out", str(server_cert),
                "-days", "3650",
                "-sha256",
                "-extfile", str(san_conf),
            ],
            check=True,
            capture_output=True,
        )

    # Clean up CA serial file if created in keys_dir
    serial_file = keys_dir / "keycloak-ca.srl"
    if serial_file.exists():
        serial_file.unlink()

    return server_key, server_cert


def generate_sampleuser_cert(keys_dir: Path) -> tuple[Path, Path]:
    """Generate a sample user client certificate signed by the CA.

    Args:
        keys_dir: Directory containing CA keys and to store output

    Returns:
        Tuple of (key_path, cert_path)
    """
    ca_key = keys_dir / "keycloak-ca-private.pem"
    ca_cert = keys_dir / "keycloak-ca.pem"
    user_key = keys_dir / "sampleuser.key"
    user_cert = keys_dir / "sampleuser.crt"

    with tempfile.TemporaryDirectory() as tmpdir:
        csr_path = Path(tmpdir) / "sampleuser.req"

        subprocess.run(
            [
                "openssl", "req", "-new", "-nodes",
                "-newkey", "rsa:2048",
                "-keyout", str(user_key),
                "-out", str(csr_path),
                "-batch",
                "-subj", "/CN=sampleuser",
            ],
            check=True,
            capture_output=True,
        )
        user_key.chmod(0o600)

        subprocess.run(
            [
                "openssl", "x509", "-req",
                "-in", str(csr_path),
                "-CA", str(ca_cert),
                "-CAkey", str(ca_key),
                "-CAcreateserial",
                "-out", str(user_cert),
                "-days", "3650",
            ],
            check=True,
            capture_output=True,
        )

    serial_file = keys_dir / "keycloak-ca.srl"
    if serial_file.exists():
        serial_file.unlink()

    return user_key, user_cert


def _get_java_opts_for_docker() -> list[str]:
    """Get JAVA_TOOL_OPTIONS env args for Docker keytool.

    Works around SIGILL on Apple M4 chips by disabling SVE.
    """
    if platform.machine() != "arm64":
        return []
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and "M4" in result.stdout:
            return ["-e", "JAVA_TOOL_OPTIONS=-XX:UseSVE=0"]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def _get_keycloak_image(compose_file: Path | None) -> str:
    """Extract the Keycloak image from a docker-compose file, or use default."""
    default = "keycloak/keycloak:25.0"
    if compose_file is None or not compose_file.exists():
        return default
    try:
        text = compose_file.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("image:") and "keycloak" in stripped:
                return stripped.split(":", 1)[1].strip()
    except OSError:
        pass
    return default


def generate_ca_stores(
    keys_dir: Path,
    compose_file: Path | None = None,
) -> tuple[Path, Path]:
    """Generate PKCS12 and JKS keystores from the CA cert.

    Args:
        keys_dir: Directory containing CA keys
        compose_file: Optional docker-compose.yaml to extract keycloak image version

    Returns:
        Tuple of (p12_path, jks_path)
    """
    ca_key = keys_dir / "keycloak-ca-private.pem"
    ca_cert = keys_dir / "keycloak-ca.pem"
    p12_path = keys_dir / "ca.p12"
    jks_path = keys_dir / "ca.jks"

    # Generate PKCS12
    subprocess.run(
        [
            "openssl", "pkcs12", "-export",
            "-in", str(ca_cert),
            "-inkey", str(ca_key),
            "-out", str(p12_path),
            "-nodes",
            "-passout", "pass:password",
        ],
        check=True,
        capture_output=True,
    )

    # Generate JKS via Docker keytool
    keycloak_image = _get_keycloak_image(compose_file)
    java_opts = _get_java_opts_for_docker()
    uid_gid = f"{os.getuid()}:{os.getgid()}"

    cmd = [
        "docker", "run", "--rm",
        *java_opts,
        "-v", f"{keys_dir.resolve()}:/keys",
        "--entrypoint", "keytool",
        "--user", uid_gid,
        keycloak_image,
        "-importkeystore",
        "-srckeystore", "/keys/ca.p12",
        "-srcstoretype", "PKCS12",
        "-destkeystore", "/keys/ca.jks",
        "-deststoretype", "JKS",
        "-srcstorepass", "password",
        "-deststorepass", "password",
        "-noprompt",
    ]

    subprocess.run(cmd, check=True, capture_output=True)

    return p12_path, jks_path


def ensure_keycloak_keys(
    keys_dir: Path,
    compose_file: Path | None = None,
    force: bool = False,
) -> bool:
    """Ensure all Keycloak TLS keys exist, generating if needed.

    All keycloak keys are regenerated together since the certs form a
    CA chain (localhost.crt and sampleuser.crt are signed by the CA).

    Args:
        keys_dir: Directory for key storage
        compose_file: Optional docker-compose.yaml for keycloak image version
        force: If True, regenerate all keys even if they exist

    Returns:
        True if keys were generated, False if they already existed
    """
    if not force and all((keys_dir / f).exists() for f in _KEYCLOAK_KEY_FILES):
        return False

    logger.info("Generating Keycloak TLS keys in %s", keys_dir)
    generate_ca_keypair(keys_dir)
    generate_localhost_cert(keys_dir)
    generate_sampleuser_cert(keys_dir)
    generate_ca_stores(keys_dir, compose_file)
    return True


def ensure_all_temp_keys(
    platform_dir: Path,
    keys_dir: Path,
    compose_file: Path | None = None,
    force: bool = False,
) -> bool:
    """Ensure all temporary keys exist for running the platform.

    KAS keys are generated per-platform-dir (referenced by relative paths
    in the platform config). Keycloak TLS keys are generated in a shared
    keys_dir so they can be reused across platform variants.

    Args:
        platform_dir: Platform source directory (for KAS keys)
        keys_dir: Shared directory for Keycloak TLS keys
        compose_file: Optional docker-compose.yaml for keycloak image version
        force: If True, regenerate all keys

    Returns:
        True if any keys were generated
    """
    kas_generated = ensure_keys_exist(platform_dir, force)
    kc_generated = ensure_keycloak_keys(keys_dir, compose_file, force)
    return kas_generated or kc_generated


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

        # Write key files to platform directory
        private_path = platform_dir / f"{kid}-private.pem"
        cert_path = platform_dir / f"{kid}-cert.pem"

        private_path.write_text(private_key)
        private_path.chmod(0o600)
        cert_path.write_text(cert)

        keys_config.append(
            {
                "kid": kid,
                "alg": alg,
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
