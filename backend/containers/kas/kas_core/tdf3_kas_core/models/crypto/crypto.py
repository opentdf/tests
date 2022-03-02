"""The Crypto class."""

import logging

from tdf3_kas_core.util import aes_encrypt_sha1
from tdf3_kas_core.util import aes_decrypt_sha1

logger = logging.getLogger(__name__)


selector = {"RSA_SHA1": [aes_encrypt_sha1, aes_decrypt_sha1]}


class Crypto(object):
    """Crypto is a lightweight abstraction of the crypto utilities.

    Crypto objects provide the same two external interfaces (encrypt/decrypt)
    regardles of what method is specified. This encapsulation and abstraction
    should reduce the need for code changes; just specify a different method
    and it should just work.
    """

    def __init__(self, method):
        """Construct using the method setter to check the method."""
        # Throws a error if method not provided or not found
        selector[method]
        # If here then method is supported. Build the instance.
        self.__method = method

    @property
    def method(self):
        """Get the method string."""
        return self.__method

    @method.setter
    def method(self, method):
        """Reset the method."""
        # Wish this were DRYer, but can't call this method during construction.
        selector[method]
        self.__method = method

    def encrypt(self, plaintext, public_key):
        """Encrypt using the chosen method."""
        return selector[self.__method][0](plaintext, public_key)

    def decrypt(self, ciphertext, private_key):
        """Decrypt using the chosen method."""
        return selector[self.__method][1](ciphertext, private_key)
