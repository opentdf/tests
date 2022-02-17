"""Test KeyAccess."""

import pytest
import base64

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import generate_hmac_digest
from tdf3_kas_core.util import aes_encrypt_sha1

from tdf3_kas_core.errors import KeyAccessError

from .key_access import KeyAccess

public_key = get_public_key_from_disk("test")
private_key = get_private_key_from_disk("test")

entity_public_key = get_public_key_from_disk("test_alt")
entity_private_key = get_private_key_from_disk("test_alt")

plain_key = b"This-is-the-good-key"
wrapped_key = aes_encrypt_sha1(plain_key, public_key)
msg = b"This message is valid"
binding = str.encode(generate_hmac_digest(msg, plain_key))

raw_wrapped_key = bytes.decode(base64.b64encode(wrapped_key))
raw_binding = bytes.decode(base64.b64encode(binding))
canonical_policy = bytes.decode(msg)


def test_key_access_constructor():
    """Test constructor."""
    actual = KeyAccess()
    assert isinstance(actual, KeyAccess)


def test_key_access_type_get_and_set_valid():
    """Test type get and set method with valid value."""
    actual = KeyAccess()
    actual.type = "remote"
    assert actual.type == "remote"


def test_key_access_type_set_invalid():
    """Test type invalid setter."""
    actual = KeyAccess()
    with pytest.raises(KeyAccessError):
        actual.type = "invalid value"


def test_key_access_url_get_and_set_valid():
    """Test type get and set method with valid value."""
    actual = KeyAccess()
    actual.url = "http://127.0.0.1:4000"
    assert actual.url == "http://127.0.0.1:4000"


def test_key_access_url_set_invalid():
    """Test type invalid setter."""
    actual = KeyAccess()
    with pytest.raises(KeyAccessError):
        # try to invoke the setter with an invalid string
        actual.url = "http:example.com"


def test_key_access_protocol_get_and_set_valid():
    """Test type get and set method with valid value."""
    actual = KeyAccess()
    actual.protocol = "kas"
    assert actual.protocol == "kas"


def test_key_access_protocol_set_invalid():
    """Test type invalid setter."""
    actual = KeyAccess()
    with pytest.raises(KeyAccessError):
        actual.protocol = "not a valid protocol"


def test_key_access_wrapped_key_set():
    """Test type invalid setter."""
    expected = "This is a wrapped key string. No, really, it is..."
    actual = KeyAccess()
    actual.wrapped_key = expected
    assert actual.wrapped_key == expected


def test_key_access_from_raw_remote():
    """Test the raw dict create method."""
    raw = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}
    actual = KeyAccess.from_raw(raw)
    assert actual.type == "remote"
    assert actual.url == "http://127.0.0.1:4000"
    assert actual.protocol == "kas"


def test_key_access_from_raw_wrapped():
    """Test the raw dict create method."""
    print("=======")
    print(raw_wrapped_key)
    print(raw_binding)
    raw = {
        "type": "wrapped",
        "url": "http://127.0.0.1:4000",
        "protocol": "kas",
        "wrappedKey": raw_wrapped_key,
        "policyBinding": raw_binding,
    }
    actual = KeyAccess.from_raw(
        raw, private_key=private_key, canonical_policy=canonical_policy
    )
    assert actual.type == "wrapped"
    assert actual.url == "http://127.0.0.1:4000"
    assert actual.protocol == "kas"
    assert actual.wrapped_key == raw_wrapped_key


def test_key_access_to_dict_remote():
    """Test the key_access to_dict production method."""
    raw = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}
    ka = KeyAccess.from_raw(raw, private_key)
    actual = ka.to_dict()
    assert actual == raw
