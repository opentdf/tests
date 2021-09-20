"""Test assure key utilitites."""

import pytest  # noqa: F401

from cryptography.hazmat.backends.openssl.rsa import _RSAPublicKey
from cryptography.hazmat.backends.openssl.rsa import _RSAPrivateKey

from .get_keys_from_disk import get_public_key_from_disk
from .get_keys_from_disk import get_private_key_from_disk

from src.errors import CryptoError

from .assure_keys import assure_public_key
from .assure_keys import assure_private_key

public_key = get_public_key_from_disk("test")
private_key = get_private_key_from_disk("test")

public_key_pem = get_public_key_from_disk("test", as_pem=True)
private_key_pem = get_private_key_from_disk("test", as_pem=True)

cert = (
    "-----BEGIN CERTIFICATE-----\n"
    "MIIDsTCCApmgAwIBAgIJAONESzw+N+3SMA0GCSqGSIb3DQEBDAUAMHUxCzAJBgNV\n"
    "BAYTAlVTMQswCQYDVQQIDAJEQzETMBEGA1UEBwwKV2FzaGluZ3RvbjEPMA0GA1UE\n"
    "CgwGVmlydHJ1MREwDwYDVQQDDAhhY2NvdW50czEgMB4GCSqGSIb3DQEJARYRZGV2\n"
    "b3BzQHZpcnRydS5jb20wIBcNMTgxMDE4MTY1MjIxWhgPMzAxODAyMTgxNjUyMjFa\n"
    "MHUxCzAJBgNVBAYTAlVTMQswCQYDVQQIDAJEQzETMBEGA1UEBwwKV2FzaGluZ3Rv\n"
    "bjEPMA0GA1UECgwGVmlydHJ1MREwDwYDVQQDDAhhY2NvdW50czEgMB4GCSqGSIb3\n"
    "DQEJARYRZGV2b3BzQHZpcnRydS5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAw\n"
    "ggEKAoIBAQC3GdLoh0BHjsu9doR2D3+MekHB9VR/cmqV7v6R7xEWZJkuymrJzPy8\n"
    "reKSLK7yDhUEZNA9jslVReMpQHaR0/ND0fevJZ0yoo8IXGSIYv+prX6wZbqp4Ykc\n"
    "ahWMx5nFzpCDSJfd2ZBnCvnsz4x95eX8jme9qNYcELFDEkeLFCushNLXdg8NKrWh\n"
    "/Ew8VEZGf4hmtb30J11Uj5P2cv6zgATpa6xqjpg8hUarQYTyQi01DTKZ9iR8Kw/x\n"
    "AH+ocXtbJdy046bMb9uMpeJ/LlMpELSN5pqamVJis/NkWJOVRdwD//p7WQdz9T4T\n"
    "GzvvrO8KUQoORYERf0EtwBtufv5SDpNhAgMBAAGjQjBAMB0GA1UdDgQWBBTVPQ3Y\n"
    "oYYXHWbZfK2sonPrOE7nszAfBgNVHSMEGDAWgBTVPQ3YoYYXHWbZfK2sonPrOE7n\n"
    "szANBgkqhkiG9w0BAQwFAAOCAQEAT2ZjAJPQSf0tME0vbAqHzB8iIhR5KniGgJMJ\n"
    "mRrXbTl2HBH6WnRwfgY1Ok1X224ph4uBGaAUGs8ONBKli0673jE+IgVob7TCu2yV\n"
    "gHaKcybDegK4esVNRdsDmOWT+eTxGYAzejdIgdFo6R7Xvs87RbqwM4Cko4xoWGVF\n"
    "ghWsBqUmyg/rZoggL5H1V166hvoLPKU7SrCInZ8Wd6x4rsNDaxNiC9El102pKXu4\n"
    "wCiqJZ0XwklGkH9X0Z5x0txc68tqmSlE/z4i/96oxMp0C2thWfy90ub85f5FrB9m\n"
    "tN5S0umLPkMUJ6zBIxh1RQK1ZYjfuKij+EEimbqtte9rYyQr3Q==\n"
    "-----END CERTIFICATE-----"
)


def test_assure_public_key_key():
    """Test assure_public_key passes through RSAPublicKeys."""
    actual = assure_public_key(public_key)
    assert actual == public_key


def test_assure_public_key_pem():
    """Test assure_public_key converts PEM encoded bytes."""
    actual = assure_public_key(public_key_pem)
    assert isinstance(actual, _RSAPublicKey)


def test_assure_public_key_pem_string():
    """Test assure_public_key converts PEM encoded string."""
    public_string = public_key_pem
    actual = assure_public_key(public_string)
    assert isinstance(actual, _RSAPublicKey)


def test_assure_public_key_pem_cert_string():
    """Test assure_public_key converts PEM encoded cert string."""
    actual = assure_public_key(cert)
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


def test_assure_private_key_pem_string():
    """Test assure_private_key converts PEM encoded bytes."""
    private_string = bytes.decode(private_key_pem)
    actual = assure_private_key(private_string)
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
