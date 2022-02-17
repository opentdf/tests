"""KeyAccess helpers functions."""
import logging
import base64
import logging
import json

from tdf3_kas_core.models import WrappedKey
from tdf3_kas_core.models import MetaData

from tdf3_kas_core.errors import BadRequestError
from tdf3_kas_core.errors import KeyAccessError

logger = logging.getLogger(__name__)


KEY_ACCESS_TYPES = "remote", "wrapped", "remoteWrapped"
PROTOCOL_TYPES = ("kas",)


def add_required_values(kao, raw_dict):
    """Unpack the required values."""
    if "type" not in raw_dict:
        logger.error("No type value in %s", raw_dict)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("No type value")
    if "url" not in raw_dict:
        logger.error("No url value in %s", raw_dict)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("No url value")
    if "protocol" not in raw_dict:
        logger.error("No protocol value in %s", raw_dict)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("No protocol value")

    logger.debug("KeyAccessObject.type = %s", raw_dict["type"])
    kao.type = raw_dict["type"]

    logger.debug("KeyAccessObject.url = %s", raw_dict["url"])
    kao.url = raw_dict["url"]

    logger.debug("KeyAccessObject.protocol = %s", raw_dict["protocol"])
    kao.protocol = raw_dict["protocol"]

    return kao


def add_remote_values(kao, raw_dict):
    """Add the mandatory fields for 'remote' type key access objects."""
    # check and add the policy_sync_options value
    return kao


def add_wrapped_values(kao, raw_dict, private_key=None, canonical_policy=None):
    """Add the mandatory fields for 'wrapped' type key access objects."""
    # Check the inputs
    if "wrappedKey" not in raw_dict:
        logger.error("No wrapped Key in %s", raw_dict)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("No wrapped Key")
    if "policyBinding" not in raw_dict:
        logger.error("No policy binding in %s", raw_dict)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("No policy bindings")
    if canonical_policy is None:
        logger.error("No canonical policy for hmac check")
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("Canonical policy provided")

    try:
        # This used to be a WrappedKey model. Now it is just the string.
        kao.wrapped_key = raw_dict["wrappedKey"]
        kao.wrapped_key_model = WrappedKey.from_raw(kao.wrapped_key, private_key)

        kao.policy_binding = raw_dict["policyBinding"]

        hmac_message = str.encode(canonical_policy)
        hmac_binding = base64.b64decode(str.encode(kao.policy_binding))

        logger.debug("hmac message = %s", hmac_message)
        logger.debug("hmac binding = %s", hmac_binding)
    except ValueError as e:
        raise BadRequestError(
            f"Error unwrapping KAO and validating binding [{e}]"
        ) from e
    kao.wrapped_key_model.perform_hmac_check(hmac_binding, hmac_message)
    return kao


def add_metadata_values(kao, raw_dict, wrapped_key=None, private_key=None):
    """Decrypt and unpack the metadata.

    Wrapped_key is (currently) the kas-wrapped symmetric object key, and
    private_key is the kas private key used to unwrap the object key.

    In the (near) future this will change.  The kas-private as a single key
    that "rules them all" may change.  Also, and more importantly, the object
    key is not always available, so there may be a metadata-specific symmetric
    encryption key that is delivered wrapped in some form.
    """
    if "encryptedMetadata" not in raw_dict:
        logger.debug("EncryptedMetadata not provided; creating empty MetaData model.")
        kao.metadata = MetaData()
        return kao

    if private_key is None:
        logger.error("No private key in %s", raw_dict)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyAccessError("No private key provided")

    if wrapped_key is None:
        logger.error("No wrapped key, can't read Metadata")
        raise KeyAccessError("No wrapped key provided")

    raw_metadata = raw_dict["encryptedMetadata"]
    logger.debug("raw metadata = %s", raw_metadata)

    json_metadata = bytes.decode(base64.b64decode(raw_metadata))
    logger.debug("json metadata = %s", json_metadata)

    metadata_dict = json.loads(json_metadata)
    logger.debug("metadata_dict = %s", metadata_dict)

    # Policies currently work with a single KAS environment.
    # Future implementations may support a multi-KAS environment.
    object_key = WrappedKey.from_raw(wrapped_key, private_key)
    metadata = MetaData.from_raw(metadata_dict, object_key.plain_key)

    logger.debug("metadata = %s", metadata)

    kao.metadata = metadata
    return kao
