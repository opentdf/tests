"""Test the Policy model."""

import pytest  # noqa: F401

import json
import base64

from .policy import Policy

from tdf3_kas_core.models import DataAttributes


def test_policy_constructor():
    """Test the constructor."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    actual = Policy(expected_uuid, expected_canonical)
    assert isinstance(actual, Policy)


def test_policy_uuid_get_and_set():
    """Test the constructor."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    policy = Policy(expected_uuid, expected_canonical)
    assert policy.uuid == expected_uuid
    policy.uuid = "Some other uuid"
    assert policy.uuid == expected_uuid


def test_policy_construct_and_basic_getters():
    """Test the constructor."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    policy = Policy(expected_uuid, expected_canonical)
    assert policy.canonical == expected_canonical
    policy.canonical = "Some other canonical"
    assert policy.canonical == expected_canonical


def test_policy_constructs_from_raw():
    """Test the factory method that constructs from raw."""
    raw_dict = {"uuid": "1111-2222-33333-44444-abddef-timestamp"}
    print(raw_dict)
    raw_can = bytes.decode(base64.b64encode(str.encode(json.dumps(raw_dict))))
    print(raw_can)
    policy = Policy.construct_from_raw_canonical(raw_can)
    print(policy)
    actual = policy.uuid
    print(actual)
    expected = raw_dict["uuid"]
    print(expected)
    assert actual == expected


def test_policy_load_data_attributes_from_raw():
    """Test loading data attributes into an existing policy from raw."""
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    raw_dict = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    print(raw_dict)
    raw_can = bytes.decode(base64.b64encode(str.encode(json.dumps(raw_dict))))
    print(raw_can)
    policy = Policy.construct_from_raw_canonical(raw_can)
    print(policy)
    da = policy.data_attributes
    print(da)
    assert isinstance(da, DataAttributes)
    actual = da.get("https://example.com/attr/Classification/value/S")
    assert actual.namespace == "https://example.com/attr/Classification"
    assert actual.value == "S"
    actual = da.get("https://example.com/attr/COI/value/PRX")
    assert actual.namespace == "https://example.com/attr/COI"
    assert actual.value == "PRX"


def test_policy_loads_dissem_from_raw():
    """Load the dissem field from raw."""
    raw_dict = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dissem": ["user-id@domain.com"]},
    }
    print(raw_dict)
    raw_can = bytes.decode(base64.b64encode(str.encode(json.dumps(raw_dict))))
    print(raw_can)
    policy = Policy.construct_from_raw_canonical(raw_can)
    print(policy)
    actual = policy.dissem.list
    print(actual)
    expected = raw_dict["body"]["dissem"]
    print(expected)
    assert actual == expected


def test_policy_produces_raw():
    """Test the export method that returns a raw policy dict."""
    expected = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {
            "dataAttributes": [{"attribute": "https://example.com/attr/coi/value/prx"}],
            "dissem": ["user-id@domain.com"],
        },
    }
    print(expected)
    raw_can = bytes.decode(base64.b64encode(str.encode(json.dumps(expected))))
    print(raw_can)
    policy = Policy.construct_from_raw_canonical(raw_can)
    actual = policy.export_raw()
    print(actual)
    assert actual == expected


def test_policy_produces_canonical():
    """Test the canonical form export method."""
    uuid = "1111-2222-33333-44444-abddef-timestamp"
    data_attributes = [
        {"attribute": "https://examplea.com/attr/coi/value/prx"},
        {"attribute": "https://exampleb.com/attr/coi/value/pry"},
        {"attribute": "https://examplec.com/attr/coi/value/prz"},
    ]
    dissem = ["user-1@domain.com", "user-2@domain.com", "user-3d@domain.com"]
    print(f"UUID = {uuid}")
    print(f"Data Attributes = {data_attributes}")
    print(f"Dissem = {dissem}")

    policy = Policy(uuid)
    policy.data_attributes.load_raw(data_attributes)
    policy.dissem.list = dissem

    actual = policy.export_canonical()
    print(f"Actual canonical = {actual}")

    p_dict = json.loads(bytes.decode(base64.b64decode(str.encode(actual))))
    print(p_dict)

    assert p_dict["uuid"] == uuid

    body = p_dict["body"]

    actual_attributes = body["dataAttributes"]
    print(f"Actual attributes = {actual_attributes}")
    a_list = []
    for attr in actual_attributes:
        a_list.append(attr["attribute"])
    d_list = []
    for attr in data_attributes:
        d_list.append(attr["attribute"])
    print(a_list)
    print(d_list)
    assert set(a_list) == set(d_list)

    assert set(body["dissem"]) == set(dissem)
