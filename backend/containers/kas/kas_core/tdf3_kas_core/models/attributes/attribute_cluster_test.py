"""Test AttributeCluster."""

import pytest

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_value import AttributeValue
from .attribute_cluster import AttributeCluster


def test_attribute_cluster_constructor():
    """Test constructor."""
    actual = AttributeCluster("https://www.virtru.com/attr/NTK")
    assert isinstance(actual, AttributeCluster)


def test_attribute_cluster_namespace_getter():
    """Test constructor."""
    expected = "https://www.virtru.com/attr/NTK"
    actual = AttributeCluster(expected)
    assert actual.namespace == expected


def test_attribute_cluster_namespace_immutability():
    """Test immutability."""
    expected = "https://www.virtru.com/attr/NTK"
    actual = AttributeCluster(expected)
    actual.namespace = "This is not my beautiful house."
    assert actual.namespace == expected


def test_attribute_cluster_value_immutability():
    """Test immutability."""
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    B = AttributeValue("https://www.virtru.com/attr/NTK/value/B")
    actual = AttributeCluster("https://www.virtru.com/attr/NTK")
    actual.values = set([A, B])
    assert len(actual.values) == 0


# ================ CRUD stuff ===============================


def test_attribute_cluster_add():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    assert len(test_set.values) == 1


def test_attribute_cluster_size():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    assert test_set.size == 0
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    assert test_set.size == 1


def test_attribute_cluster_add_non_attribute():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    with pytest.raises(InvalidAttributeError):
        test_set.add("https://www.virtru.com/attr/NTK/value/A")


def test_attribute_cluster_get_exists():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    assert A is test_set.get(A.attribute)


def test_attribute_cluster_get_doesnt_exist():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    actual = test_set.get("https://www.virtru.com/attr/NTK/value/B")
    assert actual is None


def test_attribute_cluster_remove_existing():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    actual = test_set.remove(A.attribute)
    assert test_set.size == 0
    assert actual is A


def test_attribute_cluster_remove_non_existing():
    """Test add and attributes getter."""
    test_set = AttributeCluster("https://www.virtru.com/attr/NTK")
    A = AttributeValue("https://www.virtru.com/attr/NTK/value/A")
    test_set.add(A)
    actual = test_set.remove("https://www.virtru.com/attr/NTK/value/B")
    assert test_set.size == 1
    assert actual is None
