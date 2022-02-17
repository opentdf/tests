"""Test the Policy model."""

import pytest  # noqa: F401

import json
import base64

from .policy import Policy


def test_foo():
    """Test remote type policy."""
    expected = "8010bea5-578b-46aa-a4ac-568fb66ec352"
    print(expected)

    raw_can = bytes.decode(base64.b64encode(str.encode(json.dumps(expected))))
    print(raw_can)

    # This is what the client produces; pulled from a request object
    print("IjgwMTBiZWE1LTU3OGItNDZhYS1hNGFjLTU2OGZiNjZlYzM1MiI=")
    print("=====")

    policy = Policy.construct_from_raw_canonical(raw_can)

    print(policy)
    print(policy.uuid)

    assert policy.uuid == expected
