"""Utility functions to get public and private keys.

The current methods only do reads from disk. Alternate methods may be
added to support other approaches.
"""

import logging
import os

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from .assure_keys import assure_private_key, assure_public_key
from ...eas_config import EASConfig
from ...errors import ConfigurationError, KeyNotFoundError, CryptoError

logger = logging.getLogger(__name__)
eas_config = EASConfig.get_instance()


def verify_keys_exist(
    key_names=[
        "EAS_CERTIFICATE",
        "EAS_PRIVATE_KEY",
        "KAS_CERTIFICATE",
        "KAS_EC_SECP256R1_CERTIFICATE",
    ]
):
    """
    Confirm that keys are present.  Throw a KeyNotFoundError if missing.
    Note that gunicorn.py also checks these keys on startup.


    :param key_names: A list of strings representing the names of the keys to check.
        These must correspond to the env var or eas_config value with the path to the key.
        Default provided with current keys.
    :return: True if all listed keys exist at the expected locations.
    """
    for key_name in key_names:
        key = get_key_using_config(key_name)
        try:
            if isinstance(key, bytes) or isinstance(key, str):
                logger.debug("name=%s, len=%d", key_name, len(key))
            else:
                logger.debug("name=%s, key_size=%d", key_name, key.key_size)
        except AttributeError:
            logger.debug("name=%s, type=%s", key_name, type(key))
        if not key:
            raise ConfigurationError(
                f"{key_name} env var is required to be a path to a key file."
            )
        if "CERTIFICATE" in key_name or "PUBLIC" in key_name:
            assure_public_key(key)
        elif "PRIVATE" in key_name:
            assure_private_key(key)
    return True


def get_key_using_config(path_config_name):
    """
    Load a key using the EAS App scheme:
    * Environment variable (or default value from defaults.json) has a path
    * Path points to a file
    * File contains the key

    :param path_config_name: String with the name of an environment/config variable.
    :return: String with the key
    """
    key_path = eas_config.get_item(path_config_name)
    if key_path is None:
        raise ConfigurationError(
            "{} environment variable missing. Should be path to a file with a key value.".format(
                path_config_name
            )
        )
    if key_path.startswith("---"):
        return key_path
    if not os.path.isfile(key_path):
        raise KeyNotFoundError(
            f"{path_config_name} key not found at expected path {key_path}"
        )
    return get_key_from_path(key_path)


def get_key_from_path(key_path):
    """Flexible function to fetch a key from any path.

    :param key_path: path to file containing key
    :return: key value stored at file path.
    """
    logger.info("loading key from %s", key_path)
    try:
        with open(key_path, "r") as f:
            key_value = f.read()
    except FileNotFoundError:
        raise KeyNotFoundError(f"Key not found at {key_path}")
    return key_value


def get_public_key_from_disk(path, as_pem=False):
    """Get a public key from disk.

    The path string is absolute.

    If path=='test' then produces an insecure but representative key
    that pairs with the private 'test' or "test_alt" key.
    """
    logger.info("Getting public key from disk with path = %s", path)

    curr_dir = os.path.dirname(__file__)
    if path == "test":
        path = os.path.join(curr_dir, "keys_for_tests/rsa_public.pem")

    elif path == "test_alt":
        path = os.path.join(curr_dir, "keys_for_tests/rsa_public_alt.pem")

    logger.debug("Key file final path = %s", path)

    try:
        with open(path, "rb") as key_file:
            pem_data = key_file.read()
            logger.debug("PEM public data = %s", pem_data)
            if as_pem:
                logger.debug("Key returned as PEM encoded string")
                return bytes.decode(pem_data)
            else:
                try:
                    logger.debug("Attempting to returndeserialize key")
                    return serialization.load_pem_public_key(
                        pem_data, backend=default_backend()
                    )
                except Exception:
                    logger.debug("Deserialization failed; loading cert")
                    cert = x509.load_pem_x509_certificate(pem_data, default_backend())
                    logger.debug("Cert check passed, returning key")
                    return cert.public_key()

    except Exception as err:
        # TODO - could be a bit more specific here.
        # Lots of exceptions possible.
        raise KeyNotFoundError("KEY File not found") from err


def get_private_key_from_disk(path, as_pem=False):
    """Get a private key from disk.

    The path string is absolute.

    If path=='test' then produces an insecure but representative key
    that pairs with the public 'test' or 'test_alt' key.
    """
    logger.info("Getting private key from disk with path = %s", path)

    curr_dir = os.path.dirname(__file__)
    if path == "test":
        path = os.path.join(curr_dir, "keys_for_tests/rsa_private.pem")

    elif path == "test_alt":
        path = os.path.join(curr_dir, "keys_for_tests/rsa_private_alt.pem")
    logger.debug("Key file final path = %s", path)

    try:
        with open(path, "rb") as key_file:
            pem = key_file.read()
            logger.debug("PEM private data = %s", pem)
            if as_pem:
                logger.debug("Key returned as PEM encoded string")
                return pem
            else:
                logger.debug("Attempting to return deserialized key")
                return serialization.load_pem_private_key(
                    pem, password=None, backend=default_backend()
                )

    except Exception as e:
        # TODO - could be a bit more specific here.
        # Lots of exceptions possible.
        raise KeyNotFoundError("Key File not found") from e


def get_symmetric_key_from_disk(path, as_string=False):
    """Get a symmetric key from disk.

    The path string is absolute.

    If path=='test' then produces an insecure but representative key.
    """
    logger.info("Getting symmetric key from disk with path = %s", path)
    curr_dir = os.path.dirname(__file__)
    if path == "test":
        path = os.path.join(curr_dir, "keys_for_tests/symmetric_key.txt")

    elif path == "test_alt":
        path = os.path.join(curr_dir, "keys_for_tests/symmetric_key_alt.txt")

    logger.debug("Key file final path = %s", path)

    try:
        with open(path, "rb") as key_file:
            return key_file.read()

    except Exception as e:
        # TODO - could be a bit more specific here.
        # Lots of exceptions possible.
        raise KeyNotFoundError("Key File not found") from e


def get_public_key_for_algorithm(algo_name=None):
    """
    Retrieve the public key for given algorithm name
    """
    if algo_name is None:
        logger.warning(
            "'algorithm' is missing and defaulting to rsa with 2048 key size."
        )
        kas_public_key_path = eas_config.get_item("KAS_CERTIFICATE")
        return kas_public_key_path

    algo_supported_names = ["rsa:2048", "ec:secp256r1"]
    if algo_name not in algo_supported_names:
        logger.error("Algorithm %s is not supported", algo_name)
        raise CryptoError("Supported algorithms are RSA-2048, EC-SECP256R1")
    else:
        if algo_name == "ec:secp256r1":
            algo_key_name = algo_name.replace(":", "_")
            public_key_name = f"KAS_{algo_key_name.upper()}_CERTIFICATE"
            kas_public_key_path = eas_config.get_item(public_key_name)
            return kas_public_key_path
        else:
            kas_public_key_path = eas_config.get_item("KAS_CERTIFICATE")
            return kas_public_key_path
