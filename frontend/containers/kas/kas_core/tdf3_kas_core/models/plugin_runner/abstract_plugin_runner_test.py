"""Abstract plugin runner test."""

import pytest

from tdf3_kas_core.errors import PluginIsBadError
from tdf3_kas_core.abstractions import (
    AbstractRewrapPlugin,
    AbstractUpsertPlugin,
)
from .abstract_plugin_runner import AbstractPluginRunner


@pytest.fixture
def rewrap_plugins():
    """Generate a list of dummy plugins."""
    yield [AbstractRewrapPlugin(), AbstractRewrapPlugin()]


@pytest.fixture
def upsert_plugins():
    """Generate a list of dummy plugins."""
    yield [AbstractUpsertPlugin(), AbstractUpsertPlugin()]


@pytest.fixture
def mixed_plugins():
    """Generate a list of dummy plugins."""
    yield [AbstractUpsertPlugin(), AbstractRewrapPlugin()]


def dummy_test_func(plugin):
    """Test dummy function."""
    return True


def rewrap_test_func(plugin):
    """Test to see if plugin is rewrap type."""
    return isinstance(plugin, AbstractRewrapPlugin)


def upsert_test_func(plugin):
    """Test to see if plugin is upsert type."""
    return isinstance(plugin, AbstractUpsertPlugin)


msg = "some words"

# ================ TESTS ==============================================


def test_abstract_plugin_runner_constructor_empty():
    """Test the constructor."""
    plugins = []
    actual = AbstractPluginRunner(plugins, dummy_test_func, msg)
    assert isinstance(actual, AbstractPluginRunner)


def test_abstract_plugin_runner_constructor_rewraps(rewrap_plugins):
    """Test the constructor."""
    actual = AbstractPluginRunner(rewrap_plugins, rewrap_test_func, msg)
    assert isinstance(actual, AbstractPluginRunner)


def test_abstract_plugin_runner_constructor_upserts(upsert_plugins):
    """Test the constructor."""
    actual = AbstractPluginRunner(upsert_plugins, dummy_test_func, msg)
    assert isinstance(actual, AbstractPluginRunner)


def test_abstract_plugin_runner_constructor_mixed_fails_rewrap(mixed_plugins):
    """Test the constructor."""
    with pytest.raises(PluginIsBadError):
        AbstractPluginRunner(mixed_plugins, rewrap_test_func, msg)


def test_abstract_plugin_runner_constructor_mixed_fails_upsert(mixed_plugins):
    """Test the constructor."""
    with pytest.raises(PluginIsBadError):
        AbstractPluginRunner(mixed_plugins, upsert_test_func, msg)


def test_abstract_plugin_runner_constructor_fail_solo_plugin(rewrap_plugins):
    """Test the constructor."""
    with pytest.raises(Exception):
        AbstractPluginRunner(rewrap_plugins[0], rewrap_test_func, msg)


def test_plugin_runner_constructor_fail_with_not_plugin():
    """Test the constructor."""
    plugins = [AbstractRewrapPlugin(), AbstractRewrapPlugin(), "not a plugin"]
    with pytest.raises(PluginIsBadError):
        AbstractPluginRunner(plugins, rewrap_test_func, msg)


def test_abstract_plugin_runner_constructor_no_args_fail():
    """Test the constructor."""
    with pytest.raises(Exception):
        AbstractPluginRunner()


def test_abstract_plugin_runner_constructor_just_plugins_fail():
    """Test the constructor."""
    with pytest.raises(Exception):
        AbstractPluginRunner([])


def test_abstract_plugin_runner_constructor_no_test_fail():
    """Test the constructor."""
    with pytest.raises(Exception):
        AbstractPluginRunner([], "")


def test_abstract_plugin_runner_constructor_no_msg_fail():
    """Test the constructor."""
    with pytest.raises(Exception):
        AbstractPluginRunner([], dummy_test_func)
