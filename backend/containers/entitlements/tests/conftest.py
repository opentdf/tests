import pytest
from fastapi.testclient import TestClient

from ..main import app, get_auth

def get_override_token():
    return "1111"

@pytest.fixture(scope="module")
def test_app():
    app.dependency_overrides[get_auth] = get_override_token
    client = TestClient(app)
    yield client  # testing happens here