"""Test encrypt/decrypt algorithms."""

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk

from .rsa_sha1 import aes_encrypt_sha1
from .rsa_sha1 import aes_decrypt_sha1

public_key = get_public_key_from_disk("test")
private_key = get_private_key_from_disk("test")


def test_rsa_sha1_keys():
    """Test asymmetric RSA SHA1 encrypt/decrypt."""
    expected = b"Cozy sphinx waves quart jug of bad milk"
    wrapped = aes_encrypt_sha1(expected, public_key)
    actual = aes_decrypt_sha1(wrapped, private_key)
    assert actual == expected
