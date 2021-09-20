"""Test the user service function."""
import json
import os

import pytest

from .abstract_entity_service import AbstractEntityService
from .entity_service_setup import get_initial_entities
from .entity_service_setup import setup_entity_service
from .entity_attr_rel_setup import setup_entity_attr_rel_service
from .sql import EntityServiceSql
from ..eas_config import EASConfig
from ..errors import MalformedEntityError
from ..models import Entity, State
from ..util import random_string

CHARLIE_USERID = "CN=Charlie_1234"
DEFAULT_NAMESPACE = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")

curr_dir = os.path.dirname(__file__)
test_path = os.path.join(curr_dir, "test_files", "users.json")
test_path_pki = os.path.join(curr_dir, "test_files", "users-pki.json")


@pytest.fixture(scope="session")
def entity_service(request):
    """All tests should be run on all implementations.
    Add new implementations to "params" parameter above
    This method generates a fixture of each type, so tests are run on each."""
    print(f"setup fixture = entity_service")
    ear_service = setup_entity_attr_rel_service()
    entity_service = setup_entity_service(
        ear_service=ear_service, initial_values_path=test_path_pki
    )
    assert isinstance(entity_service, AbstractEntityService)
    assert isinstance(entity_service, EntityServiceSql)
    return entity_service


def random_user():
    return {
        "userId": f"CN={random_string(7)}",
        "name": f"{random_string(3)} {random_string(7)}",
        "email": f"{random_string()}@random.example.com",
        "attributes": [
            f"{DEFAULT_NAMESPACE}/attr/language/value/english",
            f"{DEFAULT_NAMESPACE}/attr/language/value/french",
        ],
    }


def test_create_user(entity_service):
    raw_user = random_user()
    test_user = Entity.from_raw(raw_user)
    entity_service.create(raw_user)
    retrieved = entity_service.retrieve(test_user.userId)
    assert retrieved
    assert test_user.userId == retrieved["userId"]
    retrieved_user = Entity.from_raw(retrieved)
    assert test_user.equals_with_attributes(retrieved_user)


def test_delete_entity(entity_service):
    """Test soft delete - entity should be set to inactive state"""
    raw_user = random_user()
    test_user = Entity.from_raw(raw_user)
    assert entity_service.create(raw_user)

    # Delete the entity
    deleted = entity_service.delete(test_user.userId)
    assert deleted
    deleted = Entity.from_raw(deleted)
    assert deleted.userId == test_user.userId

    # make sure entity status is inactive
    updated = entity_service.retrieve(test_user.userId)
    assert updated
    assert updated["state"] == "inactive"


def test_update_user(entity_service):
    raw_user = random_user()
    test_user = Entity.from_raw(raw_user)
    entity_service.create(raw_user)
    raw_user["name"] = "new name"
    entity_service.update(raw_user)
    retrieved = entity_service.retrieve(raw_user["userId"])

    assert retrieved["name"] == "new name"
    assert State.from_input(retrieved["state"]) == test_user.state
    assert retrieved["nonPersonEntity"] == test_user.nonPersonEntity


def test_entity_service_update_malformed(entity_service):
    # if not a user object, should raise error.
    with pytest.raises(MalformedEntityError):
        entity_service.update({"user": "invalid"})


def test_get_initial_users():
    """Test the read utility - does not use service itself."""
    with open(test_path, "r") as u_file:
        expected = json.loads(u_file.read())
    actual = get_initial_entities(test_path)

    # Since these are dicts they are hard to compare. Converting them to
    # models first.
    expected_models = []
    actual_models = []
    for item in expected:
        expected_models.append(Entity.from_raw(item))
    for item in actual:
        actual_models.append(Entity.from_raw(item))

    assert set(actual_models) == set(expected_models)


def test_users_by_dn(entity_service):
    """Test the read utility with pki users"""
    with open(test_path_pki, "r") as u_file:
        for user_raw in json.loads(u_file.read()):
            user = Entity.from_raw(user_raw)
            if CHARLIE_USERID == user.userId:
                expected_user = user
                break
    actual = entity_service.retrieve(CHARLIE_USERID)
    assert actual
    actual_user = Entity.from_raw(actual)
    assert type(actual_user) is Entity
    assert actual_user.equals_with_attributes(expected_user)


def test_entity_not_found(entity_service):
    e = random_user()
    result = entity_service.retrieve(e["userId"])
    assert not result


def test_retrieve_all(entity_service):
    users = entity_service.retrieveAll()
    # User service was started with users-pki.json as initial load.
    # users-pki.json has Alice and Bob so there should be at least 2 users returned
    assert len(users) >= 2
    charlie = user_list_get(users, CHARLIE_USERID)
    assert charlie
    assert "https://eas.virtru.com/attr/language/value/french" in charlie["attributes"]
    assert "https://eas.virtru.com/attr/language/value/urdu" in charlie["attributes"]
    bob = user_list_get(users, "CN=bob_5678")
    assert charlie["name"] == "Charlie"
    assert bob
    assert "https://eas.virtru.com/attr/language/value/italian" in bob["attributes"]
    assert bob["email"] == "bob@pki.example.com"


def test_retrieve_all_by_query(entity_service):
    query = "Charlie"
    users = entity_service.retrieveAllByQuery(query=query)
    assert len(users) == 2


def user_list_get(users, userId):
    for user in users:
        if user["userId"] == userId:
            return user
    return None
