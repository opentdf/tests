"""Test the metadata class."""

import base64
import json
import pytest  # noqa: F401

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .metadata import MetaData
from tdf3_kas_core.util import aes_gcm_encrypt


def test_metadata_constructor():
    """Test basic construction."""
    data_dict = {"foo": "bar"}
    metadata = MetaData(data_dict)
    assert isinstance(metadata, MetaData)


def test_metadata_constructor_no_args():
    """Test empty construction."""
    metadata = MetaData()
    assert isinstance(metadata, MetaData)


def test_metadata_has():
    """Test the has method. Has is a shallow check."""
    data_dict = {"foo": {"bar": "baz"}}
    metadata = MetaData(data_dict)
    assert metadata.has("foo") is True
    assert metadata.has("bar") is False


def test_metadata_get():
    """Test individual get."""
    data_dict = {"foo": {"bar": "baz"}}
    metadata = MetaData(data_dict)
    # Does it get "foo"
    actual1 = metadata.get("foo")
    assert actual1 == {"bar": "baz"}
    # Was 'foo' a copy or a ref?
    actual1["bar"] = "biff"
    actual2 = metadata.get("foo")
    assert actual2 == {"bar": "baz"}


def test_metadata_data_getter():
    """Test the data dict getter."""
    expected = {"foo": {"bar": "baz"}}
    metadata = MetaData(expected)
    # Does it get "foo"
    actual1 = metadata.data
    assert actual1 == expected
    # Was it a copy or a ref?
    actual1["bar"] = "biff"
    actual2 = metadata.get("foo")
    assert actual2 == {"bar": "baz"}


def test_metadata_data_setter():
    """Test the data dict getter. Should be a noop."""
    expected = {"foo": "bar"}
    metadata = MetaData(expected)
    metadata.data = {"boy": "howdie"}
    actual = metadata.data
    assert actual == expected


# --------------------------------------------------------------------
# Note - IV prepend should not be required. Once hard-coded 12 byte
# removal is fixed this test should run without the prepend.
@pytest.mark.skip()
def test_metadata_from_raw():
    """Test raw_data factory with encryption."""
    expected = {"foo": "bar"}
    print(expected)
    metadata = str.encode(json.dumps(expected))
    print(metadata)
    secret = AESGCM.generate_key(bit_length=128)
    print(secret)
    (encrypted_metadata, iv) = aes_gcm_encrypt(metadata, secret)
    print(encrypted_metadata)
    print(iv)
    raw_metadata = {
        "algorithm": "AES_GCM",
        "iv": base64.b64encode(iv),
        "ciphertext": base64.b64encode(encrypted_metadata),
    }
    print(raw_metadata)
    metadata = MetaData.from_raw(raw_metadata, secret)
    assert isinstance(metadata, MetaData)
    assert metadata.data == expected


def test_metadata_from_raw_with_iv_prepend():
    """Test raw_data factory with encryption."""
    expected = {"foo": "bar"}
    expected_encoded = str.encode(json.dumps(expected))
    secret = AESGCM.generate_key(bit_length=128)
    (encrypted, iv) = aes_gcm_encrypt(expected_encoded, secret)
    raw_metadata = {
        "algorithm": "AES_GCM",
        "iv": base64.b64encode(iv),
        "ciphertext": base64.b64encode(iv + encrypted),
    }
    metadata = MetaData.from_raw(raw_metadata, secret)
    assert isinstance(metadata, MetaData)
    assert metadata.data == expected
