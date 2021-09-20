"""Test the authority namespace service function."""
import os

import pytest

from .abstract_authority_ns_service import AbstractAuthorityNamespaceService
from .authority_ns_service_setup import get_default_authority_namespaces
from .authority_ns_service_setup import setup_authority_ns_service
from .sql.authority_ns_service_sql import AuthorityNamespaceSql
from ..eas_config import EASConfig
from ..errors import AuthorityNamespaceExistsError, NotImplementedException
from ..models.authority_namespace import AuthorityNamespace
from ..util import random_string

curr_dir = os.path.dirname(__file__)
test_path = os.path.join(curr_dir, "test_files", "authority_namespaces.json")


@pytest.fixture(scope="session")
def authority_ns_service(request):
    print(f"setup fixture = authority_ns_service")
    authority_ns_service = setup_authority_ns_service(initial_values_path=test_path)
    assert isinstance(authority_ns_service, AbstractAuthorityNamespaceService)
    assert isinstance(authority_ns_service, AuthorityNamespaceSql)
    return authority_ns_service


def random_authority_ns():
    return {
        "namespace": f"http://{random_string(7, lcase=True)}.example.com",
        "isDefault": False,
    }


def test_create_namespace(authority_ns_service):
    new_namespace = random_authority_ns()
    authority_ns_service.create(new_namespace)
    retrieved = authority_ns_service.retrieve(namespace=new_namespace["namespace"])
    assert retrieved
    assert new_namespace["namespace"] == retrieved[0]

    # Service must not create duplicate
    with pytest.raises(AuthorityNamespaceExistsError):
        authority_ns_service.create(new_namespace)


def test_get_default_namespace():
    """Test the read utility - does not use service itself."""
    namespace = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")

    actual = get_default_authority_namespaces()

    actual_model = AuthorityNamespace.from_raw(actual[0])

    assert actual_model.namespace == namespace
    assert actual_model.isDefault


def test_retrieve_all(authority_ns_service):
    namespaces = authority_ns_service.retrieve()
    # Authority namespace service should have loaded the default namespace if not existing.
    # that file has 1 namespace
    assert len(namespaces) >= 1
    assert EASConfig.get_instance().get_item("DEFAULT_NAMESPACE") in namespaces


def test_abstract_authority_ns_service():
    service = AbstractAuthorityNamespaceService()
    with pytest.raises(NotImplementedException):
        service.create({})
    with pytest.raises(NotImplementedException):
        service.retrieve()
    with pytest.raises(NotImplementedException):
        service.get("")
