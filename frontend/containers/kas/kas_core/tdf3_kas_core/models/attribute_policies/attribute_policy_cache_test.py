"""Test AttributePolicyCache."""

import json

import pytest  # noqa: F401

from .attribute_policy import ALL_OF  # noqa: F401
from .attribute_policy import ANY_OF  # noqa: F401
from .attribute_policy import AttributePolicy
from .attribute_policy import DEFAULT  # noqa: F401
from .attribute_policy import HIERARCHY  # noqa: F401
from .attribute_policy_cache import AttributePolicyCache


def test_attribute_policy_cache_constructor():
    """Test constructor."""
    actual = AttributePolicyCache()
    assert isinstance(actual, AttributePolicyCache)
    assert actual.size == 0


def test_attribute_policy_cache_get_with_default_create():
    """Test get with default policy creation."""
    cache = AttributePolicyCache()
    assert cache.size == 0
    actual = cache.get("https://www.virtru.com/attr/NTK")
    assert cache.size == 1
    assert isinstance(actual, AttributePolicy)
    assert actual.rule == DEFAULT


def test_attribute_policy_cache_load_config():
    """Test config loader."""
    test_config_json = """[
{"authorityNamespace": "https://example.com", "name": "NTK", "rule": "allOf"},
{"authorityNamespace": "https://example.com", "name": "Rel", "rule": "anyOf"},
{"authorityNamespace": "https://example.com", "name": "Classification", "order": ["TS", "S", "C", "U"], "rule": "hierarchy"}
    ]"""
    test_config = json.loads(test_config_json)

    cache = AttributePolicyCache()
    assert cache.size == 0
    cache.load_config(test_config)
    assert cache.size == 3

    ntk = cache.get("https://example.com/attr/NTK")
    assert isinstance(ntk, AttributePolicy)
    assert ntk.rule == ALL_OF

    rel = cache.get("https://example.com/attr/Rel")
    assert isinstance(rel, AttributePolicy)
    assert rel.rule == ANY_OF

    cls = cache.get("https://example.com/attr/Classification")
    assert isinstance(cls, AttributePolicy)
    assert cls.rule == HIERARCHY
