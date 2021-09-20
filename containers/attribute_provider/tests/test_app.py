"""Test attribute_provider."""

import pytest
import base64
from flask import Flask, Response
from flask.testing import FlaskClient
from attribute_provider.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        yield client


def test_noop():
    assert True


def test_no_get(client):
    """Test get."""
    rv = client.get("/")
    assert rv.status_code == 405


def test_post(client):
    """Test get."""
    rv = client.post(
        "/",
        json=dict(
            client_id="user1",
            claim_request_type="full_claims",
            client_pk=base64.b64encode(b"hello").decode(),
            token={},
            username="user1",
        ),
    )
    assert rv.status_code == 200


def test_bad_base64_key_padding(client):
    """Some base64 implementations don't pad their encodings
    to be divisible by 4."""
    pk = base64.b64encode(b"a").decode()
    pk = pk.replace("=", "")
    rv = client.post(
        "/",
        json=dict(
            client_id="user1",
            claim_request_type="full_claims",
            client_pk=pk,
            token={},
            username="user1",
        ),
    )
    assert rv.status_code == 200
