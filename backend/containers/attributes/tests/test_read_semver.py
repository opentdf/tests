from ..main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_read_semver():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello": "attributes"}