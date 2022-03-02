"""Test the create context helper function."""


from werkzeug.datastructures import Headers

from .create_context import create_context
from tdf3_kas_core.models import Context


def test_create_context():
    """Test the create context header function."""
    # create a werkzeug.datastructures.Header object, as Flask produces
    headers = Headers()
    # Load it up with stuff.  Note the implicit string conversions.
    headers.add("foo", "AAA")
    headers.add("foo", "BBB")  # creates second kv pair with same key
    headers.add("foo", "CCC")  # creates third kv pair with same key
    headers.add("bar", 34)  # implicit string conversion
    headers.add("gee", True)  # implict string conversion
    headers.add("hah", ["one", "two", "three"])  # implict string conversion
    # Create the context from the headers
    ctx = create_context(headers)
    assert isinstance(ctx, Context)
    assert ctx.size == 4
    # Check the data property.  Note aggregation of duplicate header keys
    actual = ctx.data
    assert actual["foo"] == ["AAA", "BBB", "CCC"]  # aggregated keys
    assert actual["bar"] == "34"
    assert actual["gee"] == "True"
    assert actual["hah"] == "['one', 'two', 'three']"
