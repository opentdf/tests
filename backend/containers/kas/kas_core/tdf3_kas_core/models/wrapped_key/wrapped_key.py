"""WrappedKey class."""

import base64
import logging

from tdf3_kas_core.models.crypto import Crypto
from tdf3_kas_core.util import validate_hmac

logger = logging.getLogger(__name__)


class WrappedKey(object):
    """This class holds the wrapped key split.

    It also owns the key split rewrapping process.
    """

    @classmethod
    def from_raw(cls, raw_wrapped_key, private_unwrap_key, wrap_method="RSA_SHA1"):
        """Create a WrappedKey from raw data."""
        logger.debug("------ Unpacking Wrapped Key")
        wrapped_key = base64.b64decode(raw_wrapped_key)
        crypto = Crypto(wrap_method)
        plain_key = crypto.decrypt(wrapped_key, private_unwrap_key)
        wk = cls(plain_key)
        logger.debug("------ Wrapped Key construction complete")
        return wk

    @classmethod
    def from_plain(cls, plain_key):
        """Create a WrappedKey from a plain key."""
        return cls(plain_key)

    def __init__(self, plain_key):
        """Construct a WrappedKey instance if trusted.

        The risk of having the clear text key in memory (as self.__wrapped_key)
        is a trade against the extra work of repeated unwrapping operations.
        This decision should be revisited if there are security issues.
        """
        # If here then the key can be trusted. Pack and ship the instance.
        self.__unwrapped_key = plain_key

    @property
    def plain_key(self):
        """Return the trusted key."""
        # NOTE - this should not be possible. Need to refactor this class.
        logger.warning("Plain key access")
        return self.__unwrapped_key

    @plain_key.setter
    def plain_key(self, key):
        """Protect the key."""
        logger.warning("Attempt to reset the key in a wrapped key model")
        pass

    def perform_hmac_check(self, binding, message, method="HS256"):
        """Perform a HMAC check on the message string.

        Throws an error if the HMAC does not pass.  Method is currently
        ignored.
        """
        logger.debug(message)
        logger.debug(binding)
        validate_hmac(message, self.__unwrapped_key, binding)

    def rewrap_key(self, entity_public_key, method="RSA_SHA1"):
        """Rewrap the held key with another key."""
        crypto = Crypto(method)
        entity_wrapped_key = crypto.encrypt(self.__unwrapped_key, entity_public_key)
        return bytes.decode(base64.b64encode(entity_wrapped_key))
