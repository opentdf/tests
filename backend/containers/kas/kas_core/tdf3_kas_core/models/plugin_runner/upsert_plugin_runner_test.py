"""Abstract upsert plugin runner test."""

import pytest

from tdf3_kas_core.abstractions import AbstractUpsertPlugin

from .upsert_plugin_runner import UpsertPluginRunner


@pytest.fixture
def plugins():
    """Generate a list of dummy plugins."""
    yield [AbstractUpsertPlugin(), AbstractUpsertPlugin()]


@pytest.fixture
def req(policy, entity, key_access_remote, context):
    """Generate a req object."""
    yield {
        "policy": policy,
        "entity": entity,
        "keyAccess": key_access_remote,
        "context": context,
    }


# ========= TESTS ==========================================


def test_plugin_runner_constructor_empty():
    """Test the constructor."""
    actual = UpsertPluginRunner()
    assert isinstance(actual, UpsertPluginRunner)


def test_plugin_runner_constructor_with_plugins(plugins):
    """Test the constructor."""
    actual = UpsertPluginRunner(plugins)
    assert isinstance(actual, UpsertPluginRunner)


def test_plugin_runner_update_no_plugins(policy, entity, key_access_remote, context):
    """Test the update function."""
    pr = UpsertPluginRunner()
    actual = pr.upsert(policy, entity, key_access_remote, context)
    assert actual == []


def test_plugin_runner_upsert_dummy_plugins(
    plugins, policy, entity, key_access_remote, context
):
    """Test the upsert function with no load."""
    pr = UpsertPluginRunner(plugins)
    actual = pr.upsert(
        policy=policy, entity=entity, key_access=key_access_remote, context=context
    )
    assert len(actual) != 0


def test_plugin_runner_upsert_test_plugin(
    plugins, policy, entity, key_access_remote, context
):
    """Test the upsert function."""

    class test_plugin_one(AbstractUpsertPlugin):
        """Mock plugin."""

        def upsert(self, **kwargs):
            """Run test upsert."""
            print(kwargs)
            assert kwargs["policy"] == policy
            assert kwargs["entity"] == entity
            assert kwargs["key_access"] == key_access_remote
            assert kwargs["context"] == context
            return "thing one"

    class test_plugin_two(AbstractUpsertPlugin):
        """Mock plugin."""

        def upsert(self, **kwargs):
            """Run test upsert."""
            print(kwargs)
            assert kwargs["policy"] == policy
            assert kwargs["entity"] == entity
            assert kwargs["key_access"] == key_access_remote
            assert kwargs["context"] == context
            return "thing two"

    plugins.append(test_plugin_one())
    plugins.append(test_plugin_two())

    pr = UpsertPluginRunner(plugins)
    actual = pr.upsert(
        policy=policy, entity=entity, key_access=key_access_remote, context=context
    )

    assert len(actual) != 0
