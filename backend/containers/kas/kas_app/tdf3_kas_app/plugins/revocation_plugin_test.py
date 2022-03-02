import pytest

from dataclasses import dataclass
from tdf3_kas_core.errors import AuthorizationError
from .revocation_plugin import RevocationPlugin


@dataclass
class Entity:
    """Class for keeping track of an item in inventory."""

    user_id: str


def req(user_id):
    return {
        "entity": Entity(user_id),
    }


def test_plugin_empty():
    assert RevocationPlugin().update(req("a"), 0) == (req("a"), 0)


def test_plugin_blocks_all():
    with pytest.raises(AuthorizationError):
        RevocationPlugin(blocks=["*"]).update(req("a"), 0)


def test_plugin_allows_someone():
    just_alice = RevocationPlugin(allows=["alice"])
    with pytest.raises(AuthorizationError):
        just_alice.update(req("a"), 0)
    assert just_alice.update(req("alice"), 0) == (req("alice"), 0)


def test_plugin_blocks_and_allows_all():
    just_alice = RevocationPlugin(allows=["*"], blocks=["bob"])
    with pytest.raises(AuthorizationError):
        just_alice.update(req("bob"), 0)
    assert just_alice.update(req("alice"), 0) == (req("alice"), 0)
