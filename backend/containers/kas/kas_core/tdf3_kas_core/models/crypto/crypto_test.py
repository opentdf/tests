"""Test the crypto model."""

import pytest
from .crypto import Crypto

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk

public_key = get_public_key_from_disk("test")
private_key = get_private_key_from_disk("test")


def test_crypto_no_method_fail():
    """Crypto should throw an error with no method provided."""
    with pytest.raises(Exception):
        Crypto()


def test_crypto_unknown_method_fail():
    """Crypto should throw an error with no method provided."""
    with pytest.raises(Exception):
        Crypto("FOO")


def test_crytpo_rsa_sha1():
    """See if the SHA1 selection works."""
    crypto = Crypto("RSA_SHA1")
    expected = b"this-is-a-test-key"
    encrypted = crypto.encrypt(expected, public_key)
    actual = crypto.decrypt(encrypted, private_key)
    assert actual == expected


def test_crypto_method_get_and_set_known_method():
    """See if the selection setter works.

    This is not a great test with only one method...
    """
    crypto = Crypto("RSA_SHA1")
    crypto.method = "RSA_SHA1"
    assert crypto.method == "RSA_SHA1"


def test_crypto_method_get_and_set_unknown_method():
    """See if the selection setter can discriminate."""
    crypto = Crypto("RSA_SHA1")
    with pytest.raises(Exception):
        crypto.method = "NOT_VALID_METHOD"
