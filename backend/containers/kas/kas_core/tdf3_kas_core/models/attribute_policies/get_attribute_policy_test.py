"""Test Data attributes."""


from .attribute_policy import AttributePolicy
from .get_attribute_policy import get_attribute_policy

from .attribute_policy import ALL_OF  # noqa: F401


def test_get_attribute_policy():
    """Test get_attribute_policy stub."""
    namespace = "https://www.example.com/attr/foo"
    actual = get_attribute_policy(namespace)
    assert isinstance(actual, AttributePolicy)
    assert actual.rule == ALL_OF
