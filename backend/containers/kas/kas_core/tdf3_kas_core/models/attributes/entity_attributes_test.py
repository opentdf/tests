"""Test the EntityAttributes model."""


from .entity_attributes import EntityAttributes
from .attribute_value import AttributeValue


def test_entity_attributes_constructor():
    """Test the basic constructor.

    Should work with no arguments.
    """
    actual = EntityAttributes()
    assert isinstance(actual, EntityAttributes)


def test_entity_attributes_create_from_list():
    """See if it creates from an interable list."""
    ea = EntityAttributes.create_from_list(
        [
            {"attribute": "https://example.com/attr/test-ATTR/value/AAA"},
            {"attribute": "https://example.com/attr/test-ATTR/value/BBB"},
        ]
    )
    actual1 = ea.get("https://example.com/attr/test-ATTR/value/AAA")
    assert isinstance(actual1, AttributeValue)
    assert actual1.namespace == "https://example.com/attr/test-ATTR"
    assert actual1.value == "AAA"

    actual2 = ea.get("https://example.com/attr/test-ATTR/value/BBB")
    assert isinstance(actual2, AttributeValue)
    assert actual2.namespace == "https://example.com/attr/test-ATTR"
    assert actual2.value == "BBB"
