import asyncio
import pytest

from main import app
from fastapi.testclient import TestClient



def test_read_attribute():
    with TestClient(app) as client:
        loop = asyncio.get_event_loop()
        response = client.get("/v1/attr")
    assert response.status_code == 200
    assert response.json()["authorityNamespace"] == "https://eas.local"
    assert response.json()["rule"] == "anyOf"
    assert response.json()["state"] == "1"
    assert response.json()["order"][0] == "urdu"
    assert response.json()["order"][1] == "french"

def test_get_liveness():
    with TestClient(app) as client:
        response = client.get("/healthz?probe=liveness")
    assert response.status_code == 204

def test_get_readiness():
    with TestClient(app) as client:
        response = client.get("/healthz?probe=readiness")
    assert response.status_code == 204