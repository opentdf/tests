"""Test the hmac utilities."""

import pytest

from .hmac import validate_hmac, generate_hmac_digest
from tdf3_kas_core.errors import InvalidBindingError

good_msg = b"This message is expected."
good_key = b"TheSecretKey"

bad_msg = b"This message is unexpected."
bad_key = b"SomeOtherSecret"


def test_hmac_digest():
    """Test the digest generator."""
    digest = generate_hmac_digest(good_msg, good_key)
    assert isinstance(digest, str)


good_binding = str.encode(generate_hmac_digest(good_msg, good_key))
bad_binding = str.encode(generate_hmac_digest(bad_msg, bad_key))


def test_validate_hmac_good():
    """Test validate_hmac for success."""
    assert validate_hmac(good_msg, good_key, good_binding) is True


def test_validate_hmac_fail_msg():
    """Test validate_hmac for failure when the message has changed."""
    with pytest.raises(InvalidBindingError):
        validate_hmac(bad_msg, good_key, good_binding)


def test_validate_hmac_fail_key():
    """Test validate_hmac for failure when the wrong key is used."""
    with pytest.raises(InvalidBindingError):
        validate_hmac(good_msg, bad_key, good_binding)


def test_validate_hmac_fail_binding():
    """Test validate_hmac for failure when the wrong binding is used."""
    with pytest.raises(InvalidBindingError):
        validate_hmac(good_msg, good_key, bad_binding)
