"""Test the Authority Namespace model."""


import pytest  # noqa: F401

from .authority_namespace import AuthorityNamespace
from ...errors import MalformedAuthorityNamespaceError

EXAMPLE1_COM = "https://example1.com"
EXAMPLE2_COM = "https://example2.com"


def test_namespace_constructor():
    """Test namespace."""
    isDefault = False
    actual = AuthorityNamespace(EXAMPLE1_COM, isDefault)
    assert isinstance(actual, AuthorityNamespace)
    assert actual.namespace == EXAMPLE1_COM
    assert actual.isDefault is isDefault

    with pytest.raises(MalformedAuthorityNamespaceError):
        # Should not be blank:
        AuthorityNamespace("", False)

    # Should fix uri if it ends in slash:
    an = AuthorityNamespace(f"{EXAMPLE1_COM}/", False)
    assert an.namespace == EXAMPLE1_COM

    ns = AuthorityNamespace(EXAMPLE1_COM, False, displayName="My Example")
    assert ns.displayName == "My Example"


def test_namespace_is_default():
    """Test namespace."""
    isDefault = False
    test_case = AuthorityNamespace(EXAMPLE1_COM, isDefault)
    expected = True
    test_case.isDefault = True
    actual = test_case.isDefault
    assert actual == expected


def test_namespace_equality_hash():
    """Test namespace."""
    base = AuthorityNamespace(EXAMPLE1_COM, False)
    same = AuthorityNamespace(EXAMPLE1_COM, False)
    wrong = AuthorityNamespace(EXAMPLE2_COM, False)

    assert base == same
    assert base != wrong
    wrong = AuthorityNamespace(EXAMPLE2_COM, False)

    assert base.__hash__() == same.__hash__()
    assert base.__hash__() != wrong.__hash__()


def test_namespace_import_export():
    """Test namespace."""
    expected = {
        "namespace": EXAMPLE1_COM,
        "isDefault": True,
        "displayName": "Example One",
    }
    namespace = AuthorityNamespace.from_raw(expected)
    assert isinstance(namespace, AuthorityNamespace)
    actual = namespace.to_raw()
    assert len(actual.keys()) == 3
    assert actual["namespace"] == expected["namespace"]
    assert actual["isDefault"] == expected["isDefault"]
    assert actual["displayName"] == expected["displayName"]
