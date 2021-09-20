"""Utility functions for the cryptography module."""

import logging

from cryptography.hazmat.backends.openssl.rsa import _RSAPublicKey
from cryptography.hazmat.backends.openssl.rsa import _RSAPrivateKey
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePublicKey
from cryptography.hazmat.backends.openssl.ec import _EllipticCurvePrivateKey

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography import x509

from src.errors import CryptoError

logger = logging.getLogger(__name__)


def assure_public_key(public_key):
    """Assure that the public key is an _RSAPublicKey."""
    logger.debug("public key = %s", public_key)

    if isinstance(public_key, _RSAPublicKey):
        logger.debug("Public key is a RSAPublicKey")
        return public_key

    elif isinstance(public_key, _EllipticCurvePublicKey):
        logger.debug("Public key is an EllipticCurvePublicKey")
        return public_key

    elif isinstance(public_key, _RSAPrivateKey):
        logger.error("Public key is not a RSA private key")
        raise CryptoError("Public key expected in assure_public_key")

    elif isinstance(public_key, _EllipticCurvePrivateKey):
        logger.error("Public key is not an EllipticCurve private key")
        raise CryptoError("Public key expected in assure_public_key")

    else:
        logger.debug("Public key type is unknown")
        try:
            if isinstance(public_key, str):
                public_key = str.encode(public_key)
                logger.debug("Public key type was string")

            if b"-----BEGIN CERTIFICATE-----" in public_key:
                logger.debug("Public key appears to be an x509 certificate")
                logger.debug("Certificate = %s", public_key)
                cert = x509.load_pem_x509_certificate(public_key, default_backend())
                return cert.public_key()

            # Assume the public key is a PEM encoded bytes. Try to construct
            # a public key. If it fails error will be caught.
            logger.debug("Attempting to deserialize public key as PEM bytes")
            return serialization.load_pem_public_key(
                public_key, backend=default_backend()
            )
        except Exception as e:
            raise CryptoError("Key error") from e


def assure_private_key(private_key):
    """Assure that the private key is an _RSAPrivateKey."""
    if isinstance(private_key, _RSAPrivateKey):
        logger.debug("Private key is a RSAPrivateKey")
        return private_key

    elif isinstance(private_key, _EllipticCurvePrivateKey):
        logger.debug("Private key is an EllipticCurvePrivateKey")
        return private_key

    elif isinstance(private_key, _RSAPublicKey):
        logger.error("Private key is not a RSA public key")
        raise CryptoError("Private key expected in assure_private_key")

    elif isinstance(private_key, _EllipticCurvePublicKey):
        logger.error("Private key is not an EllipticCurve public key")
        raise CryptoError("Private key expected in assure_private_key")

    else:
        logger.debug("Private key type is unknown.")
        try:
            if isinstance(private_key, str):
                private_key = str.encode(private_key)
                logger.debug("Private key was string.")
            # Assume the private key is a PEM encoded bytes. Try to construct
            # a private key. If it isn't PEM then this will raise an error.
            logger.debug("Attempting to deserialize private key as PEM bytes")
            return serialization.load_pem_private_key(
                private_key, backend=default_backend(), password=None
            )
        except Exception as e:
            raise CryptoError("Key Error") from e
