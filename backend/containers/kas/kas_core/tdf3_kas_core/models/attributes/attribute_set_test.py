"""Test AttributeSet."""

import pytest

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_value import AttributeValue
from .attribute_set import AttributeSet


def test_attribute_value_set_constructor():
    """Test constructor."""
    actual = AttributeSet()
    assert isinstance(actual, AttributeSet)
    assert len(actual.values) == 0


def test_attribute_value_set_immutability():
    """Test immutability."""
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    B = AttributeValue("https://www.virtru.com/attr/NTK/value/B")
    actual = AttributeSet()
    actual.values = set([A, B])
    assert len(actual.values) == 0


# ================ CRUD stuff ===============================


def test_attribute_set_add():
    """Test add and attributes getter."""
    test_set = AttributeSet()
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    assert len(test_set.values) == 1
    assert A in test_set.values


def test_attribute_set_add_non_attribute():
    """Test add and attributes getter."""
    test_set = AttributeSet()
    with pytest.raises(InvalidAttributeError):
        test_set.add("https://www.virtru.com/attr/NTK/value/A")


def test_attribute_set_get_exists():
    """Test add and attributes getter."""
    test_set = AttributeSet()
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    assert A is test_set.get(A.attribute)


def test_attribute_set_get_doesnt_exist():
    """Test add and attributes getter."""
    test_set = AttributeSet()
    actual = test_set.get("https://www.virtru.com/attr/NTK/value/B")
    assert actual is None


def test_attribute_set_remove_existing():
    """Test add and attributes getter."""
    test_set = AttributeSet()
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    actual = test_set.remove(A.attribute)
    assert len(test_set.values) == 0
    assert actual is A


def test_attribute_set_remove_non_existing():
    """Test add and attributes getter."""
    test_set = AttributeSet()
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    actual = test_set.remove("https://www.virtru.com/attr/NTK/value/B")
    assert len(test_set.values) == 1
    assert actual is None


# =============== Attribute clusters ==================================


def test_attribute_set_get_clusters():
    """Test cluster get. Returns a set of cluster objects."""
    test_set = AttributeSet()

    A = AttributeValue("https://www.virtru.com/attr/alpha/value/A")
    B = AttributeValue("https://www.virtru.com/attr/alpha/value/B")

    P = AttributeValue("https://www.virtru.com/attr/beta/value/P")
    Q = AttributeValue("https://www.virtru.com/attr/beta/value/Q")
    R = AttributeValue("https://www.virtru.com/attr/beta/value/R")

    W = AttributeValue("https://www.virtru.com/attr/gamma/value/W")
    X = AttributeValue("https://www.virtru.com/attr/gamma/value/X")
    Y = AttributeValue("https://www.virtru.com/attr/gamma/value/Y")
    Z = AttributeValue("https://www.virtru.com/attr/gamma/value/Z")

    #  Insert in random orddr
    test_set.add(Y)
    test_set.add(Z)
    test_set.add(Q)
    test_set.add(B)
    test_set.add(P)
    test_set.add(X)
    test_set.add(R)
    test_set.add(W)
    test_set.add(A)

    namespaces = [
        "https://www.virtru.com/attr/alpha",
        "https://www.virtru.com/attr/beta",
        "https://www.virtru.com/attr/gamma",
    ]
    assert len(test_set.clusters) == 3
    for cluster in test_set.clusters:
        assert cluster.namespace in namespaces
        if cluster.namespace == "https://www.virtru.com/attr/alpha":
            assert cluster.values == set([A, B])
        if cluster.namespace == "https://www.virtru.com/attr/beta":
            assert cluster.values == set([P, Q, R])
        if cluster.namespace == "https://www.virtru.com/attr/gamma":
            assert cluster.values == set([W, X, Y, Z])


def test_attribute_set_get_cluster_namespaces():
    """Test cluster namespaces. Returns a list of namespace keys."""
    test_set = AttributeSet()

    A = AttributeValue("https://www.virtru.com/attr/alpha/value/A")
    B = AttributeValue("https://www.virtru.com/attr/alpha/value/B")

    P = AttributeValue("https://www.virtru.com/attr/beta/value/P")
    Q = AttributeValue("https://www.virtru.com/attr/beta/value/Q")
    R = AttributeValue("https://www.virtru.com/attr/beta/value/R")

    W = AttributeValue("https://www.virtru.com/attr/gamma/value/W")
    X = AttributeValue("https://www.virtru.com/attr/gamma/value/X")
    Y = AttributeValue("https://www.virtru.com/attr/gamma/value/Y")
    Z = AttributeValue("https://www.virtru.com/attr/gamma/value/Z")

    #  Insert in random orddr
    test_set.add(Y)
    test_set.add(Z)
    test_set.add(Q)
    test_set.add(B)
    test_set.add(P)
    test_set.add(X)
    test_set.add(R)
    test_set.add(W)
    test_set.add(A)

    alpha = "https://www.virtru.com/attr/alpha"
    beta = "https://www.virtru.com/attr/beta"
    gamma = "https://www.virtru.com/attr/gamma"

    assert test_set.cluster_namespaces == set([alpha, beta, gamma])


def test_attribute_set_cluster_getter():
    """Test immutability."""
    test_set = AttributeSet()

    A = AttributeValue("https://www.virtru.com/attr/alpha/value/AAA")
    B = AttributeValue("https://www.virtru.com/attr/alpha/value/BBB")

    P = AttributeValue("https://www.virtru.com/attr/beta/value/P")
    Q = AttributeValue("https://www.virtru.com/attr/beta/value/Q")
    R = AttributeValue("https://www.virtru.com/attr/beta/value/R")

    W = AttributeValue("https://www.virtru.com/attr/gamma/value/W")
    X = AttributeValue("https://www.virtru.com/attr/gamma/value/X")
    Y = AttributeValue("https://www.virtru.com/attr/gamma/value/Y")
    Z = AttributeValue("https://www.virtru.com/attr/gamma/value/Z")

    #  Insert in random orddr
    test_set.add(Y)
    test_set.add(Z)
    test_set.add(Q)
    test_set.add(B)
    test_set.add(P)
    test_set.add(X)
    test_set.add(R)
    test_set.add(W)
    test_set.add(A)

    actual_alpha = test_set.cluster("https://www.virtru.com/attr/alpha")
    actual_beta = test_set.cluster("https://www.virtru.com/attr/beta")
    actual_gamma = test_set.cluster("https://www.virtru.com/attr/gamma")

    assert actual_alpha.values == set([A, B])
    assert actual_beta.values == set([P, Q, R])
    assert actual_gamma.values == set([W, X, Y, Z])

    test_set.remove(R.attribute)
    test_set.remove(W.attribute)
    test_set.remove(A.attribute)

    actual_alpha = test_set.cluster("https://www.virtru.com/attr/alpha")
    actual_beta = test_set.cluster("https://www.virtru.com/attr/beta")
    actual_gamma = test_set.cluster("https://www.virtru.com/attr/gamma")

    assert actual_alpha.values == set([B])
    assert actual_beta.values == set([P, Q])
    assert actual_gamma.values == set([X, Y, Z])
