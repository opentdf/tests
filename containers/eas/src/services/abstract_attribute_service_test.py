import pytest

from .abstract_attribute_service import AbstractAttributeService
from ..errors import NotImplementedException


@pytest.fixture(scope="session")
def attribute_service():
    return AbstractAttributeService()


def test_attribute_service_create(attribute_service):
    with pytest.raises(NotImplementedException):
        attribute_service.create(None)


def test_attribute_service_retrieve(attribute_service):
    with pytest.raises(NotImplementedException):
        attribute_service.retrieve(None)


def test_attribute_service_update(attribute_service):
    with pytest.raises(NotImplementedException):
        attribute_service.update(None)


def test_attribute_service_delete(attribute_service):
    with pytest.raises(NotImplementedException):
        attribute_service.delete(None)
