"""Test Data attributes."""

import pytest

from tdf3_kas_core.errors import AttributePolicyConfigError

from .attribute_policy import AttributePolicy

from .attribute_policy import ALL_OF
from .attribute_policy import ANY_OF
from .attribute_policy import HIERARCHY


def test_attribute_policy_constructor_with_valid_namespace_defaults_to_AllOF():
    """Test constructor."""
    namespace = "https://www.example.com/attr/foo"
    actual = AttributePolicy(namespace)
    assert isinstance(actual, AttributePolicy)
    assert actual.rule == ALL_OF


def test_attribute_policy_constructor_with_AllOf_rule():
    """Test constructor."""
    namespace = "https://www.example.com/attr/foo"
    actual = AttributePolicy(namespace, ALL_OF)
    assert isinstance(actual, AttributePolicy)
    assert actual.rule == ALL_OF


def test_attribute_policy_constructor_with_AnyOf_rule():
    """Test constructor."""
    namespace = "https://www.example.com/attr/foo"
    actual = AttributePolicy(namespace, ANY_OF)
    assert isinstance(actual, AttributePolicy)
    assert actual.rule == ANY_OF


def test_attribute_policy_constructor_with_Hierarchical_rule():
    """Test constructor."""
    namespace = "https://www.example.com/attr/classification"
    order = ["TS", "S", "C", "U"]
    actual = AttributePolicy(namespace, HIERARCHY, order=order)
    assert isinstance(actual, AttributePolicy)
    assert actual.rule == HIERARCHY
    # Internally, the order is represented by a upper-cased tuple
    upper_order = ("TS", "S", "C", "U")
    assert actual.options == {"order": upper_order}


def test_attribute_policy_constructor_fail_with_no_hierarchy_order():
    """Test constructor."""
    namespace = "https://www.example.com/attr/classification"
    with pytest.raises(AttributePolicyConfigError):
        AttributePolicy(namespace, HIERARCHY)


def test_attribute_policy_constructor_with_unknown_rule():
    """Test constructor."""
    with pytest.raises(AttributePolicyConfigError):
        AttributePolicy("https://www.example.com/attr/foo", "Unknown_rule")


def test_attribute_policy_constructor_with_no_namespace():
    """Test constructor."""
    with pytest.raises(AttributePolicyConfigError):
        AttributePolicy()


def test_attribute_policy_equal():
    """Test constructor."""
    atr1 = AttributePolicy("https://www.example.com/attr/foo")
    atr2 = AttributePolicy("https://www.example.com/attr/foo")
    assert atr1 == atr2


def test_attribute_policy_equal_case_sensitive():
    """Test constructor."""
    atr1 = AttributePolicy("https://www.ExaMple.com/aTTr/FOo")
    atr2 = AttributePolicy("https://wWw.examPle.com/attr/Foos")
    assert atr1 != atr2
