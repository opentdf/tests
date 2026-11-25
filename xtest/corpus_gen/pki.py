"""RS256 assertion signers and the x5c test chain, kept in generator scratch.

Keys and certificates are generated once and reused, so re-running `write`
keeps the published public keys stable.
"""

import datetime
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT_CN = "OpenTDF Corpus Test Root CA"
INTERMEDIATE_CN = "OpenTDF Corpus Test Intermediate CA"
LEAF_CN = "OpenTDF Corpus Test Assertion Signer"


@dataclass(frozen=True)
class X5cChain:
    leaf_key: str  # PKCS#8 PEM
    leaf: str
    intermediate: str
    ca: str


def _key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _write_atomic(path: Path, data: bytes, mode: int) -> None:
    """Write via a temporary file and rename, so path is never left partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _new_key(path: Path) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _write_atomic(path, _key_pem(key), 0o600)
    return key


def _key_matches(key_pem: bytes, cert: x509.Certificate) -> bool:
    key = serialization.load_pem_private_key(key_pem, password=None)
    return key.public_key() == cert.public_key()


def signer_key(pki: Path, name: str) -> str:
    """A fixture's own RS256 signing key (PKCS#8 PEM), created on first use."""
    path = pki / "signers" / f"{name}.key.pem"
    if not path.exists():
        _new_key(path)
    return path.read_text()


def public_pem(private_pem: str) -> str:
    key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(
    cn: str,
    key: rsa.RSAPrivateKey,
    issuer_cn: str,
    issuer_key: rsa.RSAPrivateKey,
    path_length: int | None,
    ca: bool,
) -> x509.Certificate:
    now = datetime.datetime.now(datetime.UTC)
    usage = x509.KeyUsage(
        digital_signature=not ca,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=ca,
        crl_sign=ca,
        encipher_only=False,
        decipher_only=False,
    )
    return (
        x509.CertificateBuilder()
        .subject_name(_name(cn))
        .issuer_name(_name(issuer_cn))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=36500))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=path_length), True)
        .add_extension(usage, True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
            False,
        )
        .sign(issuer_key, hashes.SHA256())
    )


def _pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def forged_signer(pki: Path, subject: x509.Name) -> tuple[str, str]:
    """(key PEM, cert PEM) of a self-signed RS256 certificate for ``subject``,
    outside the test chain. Created on first use, and again if ``subject`` changes
    or the cached key is not the certificate's (an interrupted rebuild)."""
    key_path, cert_path = pki / "forged.key.pem", pki / "forged.pem"
    if key_path.exists() and cert_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        if cert.subject == subject and _key_matches(key_path.read_bytes(), cert):
            return key_path.read_text(), cert_path.read_text()
    key = _new_key(key_path)
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=36500))
        .sign(key, hashes.SHA256())
    )
    _write_atomic(cert_path, _pem(cert).encode(), 0o644)
    return key_path.read_text(), cert_path.read_text()


def _one_generation(files: dict[str, Path], leaf_key: Path) -> bool:
    """Whether the cached chain exists and comes from one generation: each
    certificate signed by the next, and leaf_key the leaf's key."""
    if not all(p.exists() for p in [*files.values(), leaf_key]):
        return False
    certs = {
        n: x509.load_pem_x509_certificate(p.read_bytes()) for n, p in files.items()
    }
    try:
        certs["leaf"].verify_directly_issued_by(certs["intermediate"])
        certs["intermediate"].verify_directly_issued_by(certs["ca"])
    except InvalidSignature:
        return False
    return _key_matches(leaf_key.read_bytes(), certs["leaf"])


def x5c_chain(pki: Path) -> X5cChain:
    """Root CA -> intermediate -> RS256 leaf, created together on first use, and
    again if the cached files are not from one generation (an interrupted rebuild)."""
    files = {n: pki / f"{n}.pem" for n in ("ca", "intermediate", "leaf")}
    leaf_key = pki / "leaf.key.pem"
    if not _one_generation(files, leaf_key):
        root_k = _new_key(pki / "ca.key.pem")
        inter_k = _new_key(pki / "intermediate.key.pem")
        leaf_k = _new_key(leaf_key)
        certs = {
            "ca": _cert(ROOT_CN, root_k, ROOT_CN, root_k, 1, True),
            "intermediate": _cert(INTERMEDIATE_CN, inter_k, ROOT_CN, root_k, 0, True),
            "leaf": _cert(LEAF_CN, leaf_k, INTERMEDIATE_CN, inter_k, None, False),
        }
        for n, cert in certs.items():
            _write_atomic(files[n], _pem(cert).encode(), 0o644)
    return X5cChain(
        leaf_key=leaf_key.read_text(),
        leaf=files["leaf"].read_text(),
        intermediate=files["intermediate"].read_text(),
        ca=files["ca"].read_text(),
    )
