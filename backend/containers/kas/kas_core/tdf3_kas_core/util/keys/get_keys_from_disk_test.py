"""Test the key production functions."""

import os
import pytest

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import get_symmetric_key_from_disk
from tdf3_kas_core.errors import KeyNotFoundError


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
    assert isinstance(public_key, bytes)


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
