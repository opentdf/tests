"""Test Config management."""
import logging

import pytest

from .eas_config import EASConfig, _value_to_boolean
from .util import random_string


@pytest.fixture(scope="session")
def eas_config():
    return EASConfig.get_instance()


def test_eas_config_constructor(eas_config):
    """Test creation and singleton behavior"""
    assert isinstance(eas_config, EASConfig)

    # Test singleton enforcement
    with pytest.raises(Exception):
        eas_config = EASConfig()
    eas_config2 = EASConfig.get_instance()
    assert eas_config == eas_config2


def test_eas_config_envvar(eas_config):
    """Test reading configs from environment variable"""
    import os

    item_name = f"EAS_TEMP_{random_string()}"
    item_value = random_string()
    os.environ[item_name] = item_value

    result = eas_config.get_item(item_name)
    assert result == item_value

    # Cleanup: reset environment variable
    os.environ[item_name] = ""
    # For an OS that supports unsetenv(), fully delete env var
    del os.environ[item_name]


def test_eas_config_defaults(eas_config):
    """Test reading configs from defaults.json"""
    assert (
        eas_config.get_item("DEFAULT_ATTRIBUTE_URL")
        == "https://eas.virtru.com/attr/default/value/default"
    )
    # SWAGGER_UI set in defaults.json to True
    assert eas_config.get_item_boolean("SWAGGER_UI")
    assert not eas_config.get_item_boolean("THIS_ITEM_DOES_NOT_EXIST")


def test_eas_config_empty_defaults(eas_config):
    """Test reading configs from defaults.json"""
    assert eas_config.get_item("EAS_ENTITY_ID_HEADER") == ""


def test_eas_load_items(eas_config):
    eas_config.load_items(["EAS_ENTITY_EXPIRATION"])
    assert eas_config.get_item("EAS_ENTITY_EXPIRATION") == {"exp_days": 120}


def test_value_to_boolean():
    assert not _value_to_boolean("0")
    assert not _value_to_boolean("FaLsE")
    assert not _value_to_boolean(None)
    assert not _value_to_boolean("1")  # Numbers not accepted as true
    assert _value_to_boolean("tRuE")
    assert not _value_to_boolean(random_string(30))
    assert _value_to_boolean(True)
    assert not _value_to_boolean(False)
