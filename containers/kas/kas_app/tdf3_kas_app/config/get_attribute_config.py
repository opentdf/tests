"""This small utility function reads and decodes the config file."""

import os
import json


def get_attribute_config():
    """Read and decode the config file."""
    curr_dir = os.path.dirname(__file__)
    path = os.path.join(curr_dir, "./attribute-config.json")

    with open(path) as config_file:
        attribute_policy_config_dict = json.loads(config_file.read())

    return attribute_policy_config_dict
