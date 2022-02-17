"""Test the aes_gcm utilities."""

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .aes_gcm import aes_gcm_encrypt
from .aes_gcm import aes_gcm_decrypt


def test_aes_gcm_mode():
    """Test encrypt/decrypt."""
    expected = b"This message is the expected message."
    print(expected)
    key = AESGCM.generate_key(bit_length=128)
    print(key)
    (ciphertext, iv) = aes_gcm_encrypt(expected, key)
    print(ciphertext)
    print(iv)
    actual = aes_gcm_decrypt(ciphertext, key, iv)
    print(actual)
    assert actual == expected
