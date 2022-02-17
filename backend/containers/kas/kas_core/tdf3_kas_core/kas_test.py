"""Test the KAS core code."""

import json

from pprint import pprint

from tdf3_kas_core.models import AttributePolicyCache

from .kas import Kas, swagger_enabled

name = "__main__"


def test_kas_constructor():
    """Test KAS constructor."""
    actual = Kas.get_instance()
    actual.set_root_name(name)
    assert isinstance(actual, Kas)
    assert actual._root_name == name


# NOTE: This test is not valid anymore, the attributes are fetched
# from eas.
# def test_kas_set_attribute_config():
#     """Test Kas ability to boot with attribute policies.
#
#     This is redundant with the unit test for the cache in
#     src/model/attribute_policies, so the only check here is that
#     the Kas has an AttributePolicyCache that constructs and loads.
#     """
#     test_kas = Kas.get_instance()
#     test_kas.set_root_name(name)
#     test_config_json = """{
#         "https://example.com/attr/NTK": {
#             "rule": "allOf"
#         },
#         "https://example.com/attr/Rel": {
#             "rule": "anyOf"
#         },
#         "https://example.com/attr/Classification": {
#             "rule": "hierarchy",
#             "order": ["TS", "S", "C", "U"]
#         }
#     }"""
#     pprint(test_config_json)
#     test_config = json.loads(test_config_json)
#     pprint(test_config)
#     actual = test_kas._attribute_policy_cache
#     assert isinstance(actual, AttributePolicyCache)
#     assert actual.size == 0
#     test_kas.set_attribute_config(test_config)
#     assert actual.size == 3


def test_swagger_enabled():
    assert swagger_enabled()
