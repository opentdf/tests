import json
import pytest

from .. import main

#Test Authorities
def test_read_authority_namespace(test_app, monkeypatch):
    test_data = [
        "https://opentdf1.io",
        "https://opentdf2.io"
    ]

    async def mock_read_authorities_crud():
        return test_data

    monkeypatch.setattr(main, "read_authorities_crud", mock_read_authorities_crud)

    response = test_app.get("/authorities")
    assert response.status_code == 200
    assert response.json() == test_data

def test_create_authorities(test_app, monkeypatch):
    test_payload = {"authority": "https://opentdf.io"}
    test_response = ["https://opentdf.io"]

    async def mock_create_authorities_crud(request):
        return test_response

    monkeypatch.setattr(main, "create_authorities_crud", mock_create_authorities_crud)

    response = test_app.post("/authorities", data=json.dumps(test_payload))
    assert response.status_code == 200
    assert response.json() == test_response

# Test Attribute Definitions
def test_read_attributes(test_app, monkeypatch):
    test_data = [
      "http://opentdf.io/attr/IntellectualProperty/value/TradeSecret",
      "http://opentdf.io/attr/IntellectualProperty/value/Proprietary",
      "http://opentdf.io/attr/Top/value/V1",
      "http://opentdf.io/attr/Top/value/V2"
    ]
    async def mock_read_attributes_crud(schema, db, filter, sort):
        return test_data

    monkeypatch.setattr(main, "read_attributes_crud", mock_read_attributes_crud)

    response = test_app.get("/attributes")
    assert response.status_code == 200
    assert response.json() == test_data
    print(response.headers)
    assert response.headers['x-total-count'] == str(4)

def test_create_attributes_definitions(test_app, monkeypatch):
    test_payload = {
      "authority": "https://opentdf.io",
      "name": "IntellectualProperty",
      "rule": "hierarchy",
      "state": "published",
      "order": [
        "TradeSecret",
        "Proprietary",
        "BusinessSensitive",
        "Open"
      ]
    }

    test_response = {
      "authority": "https://opentdf.io",
      "name": "IntellectualProperty",
      "rule": "hierarchy",
      "state": "published",
      "order": [
        "TradeSecret",
        "Proprietary",
        "BusinessSensitive",
        "Open"
      ]
    }

    async def mock_create_attributes_definitions_crud(request):
        return test_response

    monkeypatch.setattr(main, "create_attributes_definitions_crud", mock_create_attributes_definitions_crud)

    response = test_app.post("/definitions/attributes", data=json.dumps(test_payload))
    assert response.status_code == 200
    assert response.json() == test_response

def test_update_attribute_definition(test_app, monkeypatch):
    test_payload = {
      "authority": "https://opentdf.io",
      "name": "IntellectualProperty",
      "rule": "hierarchy",
      "state": "published",
      "order": [
        "TradeSecret",
        "Proprietary",
        "BusinessSensitive",
        "Open"
      ]
    }

    test_response = {
      "authority": "https://opentdf.io",
      "name": "IntellectualProperty",
      "rule": "hierarchy",
      "state": "published",
      "order": [
        "TradeSecret",
        "Proprietary",
        "BusinessSensitive",
        "Open"
      ]
    }

    async def mock_update_attribute_definition_crud(request):
        return test_response

    monkeypatch.setattr(main, "update_attribute_definition_crud", mock_update_attribute_definition_crud)

    response = test_app.put("/definitions/attributes", data=json.dumps(test_payload))
    assert response.status_code == 200
    assert response.json() == test_response

def test_delete_attributes_definitions(test_app, monkeypatch):
    test_payload = {
      "authority": "https://opentdf.io",
      "name": "IntellectualProperty",
      "rule": "hierarchy",
      "state": "published",
      "order": [
        "TradeSecret",
        "Proprietary",
        "BusinessSensitive",
        "Open"
      ]
    }

    async def mock_delete_attributes_definitions_crud(request):
        return {}

    monkeypatch.setattr(main, "delete_attributes_definitions_crud", mock_delete_attributes_definitions_crud)

    response = test_app.delete("/definitions/attributes", data=json.dumps(test_payload))
    assert response.status_code == 202
    assert response.json() == {}
