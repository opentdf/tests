"""
Tests for the ACMRewrapPlugin and associated functions.
"""
import pytest
from unittest.mock import patch
import requests

from .eas_rewrap_plugin import EASRewrapPlugin

EAS_HOST = "http://localhost:4010"
NAMESPACES = [
    "https://acme.com/attr/IntellectualProperty",
    "https://acme.mil/attr/AcmeRestrictions",
]
ATTRIBUTES = {
    "https://acme.com/attr/IntellectualProperty": {
        "rule": "hierarchy",
        "order": ["TradeSecret", "Proprietary", "BusinessSensitive", "Open"],
    },
    "https://acme.mil/attr/AcmeRestrictions": {"rule": "allOf"},
}


def test_eas_rewrap_plugin_constructor():
    actual = EASRewrapPlugin(EAS_HOST)
    assert isinstance(actual, EASRewrapPlugin)


def mocked_requests_response(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    return MockResponse(ATTRIBUTES, 200)


@patch.object(requests, "post", side_effect=mocked_requests_response)
def test_eas_rewrap_plugin_fetch_attributes(mock_request):
    test_case = EASRewrapPlugin(EAS_HOST)
    attributes = test_case.fetch_attributes(NAMESPACES)
    assert attributes == ATTRIBUTES
