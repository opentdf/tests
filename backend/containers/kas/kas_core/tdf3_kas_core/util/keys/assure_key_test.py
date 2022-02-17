"""Test assure key utilitites."""

import pytest

from cryptography.hazmat.backends.openssl.rsa import _RSAPublicKey
from cryptography.hazmat.backends.openssl.rsa import _RSAPrivateKey

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk

from tdf3_kas_core.errors import CryptoError

from .assure_key import assure_public_key
from .assure_key import assure_private_key

public_key = get_public_key_from_disk("test")
private_key = get_private_key_from_disk("test")

public_key_pem = get_public_key_from_disk("test", as_pem=True)
private_key_pem = get_private_key_from_disk("test", as_pem=True)


def test_assure_public_key_key():
    """Test assure_public_key passes through RSAPublicKeys."""
    actual = assure_public_key(public_key)
    assert actual == public_key


def test_assure_public_key_pem():
    """Test assure_public_key converts PEM encoded bytes."""
    actual = assure_public_key(public_key_pem)
    assert isinstance(actual, _RSAPublicKey)


def test_assure_public_key_fail_str():
    """Test assure_public_key raises error on bad input."""
    with pytest.raises(CryptoError):
        assure_public_key("bad input")


def test_assure_public_key_fail_private():
    """Test assure_public_key raises error with private key."""
    with pytest.raises(CryptoError):
        assure_public_key(private_key)


def test_assure_public_key_fail_private_pem():
    """Test assure_public_key raises error with private pem."""
    with pytest.raises(CryptoError):
        assure_public_key(private_key_pem)


def test_assure_private_key_key():
    """Test assure_private_key passes through RSAPrivateKeys."""
    actual = assure_private_key(private_key)
    assert actual == private_key


def test_assure_private_key_pem():
    """Test assure_private_key converts PEM encoded bytes."""
    actual = assure_private_key(private_key_pem)
    assert isinstance(actual, _RSAPrivateKey)


def test_assure_private_key_fail_bad_input():
    """Test assure_private_key raises error on bad input."""
    with pytest.raises(CryptoError):
        assure_private_key("bad input")


def test_assure_private_key_fail_public():
    """Test assure_private_key raises error on public key."""
    with pytest.raises(CryptoError):
        assure_private_key(public_key)


def test_assure_private_key_fail_public_pem():
    """Test assure_private_key raises error on bad input."""
    with pytest.raises(CryptoError):
        assure_private_key(public_key_pem)
