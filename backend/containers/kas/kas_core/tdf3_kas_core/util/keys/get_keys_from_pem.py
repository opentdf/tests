"""Utility functions to get public and private keys from pem strings."""

import logging

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography import x509

from tdf3_kas_core.errors import KeyNotFoundError

logger = logging.getLogger(__name__)


def get_public_key_from_pem(pem):
    """Deserialize a public key from a pem string."""
    try:
        try:
            logger.debug("Attempting to returndeserialize key")
            return serialization.load_pem_public_key(pem, backend=default_backend())
        except Exception:
            logger.debug("Deserialization failed; loading cert")
            cert = x509.load_pem_x509_certificate(pem, default_backend())
            logger.debug("Cert check passed, returning key")
            return cert.public_key()

    except Exception as err:
        raise KeyNotFoundError(
            "KEY File not found, or exception getting public key from pem."
        ) from err


def get_private_key_from_pem(pem):
    """Deserialize a private key from a PEM string."""
    try:
        logger.debug("Attempting to return deserialized key")
        return serialization.load_pem_private_key(
            pem, password=None, backend=default_backend()
        )

    except Exception as e:
        raise KeyNotFoundError(
            "KEY File not found, or exception getting private key from pem."
        ) from e
