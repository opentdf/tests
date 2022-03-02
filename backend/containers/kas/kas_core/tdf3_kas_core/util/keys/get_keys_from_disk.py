"""Utility functions to get public and private keys from files on disk.

NOTE - This code could be a lot DRYer if it utilized the get_keys_from_pem
functions.  Future optimization, deferred.
"""

import os
import logging

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography import x509

from tdf3_kas_core.errors import KeyNotFoundError

logger = logging.getLogger(__name__)


def get_public_key_from_disk(path, as_pem=False):
    """Get a public key from disk.

    The path string is absolute.

    If path=='test' then produces an insecure but representative key
    that pairs with the private 'test' or "test_alt" key.
    """
    logger.info("Getting public key from disk with path = %s", path)

    curr_dir = os.path.dirname(__file__)
    if path == "test":
        path = os.path.join(curr_dir, "./keys_for_tests/rsa_public.pem")

    elif path == "test_alt":
        path = os.path.join(curr_dir, "./keys_for_tests/rsa_public_alt.pem")

    logger.debug("Key file final path = %s", path)

    try:
        with open(path, "rb") as key_file:
            pem_data = key_file.read()
            if as_pem:
                logger.debug("Key returned as PEM encoded string")
                return pem_data
            else:
                try:
                    logger.debug("Attempting to return deserialize key")
                    return serialization.load_pem_public_key(
                        pem_data, backend=default_backend()
                    )
                except Exception:
                    logger.debug("Deserialization failed; loading cert")
                    cert = x509.load_pem_x509_certificate(pem_data, default_backend())
                    logger.debug("Cert check passed, returning key")
                    return cert.public_key()
    except Exception as err:
        logger.exception(err)
        raise KeyNotFoundError("public key file not found")


def get_private_key_from_disk(path, as_pem=False):
    """Get a private key from disk.

    The path string is absolute.

    If path=='test' then produces an insecure but representative key
    that pairs with the public 'test' or 'test_alt' key.
    """
    logger.info("Getting private key from disk with path = %s", path)

    curr_dir = os.path.dirname(__file__)
    if path == "test":
        path = os.path.join(curr_dir, "./keys_for_tests/rsa_private.pem")

    elif path == "test_alt":
        path = os.path.join(curr_dir, "./keys_for_tests/rsa_private_alt.pem")
    logger.debug("Key file final path = %s", path)

    try:
        with open(path, "rb") as key_file:
            pem = key_file.read()
            if as_pem:
                logger.debug("Key returned as PEM encoded string")
                return pem
            else:
                logger.debug("Attempting to return deserialized key")
                return serialization.load_pem_private_key(
                    pem, password=None, backend=default_backend()
                )

    except Exception as e:
        raise KeyNotFoundError("private key File not found") from e


def get_symmetric_key_from_disk(path, as_string=False):
    """Get a symmetric key from disk.

    The path string is absolute.

    If path=='test' then produces an insecure but representative key.
    """
    logger.info("Getting symmetric key from disk with path = %s", path)
    curr_dir = os.path.dirname(__file__)
    if path == "test":
        path = os.path.join(curr_dir, "./keys_for_tests/symmetric_key.txt")

    elif path == "test_alt":
        path = os.path.join(curr_dir, "./keys_for_tests/symmetric_key_alt.txt")
    logger.debug("Key file final path = %s", path)

    try:
        with open(path, "rb") as key_file:
            return key_file.read()

    except Exception as e:
        raise KeyNotFoundError("symmetric key file not found") from e
