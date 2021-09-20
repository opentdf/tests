"""Test the EAS connector."""

import pytest

from unittest.mock import patch, Mock

import requests

from tdf3_kas_core.errors import InvalidAttributeError
from tdf3_kas_core.errors import RequestTimeoutError
from .eas_connector import EASConnector

HOST = "http://localhost:4010"
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


def test_eas_connector_constructor():
    connector = EASConnector(HOST)
    assert isinstance(connector, EASConnector)
    assert connector._host == HOST
    assert connector._headers == {
        "Content-Type": "application/json",
    }
    assert connector._requests_timeout == 10


@patch.object(requests, "post", return_value=Mock(status_code=404))
def test_fetch_attributes_404(mock_request):
    connector = EASConnector(HOST)
    result = connector.fetch_attributes([])
    assert result is None


def mocked_requests_response(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    return MockResponse(ATTRIBUTES, 200)


@patch.object(requests, "post", side_effect=mocked_requests_response)
def test_fetch_attributes_200_stautus(mock_request):
    connector = EASConnector(HOST)
    attributes = connector.fetch_attributes(NAMESPACES)
    assert attributes == ATTRIBUTES


@patch.object(requests, "post", side_effect=requests.exceptions.ReadTimeout)
def test_fetch_attributes_read_timeout_exception(mock_request):
    connector = EASConnector(HOST)
    with pytest.raises(RequestTimeoutError):
        connector.fetch_attributes(NAMESPACES)


@patch.object(requests, "post", side_effect=requests.exceptions.ConnectTimeout)
def test_fetch_attributes_connect_timeout_exception(mock_request):
    connector = EASConnector(HOST)
    with pytest.raises(RequestTimeoutError):
        connector.fetch_attributes(NAMESPACES)


@patch.object(requests, "post", side_effect=requests.exceptions.RequestException)
def test_fetch_attributes_request_exception(mock_request):
    connector = EASConnector(HOST)
    with pytest.raises(InvalidAttributeError):
        connector.fetch_attributes(NAMESPACES)
