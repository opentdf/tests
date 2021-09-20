"""Utitity to generate keys."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def generate_rsa_keys():
    """Create public and private keys for attributes."""
    key = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )

    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return {
        public_key: public_key.decode("utf-8"),
        private_key: private_key.decode("utf-8"),
    }
