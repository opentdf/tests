"""Test the Dissem model."""


import json

# from pprint import pprint

from .dissem import Dissem


def test_dissem_empty_construction():
    """Test the constructor."""
    actual = Dissem()
    assert isinstance(actual, Dissem)


def test_dissem_raw_iterable_constructor():
    """Test the .from_list factory method."""
    expected = ["email1@example.com", "email2@example.com", "email3@example.com"]
    dissem = Dissem.from_iterable(expected)
    assert set(dissem.list) == set(expected)


def test_dissem_raw_json_constructor():
    """Test the .from_json factory method."""
    expected = ["email1@example.com", "email2@example.com", "email3@example.com"]
    dissem = Dissem.from_json(json.dumps(expected))
    assert set(dissem.list) == set(expected)


def test_dissem_list_getter_and_setter():
    """See if the list getter and setter are working."""
    expected = ["email1@example.com", "email2@example.com", "email3@example.com"]
    dissem = Dissem()
    dissem.list = expected
    assert set(dissem.list) == set(expected)


def test_dissem_add():
    """See if it adds an email."""
    dissem = Dissem()
    expected1 = "new_email1@example.com"
    expected2 = "new_email2@example.com"
    dissem.add(expected1)
    dissem.add(expected2)
    actual = dissem.list
    assert set(actual) == set([expected1, expected2])


def test_dissem_remove_existing():
    """See if it removes an email."""
    dissem = Dissem()
    expected1 = "new_email1@example.com"
    expected2 = "new_email2@example.com"
    dissem.add(expected1)
    dissem.add(expected2)
    dissem.remove(expected1)
    actual = dissem.list
    assert set(actual) == set([expected2])


def test_dissem_remove_nonexisting():
    """See if it does not crash if email does not exist."""
    dissem = Dissem()
    expected = "other_email@example.com"
    dissem.add(expected)
    dissem.remove("some_email@example.com")
    actual = dissem.list
    assert set(actual) == set([expected])


def test_dissem_contains():
    """Check the 'hasa' method."""
    dissem = Dissem.from_iterable(
        [
            "some_email@example.com",
        ]
    )
    assert dissem.contains("some_email@example.com") is True
    assert dissem.contains("another_email@example.com") is False


def test_dissem_size():
    """Check to see if size works."""
    dissem0 = Dissem.from_iterable([])
    dissem1 = Dissem.from_iterable(["e1@ex.com"])
    dissem2 = Dissem.from_iterable(["e1@ex.com", "e2@ex.com"])
    dissem3 = Dissem.from_iterable(["e1@ex.com", "e2@ex.com", "e3@ex.com"])
    assert dissem0.size == 0
    assert dissem1.size == 1
    assert dissem2.size == 2
    assert dissem3.size == 3


def test_dissem_to_json():
    """Test write to JSON."""
    dissem = Dissem()
    expected = "email@example.com"
    dissem.add(expected)
    actual = dissem.to_json()
    assert actual == '["email@example.com"]'
