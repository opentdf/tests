import pytest

from .crypto import GCMCipher, flags


@pytest.fixture
def allow_small_iv():
    old_value = flags["allow_small_iv"]
    flags["allow_small_iv"] = True
    yield
    flags["allow_small_iv"] = old_value


@pytest.fixture
def disallow_small_iv():
    old_value = flags["allow_small_iv"]
    flags["allow_small_iv"] = False
    yield
    flags["allow_small_iv"] = old_value


def test_encrypt_classic_iv_past(allow_small_iv):
    cipher = GCMCipher(b"\0" * 16, b"\0" * 3)
    cipher.tag_length = 8

    (ciphertext, tag) = cipher.encrypt(b"hello")
    assert cipher.decrypt(ciphertext, tag) == b"hello"
    assert len(tag) == 8


def test_encrypt_standard_iv_past(allow_small_iv):
    cipher = GCMCipher(b"\0" * 16, b"\0" * 12)
    cipher.tag_length = 12

    (ciphertext, tag) = cipher.encrypt(b"hello")
    assert cipher.decrypt(ciphertext, tag) == b"hello"
    assert len(tag) == 12


def test_encrypt_classic_iv_future(disallow_small_iv):
    with pytest.raises(ValueError):
        cipher = GCMCipher(b"\0" * 16, b"\0" * 3)


def test_encrypt_standard_iv_future(disallow_small_iv):
    cipher = GCMCipher(b"\0" * 16, b"\0" * 12)
    cipher.tag_length = 12

    (ciphertext, tag) = cipher.encrypt(b"hello")
    assert cipher.decrypt(ciphertext, tag) == b"hello"
    assert len(tag) == 12
