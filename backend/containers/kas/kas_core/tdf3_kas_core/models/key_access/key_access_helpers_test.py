"""Test KeyAccess."""

import pytest
import base64
import json

from pprint import pprint

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tdf3_kas_core.models import WrappedKey
from tdf3_kas_core.models import MetaData

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import generate_hmac_digest
from tdf3_kas_core.util import aes_encrypt_sha1
from tdf3_kas_core.util import aes_gcm_encrypt

from tdf3_kas_core.errors import KeyAccessError

from .key_access import KeyAccess

from .key_access_helpers import add_required_values
from .key_access_helpers import add_remote_values
from .key_access_helpers import add_wrapped_values
from .key_access_helpers import add_metadata_values

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


# =========== Test add_required_values ===========================


def test_add_required_values_success_remote():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "remote", "url": "https://example.com", "protocol": "kas"}
    kao = add_required_values(kao, raw_dict)
    assert kao.type == "remote"
    assert kao.url == "https://example.com"
    assert kao.protocol == "kas"


def test_add_required_values_type_wrapped():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "wrapped", "url": "https://example.com", "protocol": "kas"}
    kao = add_required_values(kao, raw_dict)
    assert kao.type == "wrapped"
    assert kao.url == "https://example.com"
    assert kao.protocol == "kas"


def test_add_required_values_type_remote_wrapped():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {
        "type": "remoteWrapped",
        "url": "https://example.com",
        "protocol": "kas",
    }
    kao = add_required_values(kao, raw_dict)
    assert kao.type == "remoteWrapped"
    assert kao.url == "https://example.com"
    assert kao.protocol == "kas"


def test_add_required_values_wrong_type_fail():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "unknown", "url": "https://example.com", "protocol": "kas"}
    with pytest.raises(KeyAccessError):
        add_required_values(kao, raw_dict)


def test_add_required_values_bad_url_fail():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "remote", "url": "https:example.com", "protocol": "kas"}
    with pytest.raises(KeyAccessError):
        add_required_values(kao, raw_dict)


def test_add_required_values_wrong_protocol_fail():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "remote", "url": "https://example.com", "protocol": "huh?"}
    with pytest.raises(KeyAccessError):
        add_required_values(kao, raw_dict)


def test_add_required_values_no_type_fail():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"url": "https://example.com", "protocol": "kas"}
    with pytest.raises(KeyAccessError):
        add_required_values(kao, raw_dict)


def test_add_required_values_no_url_fail():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "remote", "protocol": "kas"}
    with pytest.raises(KeyAccessError):
        add_required_values(kao, raw_dict)


def test_add_required_values_no_protocol_fail():
    """Test add_required_values."""
    kao = KeyAccess()
    raw_dict = {"type": "remote", "url": "https://example.com"}
    with pytest.raises(KeyAccessError):
        add_required_values(kao, raw_dict)


# =========== Test add_remote_values (currently a noop) =================


def test_add_remote_values():
    """Test add_remote_values."""
    kao = KeyAccess()
    kao = add_remote_values(kao, {})
    assert True


# =========== Test add_wrapped_values ===========================


def test_add_wrapped_values():
    """Test add_wrapped_values."""
    kao = KeyAccess()
    pprint(binding)
    raw_dict = {"wrappedKey": raw_wrapped_key, "policyBinding": raw_binding}
    kao = add_wrapped_values(
        kao, raw_dict, private_key=private_key, canonical_policy=canonical_policy
    )

    assert isinstance(kao, KeyAccess)
    assert kao.wrapped_key == raw_wrapped_key


# =========== Test add_metadata_values ===========================


def test_add_metadata_values_with_metadata_in_raw_dict():
    """Test add metadata values."""
    expected = {"foo": "bar"}
    print(expected)
    metadata = str.encode(json.dumps(expected))
    print(metadata)
    secret = AESGCM.generate_key(bit_length=128)
    print(secret)
    (ciphertext, iv) = aes_gcm_encrypt(metadata, secret)
    print(ciphertext)
    print(iv)
    # Note - IV prepend should not be required. Once hard-coded 12 byte
    # removal is fixed this test should run without the prepend.
    metadata_dict = {
        "algorithm": "AES_GCM",
        "iv": bytes.decode(base64.b64encode(iv)),
        "ciphertext": bytes.decode(base64.b64encode(iv + ciphertext)),
    }
    print(metadata_dict)
    metadata_json = str.encode(json.dumps(metadata_dict))
    encrypted_metadata = bytes.decode(base64.b64encode(metadata_json))
    print(encrypted_metadata)
    raw_dict = {"encryptedMetadata": encrypted_metadata}
    print(raw_dict)

    # generate the "kas wrapped 'object' key" from the local test secret
    # using the WrappedKey model.
    wrapped_secret = WrappedKey(secret)
    wrapped_key = wrapped_secret.rewrap_key(public_key)

    kao = KeyAccess()
    kao = add_metadata_values(
        kao, raw_dict, wrapped_key=wrapped_key, private_key=private_key
    )
    print(kao.metadata)
    assert isinstance(kao.metadata, MetaData)
    assert kao.metadata.get("foo") == expected["foo"]


def test_add_metadata_values_without_metadata_in_raw_dict():
    """Test add metadata values with no encrypted metadata field."""
    expected = {}

    secret = AESGCM.generate_key(bit_length=128)
    wrapped_secret = WrappedKey(secret)
    wrapped_key = wrapped_secret.rewrap_key(public_key)

    kao = KeyAccess()
    kao = add_metadata_values(kao, {}, wrapped_key=wrapped_key, private_key=private_key)
    print(kao.metadata)

    # Metadata object should exist
    assert isinstance(kao.metadata, MetaData)
    # Metadata object should be empty
    assert kao.metadata.data == expected


def test_exception_on_not_providing_wrapped_key():
    """Should throw expected error if wrapped_key absent"""
    kao = KeyAccess()
    try:
        add_metadata_values(
            kao, {"encryptedMetadata": True}, wrapped_key=None, private_key=private_key
        )
    except KeyAccessError as inst:
        assert inst.args[0] == "No wrapped key provided"


def test_exception_on_not_providing_private_key():
    """Should throw expected error if private_key absent"""
    kao = KeyAccess()
    try:
        add_metadata_values(
            kao, {"encryptedMetadata": True}, wrapped_key=wrapped_key, private_key=None
        )
    except KeyAccessError as inst:
        assert inst.args[0] == "No private key provided"
