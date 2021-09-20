import json
import logging
import os

from .errors import Error

logger = logging.getLogger(__name__)

WORKING_DIR = os.getcwd()
CONFIG_PATH = os.path.join(WORKING_DIR, "config")
PRIVATE_KEY_PATH = os.path.join(CONFIG_PATH, "key_stash", "eas-private.pem")
DEFAULTS_PATH = os.path.join(CONFIG_PATH, "defaults.json")

config_defaults = {}
with open(DEFAULTS_PATH, "r") as f:
    config_defaults = json.load(f)


def _value_to_boolean(value):
    """Convert an unknown value to boolean. Accepts:
        *   Python or json 'bool' types (returns actual value)
        *   String 'true' or 'false' (case insensitive, returns appropriate boolean)
    None or other values log warning and return False.
    This should move to an EAS/KAS shared library when we add one."""
    if value is None:
        logger.warning("_value_to_boolean: no value received, returning false")
        return False
    if type(value) is bool:
        return value
    try:
        if value.lower() == "false":
            return False
        elif value.lower() == "true":
            return True
    except (AttributeError, ValueError):
        # No Op
        None
    logger.warning(
        "_value_to_boolean: Invalid boolean; defaulting to false. Requires 'true' or 'false' string or json boolean type. Received type: {}, value: {}".format(
            type(value), value
        )
    )
    return False


class EASConfig(object):
    """This class manages loading of configurations.
    The class will attempt load an item using the following priority:
    1. Load Cached value (if previously loaded)
    2. Load from system environment variable
    3. Load from defaults.json file
    Class is read only"""

    __instance = None

    @staticmethod
    def get_instance():
        if EASConfig.__instance == None:
            EASConfig()
        return EASConfig.__instance

    def __init__(self):
        if EASConfig.__instance != None:
            raise Error("EASConfig is a singleton")
        else:
            EASConfig.__instance = self
            self.cache = {}

    def load_items(self, item_names):
        """load each environment variable in the provided list"""
        for item_name in item_names:
            self.load_item(item_name)

    def load_item(self, item_name):
        """load one environment variable from env vars.
        If missing, check default.
        If no default, report error"""
        item_value = os.getenv(item_name, None)
        if item_value == None:
            if item_name in config_defaults:
                item_value = config_defaults[item_name]
            else:
                logger.error(
                    f"Error: environment variable {item_name} is required to be set"
                )
        self.cache[item_name] = item_value
        return item_value

    def get_item(self, item_name):
        """Return one config. If not found in cache, attempt load."""
        if item_name in self.cache:
            return self.cache[item_name]
        return self.load_item(item_name)

    def get_item_boolean(self, item_name):
        return _value_to_boolean(self.get_item(item_name))
