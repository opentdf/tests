"""Test the authority namespace service function."""
import os

import pytest

from .abstract_attribute_name_service import AbstractAttributeNameService
from .abstract_authority_ns_service import AbstractAuthorityNamespaceService
from .attribute_name_service_setup import setup_attribute_name_service
from .authority_ns_service_setup import setup_authority_ns_service
from .sql import AttributeNameServiceSQL, AuthorityNamespaceSql
from ..eas_config import EASConfig
from ..errors import AttributeExistsError, MalformedAttributeError, NotFound
from ..models import AttributeName, RuleType, State
from ..util import random_string

curr_dir = os.path.dirname(__file__)
test_path = os.path.join(curr_dir, "test_files", "authority_namespaces.json")

DEFAULT_NAMESPACE = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")


@pytest.fixture(scope="session")
def attribute_name_service(request):
    print(f"setup fixture = authority_ns_service")
    authority_ns_service = setup_authority_ns_service(initial_values_path=test_path)
    assert isinstance(authority_ns_service, AbstractAuthorityNamespaceService)
    assert isinstance(authority_ns_service, AuthorityNamespaceSql)

    attribute_name_service = setup_attribute_name_service(
        authority_ns_service, DEFAULT_NAMESPACE
    )
    assert isinstance(attribute_name_service, AbstractAttributeNameService)
    assert isinstance(attribute_name_service, AttributeNameServiceSQL)

    return attribute_name_service


def random_attribute_name(rule: RuleType, order=()):
    return {
        "name": random_string(6),
        "authorityNamespace": f"https://{random_string(7, lcase=True)}.example.com",
        "rule": rule.to_string(),
        "order": order,
        "state": State,
    }


def test_create_namespace_retrieve_get(
    attribute_name_service: AbstractAttributeNameService,
):
    new_name = random_attribute_name(RuleType.ANY_OF)
    new_name_obj = AttributeName.from_raw_dict(new_name)
    attribute_name_service.create(new_name)
    retrieved = attribute_name_service.get(
        new_name_obj.authorityNamespace, new_name_obj.name
    )
    assert retrieved
    assert isinstance(retrieved, dict)
    assert retrieved["name"] == new_name["name"]
    assert retrieved["authorityNamespace"] == new_name["authorityNamespace"]
    assert retrieved["rule"] == new_name["rule"]

    # Should also be able to retrieve with get_many
    retrieved_many = attribute_name_service.get_many([new_name_obj.uri])
    assert isinstance(retrieved_many, list)
    found = False
    for r in retrieved_many:
        assert r
        assert isinstance(r, dict)
        if (
            r["name"] == new_name["name"]
            and r["authorityNamespace"] == new_name["authorityNamespace"]
        ):
            assert r["rule"] == new_name["rule"]
            found = True
    assert found

    # Service must not create duplicate
    with pytest.raises(AttributeExistsError):
        attribute_name_service.create(new_name)


def test_malformed_attribute(attribute_name_service: AbstractAttributeNameService):
    new_name = random_attribute_name(RuleType.ANY_OF)
    name_obj = AttributeName.from_raw_dict(new_name)

    # Can't patch before attribute is created in the database
    with pytest.raises(NotFound):
        attribute_name_service.patch(
            attribute_name=name_obj.name,
            namespace=name_obj.authorityNamespace,
            body=new_name,
        )

    # Create attribute in database
    attribute_name_service.create(new_name)

    # Dict doesn't have required fields
    with pytest.raises(MalformedAttributeError):
        attribute_name_service.update(
            {"invalid": 0}, new_name["name"], namespace=new_name["authorityNamespace"]
        )
