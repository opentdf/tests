"""Utilities for AES GCM-mode."""
import os
import logging

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


def aes_gcm_encrypt(plaintext, key, associated_data=None):
    """Encrypt using AES GCM mode."""
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ciphertext = aesgcm.encrypt(iv, plaintext, associated_data)
    return (ciphertext, iv)


def aes_gcm_decrypt(ciphertext, key, iv, associated_data=None):
    """Decrypt using AES GCM mode."""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext, associated_data)
