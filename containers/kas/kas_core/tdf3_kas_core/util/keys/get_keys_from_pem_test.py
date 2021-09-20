"""Test the key production functions."""

import os
import pytest  # noqa: F401

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk

from tdf3_kas_core.util import get_public_key_from_pem
from tdf3_kas_core.util import get_private_key_from_pem


# //////// Public Key //////////


def test_get_public_key_from_pem():
    """Test the get_public_key_from_disk function as pem bytes."""
    public_key_pem = get_public_key_from_disk("test", as_pem=True)
    public_key = get_public_key_from_pem(public_key_pem)
    assert isinstance(public_key, RSAPublicKey)


def test_get_public_key_from_pem_cert():
    """Test the get_public_key_from_disk function as pem bytes."""
    curr_dir = os.path.dirname(__file__)
    path = os.path.join(curr_dir, "keys_for_tests/x509_cert.pem")
    public_key_cert = get_public_key_from_disk(path, as_pem=True)
    public_key = get_public_key_from_pem(public_key_cert)
    assert isinstance(public_key, RSAPublicKey)


# //////// Private Key //////////


def test_get_private_key_from_pem():
    """Test the get_private_key_from_disk function as pem bytes."""
    private_key_pem = get_private_key_from_disk("test", as_pem=True)
    private_key = get_private_key_from_pem(private_key_pem)
    assert isinstance(private_key, RSAPrivateKey)
