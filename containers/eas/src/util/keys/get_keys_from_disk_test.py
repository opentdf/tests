"""Test the key production functions."""

import os

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .get_keys_from_disk import (
    get_key_from_path,
    get_key_using_config,
    verify_keys_exist,
)
from .get_keys_from_disk import get_private_key_from_disk
from .get_keys_from_disk import get_public_key_from_disk
from .get_keys_from_disk import get_symmetric_key_from_disk
from .get_keys_from_disk import get_public_key_for_algorithm
from ...eas_config import EASConfig
from ...errors import ConfigurationError, KeyNotFoundError, CryptoError

eas_config = EASConfig.get_instance()

# //////// Public Key //////////


def test_get_public_key_from_disk():
    """Test the get_public_key_from_disk function.

    See if it can get the public key from the test file.
    """
    public_key = get_public_key_from_disk("test")
    assert isinstance(public_key, RSAPublicKey)


def test_get_public_key_from_disk_alt():
    """Test the get_public_key_from_disk function.

    See if it can get the public key from the test file.
    """
    public_key = get_public_key_from_disk("test_alt")
    assert isinstance(public_key, RSAPublicKey)


def test_get_public_key_from_disk_as_pem():
    """Test the get_public_key_from_disk function as pem bytes."""
    public_key = get_public_key_from_disk("test", as_pem=True)
    assert isinstance(public_key, str)


def test_get_public_key_from_disk_cert():
    """Test the get_public_key_from_disk function as pem bytes."""
    curr_dir = os.path.dirname(__file__)
    path = os.path.join(curr_dir, "keys_for_tests/x509_cert.pem")
    public_key = get_public_key_from_disk(path)
    assert isinstance(public_key, RSAPublicKey)


def test_get_public_key_from_disk_bad_path():
    """Test the get_public_key_from_disk function with bad path."""
    with pytest.raises(KeyNotFoundError):
        get_public_key_from_disk("/bad/path")


# //////// Private Key //////////


def test_get_private_key_from_disk():
    """Test the get_private_key_from_disk function.

    See if it gets a private key from the test file.
    """
    private_key = get_private_key_from_disk("test")
    assert isinstance(private_key, RSAPrivateKey)


def test_get_private_key_from_disk_alt():
    """Test the get_private_key_from_disk function.

    See if it gets a private key from the test file.
    """
    private_key = get_private_key_from_disk("test_alt")
    assert isinstance(private_key, RSAPrivateKey)


def test_get_private_key_from_disk_as_pem():
    """Test the get_private_key_from_disk function as pem bytes."""
    private_key = get_private_key_from_disk("test", as_pem=True)
    assert isinstance(private_key, bytes)


def test_get_private_key_from_disk_bad_path():
    """Test the get_private_key_from_disk with bad path."""
    with pytest.raises(KeyNotFoundError):
        get_private_key_from_disk("/bad/path")


# //////// Symmetric Key //////////


def test_get_symmetric_key_from_disk():
    """Test the get_symmetric_key_from_disk function."""
    symmetric_key = get_symmetric_key_from_disk("test")
    assert symmetric_key == b"This-is-a-symmetric-key\n"


def test_get_symmetric_key_from_disk_alt():
    """Test the get_symmetric_key_from_disk function."""
    symmetric_key = get_symmetric_key_from_disk("test_alt")
    assert symmetric_key == b"This-is-a-different-symmetric-key\n"


def test_get_symmetric_key_from_disk_bad_path():
    """Test the get_symmetric_key_from_disk with bad path."""
    with pytest.raises(KeyNotFoundError):
        get_symmetric_key_from_disk("/bad/path")


def test_verify_keys_exist():
    verify_keys_exist()


def test_get_key_using_config():
    assert get_key_using_config("EAS_PRIVATE_KEY")
    with pytest.raises(ConfigurationError):
        get_key_using_config("NO_SUCH_KEY")


def test_get_key_from_path():
    with pytest.raises(KeyNotFoundError):
        get_key_from_path("/no/such/path")


def test_missing_key_problems():
    assert get_key_using_config("EAS_PRIVATE_KEY")
    assert get_key_using_config("KAS_CERTIFICATE")

    saved_kas_public_key = eas_config.get_item("KAS_CERTIFICATE")

    eas_config.cache.update({"KAS_CERTIFICATE": None})
    with pytest.raises(ConfigurationError):
        get_key_using_config("KAS_CERTIFICATE")

    eas_config.cache.update({"KAS_CERTIFICATE": "/invalid"})
    with pytest.raises(KeyNotFoundError):
        get_key_using_config("KAS_CERTIFICATE")

    # restore setting
    eas_config.cache.update({"KAS_CERTIFICATE": saved_kas_public_key})


def test_missing_kas_ec_public_key_problems():
    assert get_key_using_config("KAS_EC_SECP256R1_CERTIFICATE")

    saved_kas_public_key = eas_config.get_item("KAS_EC_SECP256R1_CERTIFICATE")

    eas_config.cache.update({"KAS_EC_SECP256R1_CERTIFICATE": None})
    with pytest.raises(ConfigurationError):
        get_key_using_config("KAS_EC_SECP256R1_CERTIFICATE")

    eas_config.cache.update({"KAS_EC_SECP256R1_CERTIFICATE": "/invalid"})
    with pytest.raises(KeyNotFoundError):
        get_key_using_config("KAS_EC_SECP256R1_CERTIFICATE")


def test_get_public_key_for_algorithm_rsa():
    """Test the get_public_key_for_algorithm function for rsa."""
    rsa_public_key = get_public_key_for_algorithm("rsa:2048")
    assert rsa_public_key == eas_config.get_item("KAS_CERTIFICATE")


def test_get_public_key_for_algorithm_ec_secp_256_r1():
    """Test the get_public_key_for_algorithm function for ec secp256r1."""
    secp256r1_pub_key = get_public_key_for_algorithm("ec:secp256r1")
    assert secp256r1_pub_key == eas_config.get_item("KAS_EC_SECP256R1_CERTIFICATE")


def test_get_public_key_for_algorithm_ec_secp_521_r1():
    """Test the get_public_key_for_algorithm function for ec secp5216r1."""
    with pytest.raises(CryptoError):
        get_public_key_for_algorithm("ec:secp521r1")


def test_get_public_key_for_algorithm_no_algorithm():
    """Test the get_public_key_for_algorithm function without algorithm"""
    rsa_public_key = get_public_key_for_algorithm(None)
    assert rsa_public_key == eas_config.get_item("KAS_CERTIFICATE")
