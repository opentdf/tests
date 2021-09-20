"""Test the EAS app."""
import logging
import re
import urllib.parse
from typing import Dict, List, Tuple

import pytest
from flask import Flask, Response
from flask.testing import FlaskClient

from .eas_app import eas_app
from .eas_config import EASConfig
from .models import (
    AttributeName,
    AttributeValue,
    AuthorityNamespace,
    Entity,
    EntityAttributeRelationship,
    RuleType,
    State,
)
from .services import EntityObjectService, ServiceSingleton
from .services.attribute_service_setup import setup_attribute_service
from .services.attribute_service_test import random_attribute, random_string
from .services.authority_ns_service_setup import setup_authority_ns_service
from .services.entity_attr_rel_setup import setup_entity_attr_rel_service
from .services.entity_object_service_test import client_public_key
from .services.entity_service_setup import setup_entity_service
from .services.entity_service_test import random_user
from .util.keys.get_keys_from_disk import get_key_using_config

logger = logging.getLogger(__name__)

# Test strings
TEST_DISPLAY_NAME = "test display name"

eas_config = EASConfig.get_instance()

DEFAULT_NAMESPACE = eas_config.get_item("DEFAULT_NAMESPACE")

# Run each test with these configs
# When adding new implementations or important options, add here.
config_profiles = [
    {"SWAGGER_UI": False},
    {"SWAGGER_UI": True},
]


@pytest.fixture(scope="session", params=config_profiles, ids=("SQL-NO-UI", "SQL-UI"))
def eas_app_client(request):
    """Create a FlaskClient for each config profile
    All tests in this module will be run under every profile"""
    logger.info("create eas_app_instance %s", request.param)

    # Push the settings for this config into the config cache so app will use them
    for setting in request.param.items():
        eas_config.cache.update({setting[0]: setting[1]})

    # The service instances used by the app are bound to these variables in services.__init__.py
    # We need to update them to the current configuration
    services = ServiceSingleton.get_instance()
    assert services
    services.ear_service = setup_entity_attr_rel_service()
    services.entity_service = setup_entity_service(services.ear_service)
    services.attribute_service = setup_attribute_service()
    services.authority_ns_service = setup_authority_ns_service()
    services.entity_object_service = EntityObjectService(
        services.entity_service, services.attribute_service
    )
    assert (
        services.ear_service
        and services.entity_service
        and services.attribute_service
        and services.authority_ns_service
        and services.entity_object_service
    )

    # Make sure the app and the attribute service are using the same public key
    assert (
        get_key_using_config("KAS_CERTIFICATE")
        == services.attribute_service.get_kas_public_key()
    )

    app = eas_app("__main__")
    app.testing = True
    app.logger.setLevel("DEBUG")
    assert isinstance(app, Flask)

    client = app.test_client()
    assert isinstance(client, FlaskClient)
    return client


def test_swagger(eas_app_client):
    """swagger_ui should only be enabled if SWAGGER_UI is True"""
    response = eas_app_client.get("/ui/")
    if eas_config.get_item_boolean("SWAGGER_UI"):
        check_response_code(response, 200)
    else:
        assert response.status_code == 404


def test_eas_heartbeat(eas_app_client):
    """App root url should respond with version."""
    response = eas_app_client.get("/")
    assert isinstance(response, Response)
    check_response_code(response, 200)
    assert response.is_json
    json = response.get_json()
    assert re.match(r"\d+\.\d+\.\d+", json["version"])


def test_eas_ready(eas_app_client):
    """The readiness endpoint returns successful NO-CONTENT response."""
    response = eas_app_client.get("/healthz?probe=readiness")
    assert isinstance(response, Response)
    check_response_code(response, 204)


def test_eas_attribute_create(eas_app_client):
    """Attribute should be created"""
    test_attr_url = random_attribute()
    attr = AttributeValue.from_uri(test_attr_url)

    response = eas_app_client.post("/v1/attribute", json=[test_attr_url])
    assert isinstance(response, Response)
    check_response_code(response, 201)
    assert response.is_json
    json = response.get_json()
    assert json[0]["attribute"] == test_attr_url

    namespace = attr.authorityNamespace
    response = eas_app_client.get(
        f"/v1/attr/{attr.name}/value?namespace={urllib.parse.quote(namespace)}"
    )
    check_response_code(response, 200)
    json = response.get_json()

    uri_list = [attr_result["attribute"] for attr_result in json]
    assert test_attr_url in uri_list
    i = uri_list.index(test_attr_url)
    assert json[i]["state"] == State.ACTIVE.to_string()


def test_eas_attribute_error_handling(eas_app_client):
    response = eas_app_client.get("/v1/not-a-real-endpoint")
    assert response.status_code == 404


def test_eas_attribute_value_error_handling(eas_app_client):
    invalid_name = random_string()
    invalid_value = random_string()
    response = eas_app_client.get(
        f"/v1/attr/{invalid_name}/value/{invalid_value}?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}"
    )
    assert response.status_code == 404


def test_eas_attribute_value_with_ns_error_handling(eas_app_client):
    invalid_name = random_string()
    response = eas_app_client.get(
        f"/v1/attr/{invalid_name}/value?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}"
    )
    assert response.status_code == 404


def test_eas_attribute_value_with_ns2_error_handling(eas_app_client):
    invalid_name = random_string()
    response = eas_app_client.get(
        f"/v1/attr/{invalid_name}/value?namespace={urllib.parse.quote('https://invalid.example.com')}"
    )
    assert response.status_code == 404


def test_eas_attribute_value_with_ns3_error_handling(eas_app_client):
    invalid_name = random_string()
    response = eas_app_client.get(
        f"/v1/attr/{invalid_name}?namespace={urllib.parse.quote('https://invalid.example.com')}"
    )
    assert response.status_code == 404


def test_eas_attribute_update_retrieve(eas_app_client):
    """Attribute should be updated correctly"""
    test_attr_url = random_attribute()
    attr_body = [test_attr_url]
    response = eas_app_client.post("/v1/attribute", json=attr_body)
    check_response_code(response, 201)

    # Update the attribute with a new display name
    update_body = {
        "attribute": test_attr_url,
        "displayName": TEST_DISPLAY_NAME,
        "isDefault": False,
        "kasUrl": eas_config.get_item("KAS_DEFAULT_URL"),
        "pubKey": get_key_using_config("KAS_CERTIFICATE"),
    }
    updated_response = eas_app_client.put("/v1/attribute", json=update_body)
    assert updated_response.status_code == 200

    attribute_service = ServiceSingleton.get_instance().attribute_service
    updated_attribute_value = attribute_service.retrieve([test_attr_url])[0]
    assert updated_attribute_value.attribute == test_attr_url
    assert updated_attribute_value.display_name == TEST_DISPLAY_NAME


def test_eas_attr_value_update_retrieve(eas_app_client):
    """Attribute should be updated correctly using attr endpoints"""
    test_attr_url = random_attribute()
    test_attr_raw = {
        "attribute": test_attr_url,
        "kasUrl": eas_config.get_item("KAS_DEFAULT_URL"),
        "pubKey": get_key_using_config("KAS_CERTIFICATE"),
    }
    a = AttributeValue.from_raw_dict(test_attr_raw)
    response = eas_app_client.post(
        f"/v1/attr/{a.name}/value?namespace={a.authorityNamespace}", json=test_attr_raw
    )
    assert response.status_code == 201

    response = eas_app_client.get(
        f"/v1/attr/{a.name}/value?namespace={a.authorityNamespace}"
    )
    assert response.status_code == 200
    check_response_code(response, 200)
    json = response.get_json()
    uri_list = [attr_result["attribute"] for attr_result in json]
    assert test_attr_url in uri_list

    # Can't create attribute value that already exists
    response = eas_app_client.post(
        f"/v1/attr/{a.name}/value?namespace={a.authorityNamespace}", json=test_attr_raw
    )
    assert response.status_code == 409

    # should return the specific value we just created
    response = eas_app_client.get(
        f"/v1/attr/{a.name}/value/{a.value}?namespace={a.authorityNamespace}"
    )
    check_response_code(response, 200)
    json = response.get_json()
    assert json["attribute"] == test_attr_url

    # Update the attribute with a new display name
    update_body = {
        "attribute": test_attr_url,
        "displayName": TEST_DISPLAY_NAME,
        "isDefault": False,
        "kasUrl": eas_config.get_item("KAS_DEFAULT_URL"),
        "pubKey": get_key_using_config("KAS_CERTIFICATE"),
    }
    updated_response = eas_app_client.put(
        f"/v1/attr/{a.name}/value/{a.value}?namespace={a.authorityNamespace}",
        json=update_body,
    )
    json = updated_response.get_json()
    assert updated_response.status_code == 200
    assert json

    attribute_service = ServiceSingleton.get_instance().attribute_service
    updated_attribute_value = attribute_service.retrieve([test_attr_url])[0]
    assert updated_attribute_value.attribute == test_attr_url
    assert updated_attribute_value.display_name == TEST_DISPLAY_NAME


def test_eas_entity_create_deactivate(eas_app_client):
    """User Entity should be created - using deprecated user endpoint"""
    test_user = random_user()

    # Can't delete before adding to EAS
    response = eas_app_client.delete(f"/v1/user{test_user['userId']}", json=test_user)
    assert response.status_code == 404

    # Create user in DB
    response = eas_app_client.post("/v1/user", json=test_user)
    validate_entity_response(response, test_user, 201)

    # Get the user
    response = eas_app_client.get(f"/v1/user/{test_user['userId']}")
    validate_entity_response(response, test_user, 200)

    # Delete the user
    response = eas_app_client.delete(f"/v1/user/{test_user['userId']}", json=test_user)
    expected_deleted_test_user = test_user
    expected_deleted_test_user["state"] = "inactive"
    validate_entity_response(response, test_user, 200)


def validate_entity_response(response, test_user, expected_status):
    assert isinstance(response, Response)
    assert response.is_json
    json = response.get_json()
    assert response.status_code == expected_status
    assert json["userId"] == test_user["userId"]
    test_user_obj = Entity.from_raw(test_user)
    returned_user_obj = Entity.from_raw(json)
    assert test_user_obj.equals_with_attributes(returned_user_obj)
    return test_user_obj


def test_eas_entity_retrieve_notfound(eas_app_client):
    """Entity should be created"""
    test_entity = random_user()
    response = eas_app_client.get(f"/v1/entity/{test_entity['userId']}")
    assert response.status_code == 404
    # Deprecated endpoint should return same
    response = eas_app_client.get(f"/v1/user/{test_entity['userId']}")
    assert response.status_code == 404


def test_eas_entity_head(eas_app_client):
    # Test head method
    all_users_head = eas_app_client.head("/v1/entity")
    assert all_users_head.status_code == 200


def test_eas_entity_create_retrieve_update(eas_app_client):
    """Entity should be created"""
    test_entity = random_user()
    response = eas_app_client.post("/v1/entity", json=test_entity)
    assert isinstance(response, Response)
    validate_entity_response(response, test_entity, 201)

    # Can't create entity who already exists
    response = eas_app_client.post("/v1/entity", json=test_entity)
    assert response.status_code == 409

    # Test retrieval of this entity
    retrieved = eas_app_client.get(f"/v1/entity/{test_entity['userId']}")
    test_user_obj = validate_entity_response(retrieved, test_entity, 200)

    # Filtering entities isn't implemented, so should return 501
    all_users_head = eas_app_client.head(f"/v1/entity?q={test_entity['userId']}")
    assert all_users_head.status_code == 200
    all_users_head = eas_app_client.get(f"/v1/entity?q={test_entity['userId']}")
    assert all_users_head.status_code == 200

    all_users = eas_app_client.get("/v1/entity")
    json = all_users.get_json()
    returned_user_obj = None
    for raw_user in json:
        if raw_user["userId"] == test_entity["userId"]:
            returned_user_obj = Entity.from_raw(raw_user)
            assert test_user_obj.equals_with_attributes(returned_user_obj)
    assert returned_user_obj

    test_entity["email"] = f"changed_{test_entity['email']}"
    changed_test_user_obj = Entity.from_raw(test_entity)
    update = eas_app_client.put("/v1/entity", json=test_entity)
    assert update.status_code == 200
    json = update.get_json()
    returned_user_obj = Entity.from_raw(json)
    assert changed_test_user_obj.equals_with_attributes(returned_user_obj)


def test_eas_generate_entity_object(eas_app_client):
    """Create entity and get entity object"""
    test_user = random_user()
    response = eas_app_client.post("/v1/entity", json=test_user)
    assert isinstance(response, Response)
    check_response_code(response, 201)

    eo_post = {"publicKey": client_public_key, "userId": test_user["userId"]}
    eo_response = eas_app_client.post("/v1/entity_object", json=eo_post)
    assert eo_response.status_code == 200

    # Error cases - no such user
    eo_post = {"publicKey": client_public_key, "userId": "no such user"}
    eo_response = eas_app_client.post("/v1/entity_object", json=eo_post)
    assert eo_response.status_code == 403  # Authorization Error

    # Error cases - missing public key
    eo_post = {"userId": test_user["userId"]}
    eo_response = eas_app_client.post("/v1/entity_object", json=eo_post)
    assert eo_response.status_code == 400


def test_namespace_get(eas_app_client):
    # Get non-default namespaces
    response = eas_app_client.get("/v1/authorityNamespace?isDefault=false")
    assert isinstance(response, Response)
    check_response_code(response, 200)
    assert response.is_json
    json = response.get_json()
    assert isinstance(json, list)
    # Not asserting non-default namespaces because they aren't required to be created.

    # Getting default namespace should return one result and should match default namespace config
    response = eas_app_client.get("/v1/authorityNamespace?isDefault=true")
    assert isinstance(response, Response)
    check_response_code(response, 200)
    assert response.is_json
    json = response.get_json()
    assert json[0] == DEFAULT_NAMESPACE
    assert len(json) == 1


def test_namespace_create(eas_app_client):
    body = {"namespace": f"https://{random_string()}.example.com", "isDefault": False}
    orig_ns = AuthorityNamespace.from_raw(body)
    response = eas_app_client.post("/v1/authorityNamespace", json=body)
    assert isinstance(response, Response)

    check_response_code(response, 200)
    assert response.is_json
    new_ns = AuthorityNamespace.from_raw(response.get_json())
    assert orig_ns == new_ns

    # Can't create same namespace twice
    response = eas_app_client.post("/v1/authorityNamespace", json=body)
    assert response.status_code == 409


def test_attr_post_get_update(eas_app_client):
    name = random_string()
    attr_name = f"{DEFAULT_NAMESPACE}/attr/{name}"
    body = {
        "authorityNamespace": DEFAULT_NAMESPACE,
        "name": name,
        "order": ["TradeSecret", "Proprietary", "BusinessSensitive", "Open"],
        "rule": "anyOf",
        "state": "active",
    }
    attr_name_obj: AttributeName = AttributeName.from_raw_dict(body)
    assert attr_name_obj.name == name
    assert attr_name_obj.authorityNamespace == DEFAULT_NAMESPACE

    # Test creating attribute name
    response = eas_app_client.post(
        f"/v1/attr?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}", json=[body]
    )
    json = response.get_json()
    check_response_code(response, 201)
    assert len(json) == 1
    attr_name_created = AttributeName.from_uri_and_raw_dict(attr_name, json[0])
    assert attr_name_created.equals_with_attributes(attr_name_obj)

    # Can't create same attribute name twice - communicated with a "None" value
    response = eas_app_client.post(
        f"/v1/attr?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}", json=[body]
    )
    check_response_code(response, 409)

    # Get the attribute name
    response = eas_app_client.get(
        f"/v1/attr?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}"
    )
    json = response.get_json()
    check_response_code(response, 200)

    found = False
    for attr_result in json:
        attr_result_obj: AttributeName = AttributeName.from_raw_dict(attr_result)
        if attr_result_obj.uri == attr_name:
            assert attr_result["state"] == State.ACTIVE.to_string()
            assert attr_result_obj.equals_with_attributes(attr_name_obj)
            found = True
    assert found

    # Test update method
    body = {
        "authorityNamespace": DEFAULT_NAMESPACE,
        "name": name,
        "order": ["TradeSecret", "Proprietary", "BusinessSensitive", "Open"],
        "rule": "anyOf",
        "state": "inactive",
    }

    response = eas_app_client.put(
        f"/v1/attr/{urllib.parse.quote(name)}?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}",
        json=body,
    )
    check_response_code(response, 200)
    json = response.get_json()
    assert json["name"] == name
    assert json["authorityNamespace"] == DEFAULT_NAMESPACE
    assert json["state"] == State.INACTIVE.name.lower()

    # Patch the Attribute name
    body = [
        {
            "authorityNamespace": DEFAULT_NAMESPACE,
            "name": name,
            "rule": "allOf",
            "state": "active",
        }
    ]
    logger.debug(f"/v1/attr?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}")
    logger.debug(body)
    response = eas_app_client.patch(
        f"/v1/attr?namespace={urllib.parse.quote(DEFAULT_NAMESPACE)}", json=body
    )
    check_response_code(response, 200)
    json = response.get_json()
    assert len(json) == 1
    assert json[0]["name"] == name
    assert json[0]["rule"] == RuleType.ALL_OF.to_string()
    assert json[0]["state"] == State.ACTIVE.name.lower()

    # Test with attrName interface
    attr_name_list = [attr_name]
    response = eas_app_client.post("/v1/attrName", json=attr_name_list)
    json = response.get_json()
    check_response_code(response, 200)
    assert isinstance(json, list)
    assert json[0]["name"] == name
    assert json[0]["rule"] == RuleType.ALL_OF.to_string()
    assert json[0]["state"] == State.ACTIVE.name.lower()


def test_attr_head(eas_app_client):
    namespace = "https://new.namespace.example.com"
    response = eas_app_client.head(
        f"/v1/attr?namespace={urllib.parse.quote(namespace)}"
    )
    check_response_code(response, 200)


def test_entity_attribute(eas_app_client):
    response = eas_app_client.get("/v1/entity/attribute")
    assert isinstance(response, Response)
    check_response_code(response, 200)

    user1: dict = post_random_user(eas_app_client)

    attr1: str = post_random_attribute(eas_app_client)
    assert attr1
    # Relate them using `/v1/attribute/{attributeURI}/entity` endpoint
    body = [user1["userId"]]

    response = eas_app_client.put(
        f"/v1/attribute/{urllib.parse.quote(attr1)}/entity",
        json=body,
        content_type="application/json",
    )
    check_response_code(response, 200)

    attr2 = post_random_attribute(eas_app_client)
    # Relate another attribute using `/v1/entity/{entityId}/attribute` endpoint
    body = [attr2]
    response = eas_app_client.put(f"/v1/entity/{user1['userId']}/attribute", json=body)
    check_response_code(response, 200)

    # Get the relationship to validate
    a1 = AttributeValue.from_uri(attr1)
    response = eas_app_client.get(
        f"/v1/attr/{a1.name}/value/{a1.value}/entity?namespace={a1.authorityNamespace}"
    )
    check_response_code(response, 200)
    entity_list = response.get_json()
    assert user_in_entity_list(entity_list, user1)

    # Get the relationship - via attribute name - to validate
    response = eas_app_client.get(
        f"/v1/attr/{a1.name}/entity?namespace={a1.authorityNamespace}"
    )
    check_response_code(response, 200)
    expanded_ear_list = response.get_json()
    assert user_in_expanded_ear(expanded_ear_list, user1)

    # delete attr2
    response = eas_app_client.delete(
        f"/v1/entity/{user1['userId']}/attribute/{urllib.parse.quote(attr2)}"
    )
    check_response_code(response, 200)

    # Confirm that the relationships exist and are in the state we set them to
    confirm_ear(eas_app_client, user1, attr1, State.ACTIVE)
    confirm_ear(eas_app_client, user1, attr2, State.INACTIVE)


def test_ear_state_transitions(eas_app_client):
    # Regression test for PLAT-762
    user_raw: dict = post_random_user(eas_app_client)
    attr_uri: str = post_random_attribute(eas_app_client)

    # Relate them using `/v1/attribute/{attributeURI}/entity` endpoint
    body = [user_raw["userId"]]
    response = eas_app_client.put(
        f"/v1/attribute/{urllib.parse.quote(attr_uri)}/entity",
        json=body,
        content_type="application/json",
    )
    check_response_code(response, 200)

    confirm_ear(eas_app_client, user_raw, attr_uri, State.ACTIVE)
    confirm_ear_through_entity(eas_app_client, user_raw, attr_uri, State.ACTIVE)

    # delete (inactivate) attr_uri
    response = eas_app_client.delete(
        f"/v1/entity/{user_raw['userId']}/attribute/{urllib.parse.quote(attr_uri)}"
    )
    check_response_code(response, 200)

    # Confirm attr_uri is inactive for user_raw
    confirm_ear(eas_app_client, user_raw, attr_uri, State.INACTIVE)
    user_update = confirm_ear_through_entity(
        eas_app_client, user_raw, attr_uri, State.INACTIVE
    )

    # Update the user by adding the attribute again:
    user_update["attributes"] = [attr_uri]
    eas_app_client.put("/v1/entity", json=user_update)

    # Confirm the ear is active - the user actively has the attribute
    confirm_ear(eas_app_client, user_raw, attr_uri, State.ACTIVE)
    confirm_ear_through_entity(eas_app_client, user_raw, attr_uri, State.ACTIVE)
    confirm_ear_through_attribute(eas_app_client, user_raw, attr_uri, State.ACTIVE)

    # Update the user to have no attributes:
    user_update["attributes"] = []
    eas_app_client.put("/v1/entity", json=user_update)

    # Confirm the ear is inactive - the user doesn't have attribute
    confirm_ear(eas_app_client, user_raw, attr_uri, State.INACTIVE)
    confirm_ear_through_entity(eas_app_client, user_raw, attr_uri, State.INACTIVE)
    confirm_ear_through_attribute(eas_app_client, user_raw, attr_uri, State.INACTIVE)


def user_in_entity_list(entity_list, user1) -> bool:
    for entity_raw in entity_list:
        if entity_raw["userId"] == user1["userId"]:
            return True
    return False


def user_in_expanded_ear(entity_list, user1) -> bool:
    for expanded in entity_list:
        assert "entity" in expanded
        assert "state" in expanded
        assert "attribute" in expanded
        if expanded["entity"]["userId"] == user1["userId"]:
            return True
    return False


def get_all_ears(eas_app_client) -> Dict[Tuple[str, str], EntityAttributeRelationship]:
    """fetch all the ears and make a dict on tuple (userId, attrUri)"""
    response = eas_app_client.get("/v1/entity/attribute")
    all_ears = response.get_json()
    check_response_code(response, 200)
    return raw_ear_list_to_dict(all_ears)


def raw_ear_list_to_dict(
    all_ears: list,
) -> Dict[Tuple[str, str], EntityAttributeRelationship]:
    ear_dict: Dict[Tuple[str, str], EntityAttributeRelationship] = {}
    for ear_raw in all_ears:
        ear: EntityAttributeRelationship = EntityAttributeRelationship.from_raw(ear_raw)
        # Check for duplicates.  If it is already there, we have a duplicate and that is invalid
        with pytest.raises(KeyError):
            print(ear_dict[(ear.entity_id, ear.attribute_uri)].to_json())
        ear_dict[(ear.entity_id, ear.attribute_uri)] = ear
    return ear_dict


def confirm_ear(
    eas_app_client, entity_raw: dict, attr: str, st: State
) -> EntityAttributeRelationship:
    ear_dict: Dict[Tuple[str, str], EntityAttributeRelationship] = get_all_ears(
        eas_app_client
    )
    # Assert that entity has attr and that the relationship has state st
    ear: EntityAttributeRelationship = ear_dict[(entity_raw["userId"]), attr]
    assert isinstance(ear, EntityAttributeRelationship)
    assert ear.entity_id == entity_raw["userId"]
    assert ear.attribute_uri == attr
    assert ear.state == st
    return ear


def confirm_ear_through_entity(
    eas_app_client, entity_raw: dict, attr: str, st: State
) -> dict:
    response = eas_app_client.get(f"/v1/entity/{entity_raw['userId']}")
    check_response_code(response, 200)
    retrieved_entity: dict = response.get_json()
    retrieved_attr: List[str] = retrieved_entity["attributes"]
    if st is State.ACTIVE:
        assert attr in retrieved_attr
    else:
        assert attr not in retrieved_attr
    return retrieved_entity


def confirm_ear_through_attribute(
    eas_app_client, entity_raw: dict, attr: str, st: State
) -> None:
    attr_obj = AttributeValue.from_uri(attr)
    response = eas_app_client.get(
        f"/v1/attr/{attr_obj.name}/value/{attr_obj.value}/entity"
    )
    check_response_code(response, 200)
    retrieved_entities: List[dict] = response.get_json()
    entity_ids: List[str] = [entity["userId"] for entity in retrieved_entities]
    if st is State.ACTIVE:
        assert entity_raw["userId"] in entity_ids
    else:
        assert entity_raw["userId"] not in entity_ids


def post_random_attribute(eas_app_client) -> str:
    """Create a test attribute, return uri"""
    test_attr_url = random_attribute()
    attr_body = [test_attr_url]
    response = eas_app_client.post("/v1/attribute", json=attr_body)
    assert response.status_code == 201
    check_response_code(response, 201)

    return test_attr_url


def post_random_user(eas_app_client) -> dict:
    """Create a test user, return as raw dict"""
    test_user = random_user()
    response = eas_app_client.post("/v1/user", json=test_user)
    check_response_code(response, 201)
    return test_user


def check_response_code(response: Response, expected: int):
    """Check response code; print diagnostics if unexpected code"""
    logger.info("%s => %s", response.status, response.data)
    # Use an assert so that Pytest will show debugging information
    assert response.status_code == expected
