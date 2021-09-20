"""Utility functions for the cryptography module."""

import logging

from cryptography.hazmat.backends.openssl.rsa import _RSAPublicKey
from cryptography.hazmat.backends.openssl.rsa import _RSAPrivateKey

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from tdf3_kas_core.errors import CryptoError

logger = logging.getLogger(__name__)


def assure_public_key(public_key):
    """Assure that the public key is an _RSAPublicKey."""
    if isinstance(public_key, _RSAPublicKey):
        return public_key
    elif isinstance(public_key, _RSAPrivateKey):
        raise CryptoError("Public key expected in assure_public_key")
    else:
        try:
            # Assume the public key is a PEM encoded bytes. Try to construct
            # a public key. If it fails error will be caught.
            return serialization.load_pem_public_key(
                public_key, backend=default_backend()
            )
        except Exception as e:
            raise CryptoError("Key error") from e


def assure_private_key(private_key):
    """Assure that the private key is an _RSAPrivateKey."""
    if isinstance(private_key, _RSAPrivateKey):
        return private_key
    elif isinstance(private_key, _RSAPublicKey):
        raise CryptoError("Private key expected in assure_private_key")
    else:
        try:
            # Assume the private key is a PEM encoded bytes. Try to construct
            # a private key. If it isn't PEM then this will raise an error.
            return serialization.load_pem_private_key(
                private_key, backend=default_backend(), password=None
            )
        except Exception as e:
            raise CryptoError("Key Error") from e
