"""KeyAccess model."""
import logging

import logging

from tdf3_kas_core.models import MetaData

from tdf3_kas_core.errors import KeyAccessError
from tdf3_kas_core.validation import attr_authority_check

from .key_access_helpers import add_required_values
from .key_access_helpers import add_remote_values
from .key_access_helpers import add_wrapped_values
from .key_access_helpers import add_metadata_values

logger = logging.getLogger(__name__)


KEY_ACCESS_TYPES = "remote", "wrapped", "remoteWrapped"
PROTOCOL_TYPES = ("kas",)


class KeyAccess(object):
    """The Key Access class.

    The purpose of this class is to clean and repackage the KeyAccess object
    into a form that is understood by the plugins. Deviations from acceptable
    values throw errors that end the rewrap request. Follows the builder
    pattern.
    """

    def __init__(self):
        """Construct an empty key access.

        For internal use only.
        """
        self.__type = None
        self.__url = None
        self.__protocol = None
        self.__wrapped_key = None
        self.__policy_binding = None
        self.__metadata = None
        self.__policy_sync_options = None

    @classmethod
    def from_raw(cls, raw_dict, private_key=None, canonical_policy=None, use=None):
        """Construct a key access model from the input raw_dict."""
        logger.debug("Constructing Key Access Object with = %s", raw_dict)
        # Construct an empty KeyAccess instance.
        kao = cls()

        kao = add_required_values(kao, raw_dict)

        if kao.type == "remote":
            kao = add_remote_values(kao, raw_dict)
            if use == "upsert":
                kao = add_wrapped_values(
                    kao,
                    raw_dict,
                    private_key=private_key,
                    canonical_policy=canonical_policy,
                )

        elif kao.type == "wrapped":
            kao = add_wrapped_values(
                kao,
                raw_dict,
                private_key=private_key,
                canonical_policy=canonical_policy,
            )
        #
        # elif kao.type == "remoteWrapped":
        #     logger.debug('REMOTE-WRAPPED key access object')
        #     kao = add_remote_values(kao,
        #                             raw_dict)
        #     kao = add_wrapped_values(kao,
        #                              raw_dict,
        #                              private_key=private_key,
        #                              canonical_policy=canonical_policy)

        else:
            msg = f"Unknown key access type = {kao.type}"
            logger.error(msg)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError(msg)

        kao = add_metadata_values(
            kao, raw_dict, wrapped_key=kao.wrapped_key, private_key=private_key
        )

        logger.debug("Key Access Object Complete = %s", kao)
        return kao

    def to_dict(self):
        """Construct a dict representation of this model, if possible."""
        resp = {}
        if self.type is not None:
            resp["type"] = self.type
        if self.url is not None:
            resp["url"] = self.url
        if self.protocol is not None:
            resp["protocol"] = self.protocol
        if self.policy_sync_options is not None:
            resp["policySyncOptions"] = self.policy_sync_options
        return resp

    @property
    def type(self):
        """Get the type."""
        logger.debug("Accessing type = %s", self.__type)
        return self.__type

    @type.setter
    def type(self, value):
        """Set the type."""
        logger.debug("Setting type to = %s", value)
        if value not in KEY_ACCESS_TYPES:
            logger.error("Key access type '%s' is invalid", value)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError("Invalid type")
        self.__type = value

    @property
    def url(self):
        """Get the url."""
        logger.debug("Accessing url = %s", self.__url)
        return self.__url

    @url.setter
    def url(self, value):
        """Set the url."""
        logger.debug("Setting url to = %s", value)
        valid = attr_authority_check.match(value)
        if not valid:
            logger.error("url '%s' is invalid", value)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError("Invalid url")
        self.__url = value

    @property
    def policy_binding(self):
        """Get the policy_binding."""
        logger.debug("Accessing binding = %s", self.__policy_binding)
        return self.__policy_binding

    @policy_binding.setter
    def policy_binding(self, value):
        """Set the policy binding."""
        logger.debug("Setting policy binding to = %s", value)
        self.__policy_binding = value

    @property
    def protocol(self):
        """Get the protocol."""
        logger.debug("Accessing protocol = %s", self.__protocol)
        return self.__protocol

    @protocol.setter
    def protocol(self, value):
        """Set the protocol."""
        logger.debug("Setting protocol to = %s", value)
        if value not in PROTOCOL_TYPES:
            msg = f"Invalid protocol = {value}; must be type {PROTOCOL_TYPES}"
            logger.error(msg)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError(msg)
        self.__protocol = value

    @property
    def wrapped_key(self):
        """Get the wrapped key (may be None)."""
        logger.debug("Accessing wrapped key = %s", self.__wrapped_key)
        return self.__wrapped_key

    @wrapped_key.setter
    def wrapped_key(self, value):
        """Set the wrapped_key options.

        Must be String instance (or None?).
        """
        logger.debug("Setting wrapped_key to = %s", value)
        # Might need to add None as a valid value for Wrapped_Key
        if not (isinstance(value, str) or (value is None)):
            msg = f"Wrapped key must be string, got {value}"
            logger.error(msg)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError(msg)
        self.__wrapped_key = value

    @property
    def metadata(self):
        """Get the meta-data (may be None)."""
        logger.debug("Accessing metadata = %s", self.__metadata)
        return self.__metadata

    @metadata.setter
    def metadata(self, value):
        """Set the metadata.

        Must be MetaData instance or None.
        """
        logger.debug("Setting metadata = %s", value)

        if (value is None) or (not isinstance(value, MetaData)):
            msg = f"Invalid metadata object, got {value}"
            logger.error(msg)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError(msg)

        self.__metadata = value

    @property
    def policy_sync_options(self):
        """Get policy_sync_options."""
        logger.debug("Accessing binding = %s", self.__policy_sync_options)
        return self.__policy_sync_options

    @policy_sync_options.setter
    def policy_sync_options(self, value):
        """Set policy_sync_options."""
        logger.debug("Setting policy_sync_options to = %s", value)
        self.__policy_sync_options = value
