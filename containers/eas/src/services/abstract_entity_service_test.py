import pytest

from .abstract_entity_service import AbstractEntityService
from ..errors import NotImplementedException


@pytest.fixture(scope="session")
def user_service():
    return AbstractEntityService()


def test_user_service_create(user_service):
    with pytest.raises(NotImplementedException):
        user_service.create(None)


def test_user_service_retrieve(user_service):
    with pytest.raises(NotImplementedException):
        user_service.retrieve(None)


def test_user_service_retrieve_all(user_service):
    with pytest.raises(NotImplementedException):
        user_service.retrieveAll()


def test_user_service_retrieve_all_query(user_service):
    with pytest.raises(NotImplementedException):
        user_service.retrieveAllByQuery(query="")


def test_user_service_update(user_service):
    with pytest.raises(NotImplementedException):
        user_service.update(None)


def test_user_service_delete(user_service):
    with pytest.raises(NotImplementedException):
        user_service.delete(None)
