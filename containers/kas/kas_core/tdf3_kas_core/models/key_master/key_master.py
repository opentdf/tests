"""The key master manages the keys."""

import copy
import logging

from tdf3_kas_core.util import get_public_key_from_disk
from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import get_symmetric_key_from_disk
from tdf3_kas_core.util import get_public_key_from_pem
from tdf3_kas_core.util import get_private_key_from_pem

from tdf3_kas_core.errors import KeyNotFoundError

logger = logging.getLogger(__name__)


KEY_TYPES = ["PUBLIC", "PRIVATE", "SYMMETRIC"]


def get_key_from_pem(type, pem):
    """Get an operational key from a PEM encoded string."""
    if type == "PUBLIC":
        return get_public_key_from_pem(pem)
    elif type == "PRIVATE":
        return get_private_key_from_pem(pem)
    elif type == "SYMMETRIC":
        return pem
    else:
        raise KeyNotFoundError("Wrong key type")


def get_key_from_disk(type, path):
    """Get an operational key from disk."""
    if type == "PUBLIC":
        return get_public_key_from_disk(path)
    elif type == "PRIVATE":
        return get_private_key_from_disk(path)
    elif type == "SYMMETRIC":
        return get_symmetric_key_from_disk(path)
    else:
        raise KeyNotFoundError("Wrong key type")


def get_export_bytes_from_disk(type, path):
    """Get an exportable string from disk."""
    if type == "PUBLIC":
        return get_public_key_from_disk(path, as_pem=True)
    elif type == "PRIVATE":
        return get_private_key_from_disk(path, as_pem=True)
    elif type == "SYMMETRIC":
        return get_symmetric_key_from_disk(path)  # already exportable
    else:
        raise KeyNotFoundError("Wrong key type")


class KeyMaster(object):
    """KeyMaster provides keys."""

    def __init__(self):
        """Construct an empty key master.

        Keys is a dictionary containing objects of the form:
            {
                name: <name string>  # Must be unique
                type: <type string>  # Must be in KEY_TYPES
                path: <path string>  # (optional) Absolute path if from disk
                key: <key string>    # (optional) String form, e.g. PEM
            }

        The keys dictionary is indexed by the name strings.
        """
        self.__keys = {}

    @property
    def keys(self):
        """Get the key dictionary.

        The returned object is a copy to avoid corruption of the database.
        It is also not actionable by iteself; though the key files could
        be messed with since the paths are known.
        """
        return copy.deepcopy(self.__keys)

    @keys.setter
    def keys(self, new_keys):
        """Noop for key setting."""
        pass

    def get_key(self, key_name):
        """Get a key object that can be used to unlock things."""
        if key_name in self.__keys:
            key_obj = self.__keys[key_name]

            if "type" not in key_obj:
                logger.error("Type defective key record = %s", key_name)
                raise KeyNotFoundError("Key record is defective")
            type = key_obj["type"]

            if "pem" in key_obj:
                return get_key_from_pem(type, key_obj["pem"])
            elif "path" in key_obj:
                return get_key_from_disk(type, key_obj["path"])
            else:
                logger.error("Defective key record = %s", key_name)
                raise KeyNotFoundError("Key record is defective")
        else:
            msg = f"Key '{key_name}' not found in get_key."
            # This is not necessarily a critical failure,
            # in some cases we fetch the key if it is not cached
            # with key_manager.
            logger.warning(msg)
            raise KeyNotFoundError(msg)

    def get_export_string(self, key_name):
        """Get an exportable key string."""
        if key_name in self.__keys:
            key_obj = self.__keys[key_name]

            if "pem" in key_obj:
                return bytes.decode(key_obj["pem"])

            if "type" not in key_obj:
                logger.error("Type defective key record = %s", key_name)
                raise KeyNotFoundError("Key record is defective")
            if "path" not in key_obj:
                logger.error("Defective key record = %s", key_name)
                raise KeyNotFoundError("Key record is defective")

            return bytes.decode(
                get_export_bytes_from_disk(key_obj["type"], key_obj["path"])
            )
        else:
            msg = f"Key '{key_name}' not found among {self.__keys}"
            logger.error(msg)
            raise KeyNotFoundError(msg)

    def set_key_pem(self, key_name, key_type, pem_key):
        """Set the pem key directly into the store."""
        if key_type not in KEY_TYPES:
            raise KeyNotFoundError("Attempt to load key with defective type")

        key_obj = {"name": key_name, "type": key_type, "pem": pem_key}
        self.__keys[key_name] = key_obj

    def set_key_path(self, key_name, key_type, key_path):
        """Set the key indirectly by reading a file into the store."""
        if key_type not in KEY_TYPES:
            raise KeyNotFoundError("Attempt to load key with defective type")

        key_obj = {"name": key_name, "type": key_type, "path": key_path}
        self.__keys[key_name] = key_obj
