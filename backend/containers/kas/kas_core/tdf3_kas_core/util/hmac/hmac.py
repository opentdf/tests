"""Validate a message with HMAC."""

import hashlib
import hmac
import logging

from tdf3_kas_core.errors import InvalidBindingError

logger = logging.getLogger(__name__)


def validate_hmac(msg, key, binding, method=None):
    """Validate a message string with a hmac."""
    if method is None:  # this is the safer way to do argument defaults
        method = "H256"

    # Currently only does H256
    if method != "H256":
        logger.error("Unknown method %s", method)
        raise InvalidBindingError("Unknown hmac method")

    # Check the msg
    digest = str.encode(generate_hmac_digest(msg, key))
    if not hmac.compare_digest(binding, digest):
        raise InvalidBindingError("Invalid Binding")

    # msg checked out
    return True


def generate_hmac_digest(msg, key):
    """Generate a digest string from msg and key."""
    # Create a digest (key encrypted hash) of the message
    logger.debug("msg = %s", msg)
    if isinstance(msg, str):
        bmsg = msg.encode()
    else:
        bmsg = msg
    digest_maker = hmac.new(key, msg=bmsg, digestmod=hashlib.sha256)
    logger.debug("digest maker = %s", digest_maker)
    digest = digest_maker.hexdigest()
    logger.debug("digest = %s", digest)
    return digest
