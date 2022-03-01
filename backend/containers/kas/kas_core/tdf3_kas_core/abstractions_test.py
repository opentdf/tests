"""Abstract rewrap plugin test."""

from .abstractions import (
    AbstractHealthzPlugin,
    AbstractPlugin,
    AbstractRewrapPlugin,
    AbstractUpsertPlugin,
)


def test_abstract_healthz_plunging():
    """Test the constructor and stub update method."""
    actual = AbstractHealthzPlugin()
    assert isinstance(actual, AbstractPlugin)
    assert isinstance(actual, AbstractHealthzPlugin)
    v = actual.healthz(probe="whatever")
    assert v == None


def test_abstract_rewrap_pluging():
    """Test the constructor and stub update method."""
    actual = AbstractRewrapPlugin()
    assert isinstance(actual, AbstractPlugin)
    assert isinstance(actual, AbstractRewrapPlugin)
    (req, res) = actual.update({"foo": 1}, {"bar": 2})
    assert req == {"foo": 1}
    assert res == {"bar": 2}


def test_abstract_upsert_pluging():
    """Test the constructor and stub update method."""
    actual = AbstractUpsertPlugin()
    assert isinstance(actual, AbstractPlugin)
    assert isinstance(actual, AbstractUpsertPlugin)
    actual = actual.upsert()
    assert actual == ""
