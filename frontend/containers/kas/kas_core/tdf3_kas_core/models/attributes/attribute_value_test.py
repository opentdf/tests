"""Test AttributeValue."""

import pytest

from tdf3_kas_core.errors import InvalidAttributeError

from .attribute_value import AttributeValue


def test_attribute_value_constructor_with_valid_attribute_string():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    assert isinstance(actual, AttributeValue)


def test_attribute_value_constructor_with_no_attribute_string():
    """Test constructor."""
    with pytest.raises(InvalidAttributeError):
        AttributeValue()


# This test is just to make sure the attribute_validator is installed.
# More detailed attribute checking tests are found in validation_regex.
def test_attribute_validation_regex_with_no_value():
    """Test constructor."""
    with pytest.raises(InvalidAttributeError):
        AttributeValue("https://www.example.com/attr/Foo/value/")


def test_attribute_value_namespace_getter():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    assert actual.namespace == "https://www.example.com/attr/Foo"


def test_attribute_value_namespace_setter():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    actual.namespace = "Betty Lou Bioloski"
    assert actual.namespace == "https://www.example.com/attr/Foo"


def test_attribute_value_value_getter():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    assert actual.value == "Bar"


def test_attribute_value_value_setter():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    actual.value = "Betty Lou Bioloski"
    assert actual.value == "Bar"


def test_attribute_value_attribute_string_getter():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    assert actual.attribute == "https://www.example.com/attr/Foo/value/Bar"


def test_attribute_value_attribute_string_setter():
    """Test constructor."""
    actual = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    actual.attribute = "Betty Lou Bioloski"
    assert actual.attribute == "https://www.example.com/attr/Foo/value/Bar"


def test_attribute_value_equal():
    """Test constructor."""
    v1 = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    v2 = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    assert v1 == v2


def test_attribute_value_equal_namespace_case_insensitive():
    """Test constructor."""
    v1 = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    v2 = AttributeValue("https://www.example.com/attr/Foo/value/Bar")
    assert v1 == v2
