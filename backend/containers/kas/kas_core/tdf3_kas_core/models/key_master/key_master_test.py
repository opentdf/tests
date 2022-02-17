"""Test the KeyMaster."""

import pytest

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

#
from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import get_symmetric_key_from_disk
from tdf3_kas_core.errors import KeyNotFoundError

from .key_master import KeyMaster


def test_key_master():
    """Test the KeyMaster constructor."""
    km = KeyMaster()
    assert isinstance(km, KeyMaster)


def test_key_master_set_key_pem():
    """Test the KeyMaster set function."""
    public_key = get_public_key_from_disk("test", as_pem=True)
    private_key = get_private_key_from_disk("test", as_pem=True)
    symmetric_key = get_symmetric_key_from_disk("test", as_string=True)

    km = KeyMaster()
    km.set_key_pem("Sym", "SYMMETRIC", symmetric_key)
    km.set_key_pem("Pub", "PUBLIC", public_key)
    km.set_key_pem("Priv", "PRIVATE", private_key)
    expected = {
        "Sym": {"name": "Sym", "type": "SYMMETRIC", "pem": symmetric_key},
        "Pub": {"name": "Pub", "type": "PUBLIC", "pem": public_key},
        "Priv": {"name": "Priv", "type": "PRIVATE", "pem": private_key},
    }
    actual = km.keys
    assert actual == expected


def test_key_master_set_key_path():
    """Test the KeyMaster set function."""
    km = KeyMaster()
    km.set_key_path("Sym", "SYMMETRIC", "symmetric path")
    km.set_key_path("Pub", "PUBLIC", "public path")
    km.set_key_path("Priv", "PRIVATE", "private path")
    expected = {
        "Sym": {"name": "Sym", "type": "SYMMETRIC", "path": "symmetric path"},
        "Pub": {"name": "Pub", "type": "PUBLIC", "path": "public path"},
        "Priv": {"name": "Priv", "type": "PRIVATE", "path": "private path"},
    }
    actual = km.keys
    assert actual == expected


def test_key_master_set_key_bad_type():
    """Test the KeyMaster set function."""
    km = KeyMaster()
    with pytest.raises(KeyNotFoundError):
        km.set_key_path("name", "UNKNOWN_TYPE", "some path")


def test_key_master_get_key_symmetric():
    """Get a symmetric key."""
    km = KeyMaster()
    km.set_key_path("SYM", "SYMMETRIC", "test")
    actual = km.get_key("SYM")
    expected = get_symmetric_key_from_disk("test")
    assert actual == expected


def test_key_master_get_key_public():
    """Get a public key."""
    km = KeyMaster()
    km.set_key_path("PUB", "PUBLIC", "test")
    actual = km.get_key("PUB")
    assert isinstance(actual, RSAPublicKey)


def test_key_master_get_key_private():
    """Get a private key."""
    km = KeyMaster()
    km.set_key_path("PRIV", "PRIVATE", "test")
    actual = km.get_export_string("PRIV")
    assert isinstance(actual, str)


def test_key_master_export_symmetric():
    """Get a symmetric key."""
    km = KeyMaster()
    km.set_key_path("SYM", "SYMMETRIC", "test")
    actual = km.get_export_string("SYM")
    assert isinstance(actual, str)


def test_key_master_export_public():
    """Get a public key."""
    km = KeyMaster()
    km.set_key_path("PUB", "PUBLIC", "test")
    actual = km.get_export_string("PUB")
    assert isinstance(actual, str)


def test_key_master_export_private():
    """Get a private key."""
    km = KeyMaster()
    km.set_key_path("PRIV", "PRIVATE", "test")
    actual = km.get_key("PRIV")
    assert isinstance(actual, RSAPrivateKey)


def test_key_master_get_key_non_existant():
    """Try to get a non-existant key."""
    km = KeyMaster()
    with pytest.raises(KeyNotFoundError):
        km.get_key("DOES_NOT_EXIST")
