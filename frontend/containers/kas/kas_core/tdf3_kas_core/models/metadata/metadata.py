"""The Metadata model represents /rewrap metadata."""

import base64
import json
import copy
import logging

from tdf3_kas_core.util import aes_gcm_decrypt

logger = logging.getLogger(__name__)


class MetaData(object):
    """Represents /rewrap service metadata.

    The metadata model is going to be handed off to policy plugins, so
    some effort has been made to toughen up the internal representation
    to avoid bugs from people inadvertently changing the internal data
    values.  Since this is python there is no enforcable way to do this,
    but the @property and @.setter methods are considered a best practice.
    """

    @classmethod
    def from_raw(cls, raw_metadata, secret):
        """Decrypt metadata and return a metadata model.

        Or raise an error if something goes wrong.
        """
        logger.debug("Unpacking raw metadata = %s", raw_metadata)

        iv = base64.b64decode(raw_metadata["iv"])
        logger.debug("IV = %s", iv)

        ciphertext = base64.b64decode(raw_metadata["ciphertext"])
        logger.debug("ciphertext = %s", ciphertext)

        # Remove 12 bytes of the prepended IV that comes with the metadata
        pure_ciphertext = ciphertext[12:]

        logger.debug("pure_ciphertext = %s", pure_ciphertext)

        data = aes_gcm_decrypt(pure_ciphertext, secret, iv)

        logger.debug("metaData = %s", data)

        if data:
            data_dict = json.loads(bytes.decode(data))
        else:
            data_dict = None

        logger.debug("Metadata dict = %s", data_dict)

        return cls(data_dict)

    def __init__(self, data_dict=None):
        """Construct with a static dictionary."""
        if data_dict is None:
            self.__data = {}
        else:
            self.__data = data_dict

    def get(self, key):
        """Get the value that goes with the key, if any."""
        logger.debug("Getting data field %s from metadata", key)
        if key in self.__data:
            logger.debug("data['%s']' = %s", key, self.__data[key])
            return copy.deepcopy(self.__data[key])
        else:
            return None

    def has(self, key):
        """Check if key exists."""
        exists = key in self.__data
        logger.debug("key '%s' exists = %s", key, exists)
        return exists

    @property
    def data(self):
        """Provide a deep copy of the data to protect .__data."""
        logger.debug("Providing copy of metadata data")
        return copy.deepcopy(self.__data)

    @data.setter
    def data(self, new_data):
        """Noop to protect .__data."""
        logger.warning("attempt to set data on a metadata model")
        pass
