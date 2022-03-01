"""Test Data attributes."""

import pytest  # noqa: F401

from .data_attributes import DataAttributes
from .attribute_value import AttributeValue


def test_data_attributes_constructor():
    """Test the basic constructor."""
    actual = DataAttributes()
    assert isinstance(actual, DataAttributes)


def test_data_attributes_load_raw():
    """Test data_attributes_load_raw."""
    raw_list = [
        {
            "attribute": "https://example.com/attr/Classification/value/TS",
            "displayName": "does not matter",
        }
    ]
    da = DataAttributes()
    da.load_raw(raw_list)
    actual = da.get("https://example.com/attr/Classification/value/TS")
    assert isinstance(actual, AttributeValue)
    assert actual.namespace == "https://example.com/attr/Classification"
    assert actual.value == "TS"


def test_data_attributes_export_raw():
    """Test data_attributes_export_raw."""
    expected = [{"attribute": "https://example.com/attr/Classification/value/TS"}]
    da = DataAttributes()
    da.load_raw(expected)
    # Note - order is not preserved, so comparing actual to expected is
    # a little difficult for multiple attributes. Hence one item.
    actual = da.export_raw()
    assert actual == expected
