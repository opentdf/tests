"""Test the context class."""

from .context import Context


def test_context_constructor():
    """Test empty construction."""
    context = Context()
    assert isinstance(context, Context)


def test_context_add_and_get_string():
    """Test individual add."""
    context = Context()
    context.add("foo", "HELLO WORLD")
    assert context.get("foo") == "HELLO WORLD"


def test_context_add_and_get_scalar():
    """Test individual add."""
    context = Context()
    context.add("foo", 42)
    assert context.get("foo") == 42


def test_context_add_and_get_object():
    """Test individual add."""
    context = Context()
    context.add("foo", {"bar": 42})
    assert context.get("foo") == {"bar": 42}


def test_context_add_and_get_new_list():
    """Test individual add."""
    context = Context()
    context.add("foo", [1, 2, 3])
    assert context.get("foo") == [1, 2, 3]


def test_context_add_and_get_new_tuple():
    """Test individual add."""
    context = Context()
    context.add("foo", (1, 2, 3))
    assert context.get("foo") == [1, 2, 3]


def test_context_add_and_get_new_tuple_and_more():
    """Test individual add."""
    context = Context()
    context.add("foo", (1, 2, 3))
    context.add("Foo", (4, 5, 6))
    assert context.get("FOO") == [1, 2, 3, 4, 5, 6]


def test_context_add_and_get_new_list_then_tuple():
    """Test individual add."""
    context = Context()
    context.add("foo", [1, 2, 3])
    context.add("Foo", (4, 5, 6))
    assert context.get("FOO") == [1, 2, 3, 4, 5, 6]


def test_context_add_and_get_scalar_to_old_scalar():
    """Test individual add."""
    context = Context()
    context.add("foo", 1)
    context.add("foo", 2)
    assert context.get("foo") == [1, 2]


def test_context_add_and_get_scalar_to_old_list():
    """Test individual add."""
    context = Context()
    context.add("foo", 1)
    context.add("foo", 2)
    context.add("foo", 3)
    assert context.get("foo") == [1, 2, 3]


def test_context_add_and_get_objects_to_old_list():
    """Test individual add."""
    context = Context()
    context.add("foo", {"bar": 1})
    context.add("foo", {"bar": 2})
    context.add("foo", {"bar": 3})
    assert context.get("foo") == [{"bar": 1}, {"bar": 2}, {"bar": 3}]


def test_context_add_and_get_new_lists_to_old_list():
    """Test individual add."""
    context = Context()
    context.add("foo", 1)
    context.add("foo", [2, 3])
    context.add("foo", [4, 5])
    assert context.get("foo") == [1, 2, 3, 4, 5]


def test_context_add_and_get_new_tuple_to_old_list():
    """Test individual add."""
    context = Context()
    context.add("foo", 1)
    context.add("foo", (2, 3))
    context.add("foo", (4, 5))
    assert context.get("foo") == [1, 2, 3, 4, 5]


def test_context_has():
    """Test the shallow check has method."""
    context = Context()
    context.add("foo", 1)
    assert context.has("foo") is True
    assert context.has("bar") is False


def test_context_keys():
    """Test individual add."""
    context = Context()
    context.add("foo", 42)
    context.add("bar", 42)
    context.add("gee", 42)
    context.add("haw", 42)
    assert set(context.keys()) == set(["foo", "bar", "gee", "haw"])


def test_context_size():
    """Test individual add."""
    context = Context()
    context.add("foo", 42)
    context.add("bar", 42)
    context.add("gee", 42)
    context.add("haw", 42)
    assert context.size == 4


def test_context_get_object_makes_copy():
    """Test that get returns a copy."""
    context = Context()
    context.add("foo", {"bar": 42})
    # get a copy
    actual1 = context.get("foo")
    assert actual1 == {"bar": 42}
    # Modify the copy
    actual1["bar"] = 897
    assert actual1 == {"bar": 897}
    # See if modification made it into context object
    actual2 = context.get("foo")
    assert actual2 == {"bar": 42}


def test_context_get_tuple_makes_copies():
    """Test that get returns a copy."""
    context = Context()
    context.add("foo", {"bar": 41})
    context.add("foo", {"bar": 42})
    context.add("foo", {"bar": 43})
    # get a copy
    actual1 = context.get("foo")
    assert actual1 == [{"bar": 41}, {"bar": 42}, {"bar": 43}]
    # Modify the copy
    actual1[1]["bar"] = 897
    assert actual1 == [{"bar": 41}, {"bar": 897}, {"bar": 43}]
    # See if modification made it into context object
    actual2 = context.get("foo")
    assert actual2 == [{"bar": 41}, {"bar": 42}, {"bar": 43}]


def test_context_data_getter():
    """Test the data dict getter."""
    expected = {"foo": [{"A": 41}, {"B": 42}, {"C": 43}], "bar": "tuesday"}
    context = Context()
    context.add("foo", {"A": 41})
    context.add("foo", {"B": 42})
    context.add("foo", {"C": 43})
    context.add("bar", "tuesday")
    actual = context.data
    assert actual == expected


def test_context_data_getter_immutability():
    """Test the data dict getter."""
    expected = {"foo": [{"A": 41}, {"B": 42}, {"C": 43}], "bar": "tuesday"}
    context = Context()
    context.add("foo", {"A": 41})
    context.add("foo", {"B": 42})
    context.add("foo", {"C": 43})
    context.add("bar", "tuesday")
    actual = context.data
    assert actual == expected
    actual["bar"] = "wednesday"
    assert context.data == expected


def test_context_data_setter():
    """Test the data dict getter. Should be a noop."""
    expected = {"foo": "bar"}
    context = Context()
    context.add("foo", "bar")
    context.data = {"boy": "howdie"}
    assert context.data == expected
