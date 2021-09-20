"""Test the attribute service function."""

import json
import logging
import os
from typing import List

import jwt
import pytest  # noqa: F401

from .abstract_attribute_service import AbstractAttributeService
from .attribute_service_setup import get_initial_attribute_urls, setup_attribute_service
from .sql import AttributeServiceSql
from ..eas_config import EASConfig
from ..errors import AttributeExistsError, MalformedAttributeError, NotFound
from ..models import AttributeValue, State
from ..util import random_string

logger = logging.getLogger(__name__)

DEFAULT_NAMESPACE = EASConfig.get_instance().get_item("DEFAULT_NAMESPACE")
WORKING_DIR = os.getcwd()
TEST_PATH = os.path.join(WORKING_DIR, "src", "services", "test_files")
TEST_KEY_PATH = os.path.join(TEST_PATH, "key_stash")

PRIVATE_KEY_PATH = os.path.join(TEST_KEY_PATH, "eas-private.pem")
with open(PRIVATE_KEY_PATH, "r") as f:
    EAS_PRIVATE_KEY = f.read()

PUBLIC_KEY_PATH = os.path.join(TEST_KEY_PATH, "eas-public.pem")
with open(PUBLIC_KEY_PATH, "r") as f:
    EAS_CERTIFICATE = f.read()

PUBLIC_ATTR_KEY_PATH = os.path.join(TEST_KEY_PATH, "kas-public.pem")
with open(PUBLIC_ATTR_KEY_PATH, "r") as f:
    DEFAULT_ATTR_PUB_KEY = f.read()


@pytest.fixture(scope="session")
def attribute_service(request):
    """All attribute service tests should be run on all implementations."""
    assert EAS_PRIVATE_KEY is not None
    assert EAS_CERTIFICATE is not None
    assert DEFAULT_ATTR_PUB_KEY is not None

    print(f"setup fixture = entity_service")
    attribute_service = setup_attribute_service(
        eas_private_key=EAS_PRIVATE_KEY,
        kas_url="http://localhost:4000",
        kas_certificate=DEFAULT_ATTR_PUB_KEY,
    )
    assert isinstance(attribute_service, AbstractAttributeService)
    assert isinstance(attribute_service, AttributeServiceSql)
    return attribute_service


def test_get_initial_attribute_urls():
    """Test the read utility. Does not use attribute service itself."""
    urls_path = os.path.join(TEST_PATH, "attribute_urls.json")
    logger.debug("URLS path = %s", urls_path)
    with open(urls_path, "r") as u_file:
        urls_json = u_file.read()

    expected = json.loads(urls_json)

    actual = get_initial_attribute_urls(urls_path)

    # Since these are dicts they are hard to compare. Converting them to
    # models first.
    to_model = lambda u: AttributeValue(
        u, kas_url="no:where", pub_key="super secret string"
    )
    expected_models = [to_model(x) for x in expected]
    actual_models = [to_model(x) for x in actual]

    assert set(actual_models) == set(expected_models)


def test_attribute_service_create_one(attribute_service):
    """Test create one attribute."""

    attribute_url = random_attribute()
    created = attribute_service.create({"attribute": attribute_url})

    # make sure it returns the attribute
    assert isinstance(created, AttributeValue)
    assert created.attribute == attribute_url

    # retrieve the attribute and make sure it is correct
    actual_list = attribute_service.retrieve_jwt([attribute_url])

    assert len(actual_list) == 1
    actual = actual_list[0]
    actual_jwt = actual["jwt"]

    actual_payload = jwt.decode(actual_jwt, EAS_CERTIFICATE, algorithms=["RS256"])

    assert actual_payload["attribute"] == attribute_url


def test_attribute_service_create_with_new_namespace(
    attribute_service: AbstractAttributeService,
):
    """Test create one attribute."""

    attribute_url = random_attribute_new_namespace()
    attribute_obj = AttributeValue.from_uri(attribute_url)
    created = attribute_service.create({"attribute": attribute_url})

    # make sure it returns the attribute
    assert isinstance(created, AttributeValue)
    assert created.attribute == attribute_url

    # retrieve the attribute and make sure it is correct
    actual_list = attribute_service.retrieve([attribute_url])
    assert isinstance(actual_list, list)
    assert len(actual_list) == 1
    actual = actual_list[0]
    assert isinstance(actual, AttributeValue)

    assert actual.attribute == attribute_obj.attribute
    assert actual.state == State.ACTIVE
    assert actual.__eq__(attribute_obj)


def test_attribute_service_create_missing_url(attribute_service):
    """Attribute body must be present."""
    with pytest.raises(MalformedAttributeError):
        attribute_service.create({"display_name": "some name"})


def test_attribute_service_create_duplicate(attribute_service):
    attribute_url = random_attribute()
    attribute_service.create(
        {
            "attribute": attribute_url,
            "display_name": "instance 1",
        }
    )
    assert attribute_service.retrieve_jwt([attribute_url])
    with pytest.raises(AttributeExistsError):
        attribute_service.create(
            {
                "attribute": attribute_url,
                "display_name": "instance 2",
            }
        )


def test_attribute_service_autocreate_namespace(attribute_service):
    attribute_url = random_attribute_new_namespace()
    attr_obj = AttributeValue.from_uri(attribute_url)
    attribute_service.create(
        {
            "attribute": attribute_url,
            "display_name": "instance 1",
        }
    )
    retrieved = attribute_service.retrieve_jwt([attribute_url])
    assert retrieved

    values = attribute_service.get_values_for_name(
        attr_obj.authorityNamespace, attr_obj.name
    )
    assert len(values) == 1
    assert values[0]["attribute"] == attribute_url

    assert attribute_service.attr_name_exists(
        attr_obj.authorityNamespace, attr_obj.name
    )

    assert attribute_service.authority_namespace_exists(attr_obj.authorityNamespace)


def test_attribute_service_retrieve_all_with_none(attribute_service):
    """Test retrieve with no argument."""
    attribute_urls = []
    for _ in range(3):
        attribute_urls.append(random_attribute())

    for attribute_url in attribute_urls:
        attribute_service.create({"attribute": attribute_url})
    actual = attribute_service.retrieve_jwt()

    assert len(actual) >= 3
    assert actual[0] != actual[1]
    assert actual[1] != actual[2]
    assert actual[2] != actual[0]

    all_attribute_urls = extract_urls(actual)

    assert attribute_urls[0] in all_attribute_urls
    assert attribute_urls[1] in all_attribute_urls
    assert attribute_urls[2] in all_attribute_urls


def test_attribute_service_retrieve_all_empty_list(attribute_service):
    """Test retrieve with an empty list."""
    attribute_urls = []
    for _ in range(3):
        attribute_urls.append(random_attribute())

    for attribute_url in attribute_urls:
        attribute_service.create({"attribute": attribute_url})
    actual = attribute_service.retrieve_jwt([])

    assert len(actual) >= 3
    all_attribute_urls = extract_urls(actual)

    assert attribute_urls[0] in all_attribute_urls
    assert attribute_urls[1] in all_attribute_urls
    assert attribute_urls[2] in all_attribute_urls


def extract_urls(actual: List[dict]):
    all_attribute_urls = []
    for actual_record in actual:
        actual_jwt = actual_record["jwt"]
        actual_payload = jwt.decode(actual_jwt, EAS_CERTIFICATE, algorithms=["RS256"])
        all_attribute_urls.append(actual_payload["attribute"])
    return all_attribute_urls


def test_attribute_service_retrieve_some(attribute_service):
    """Test the constructor."""
    attribute_urls = []
    for _ in range(5):
        attribute_urls.append(random_attribute())

    for attribute_url in attribute_urls:
        attribute_service.create({"attribute": attribute_url})
    # retrieve a subset of the new attributes.
    expected = [
        attribute_urls[2],
        attribute_urls[4],
    ]
    actual = attribute_service.retrieve_jwt(expected)

    assert len(actual) == 2
    all_attribute_urls = extract_urls(actual)
    assert attribute_urls[2] in all_attribute_urls
    assert attribute_urls[4] in all_attribute_urls


def test_attribute_service_retrieve_negative(attribute_service):
    attribute_url = random_attribute()
    assert not attribute_service.retrieve_jwt([attribute_url])
    assert not attribute_service.retrieve([attribute_url])

    # Throws if not given a list
    with pytest.raises(MalformedAttributeError):
        attribute_service.retrieve(attribute_url)


def test_attribute_service_update(attribute_service):
    attribute_url = random_attribute()
    attribute_service.create({"attribute": attribute_url})

    display_name = random_string()
    attribute_value = AttributeValue.from_raw_dict(
        {
            "attribute": attribute_url,
            "displayName": display_name,
            "kasUrl": "no:where",
            "pubKey": DEFAULT_ATTR_PUB_KEY,
        }
    )

    attribute_service.update(attribute_value)

    raw_result = attribute_service.retrieve_jwt([attribute_url])
    assert type(raw_result) is list
    assert len(raw_result) == 1
    actual = raw_result[0]
    actual_jwt = actual["jwt"]

    actual_payload = jwt.decode(actual_jwt, EAS_CERTIFICATE, algorithms=["RS256"])

    assert actual_payload["displayName"] == attribute_value.display_name
    assert actual_payload["kasUrl"] == attribute_value.kas_url
    assert actual_payload["pubKey"] == attribute_value.pub_key
    assert actual_payload["attribute"] == attribute_url


def test_attribute_service_update_malformed(attribute_service):
    # if not an attribute_value, should raise error.
    malformed = {"attribute": "invalid"}
    with pytest.raises(MalformedAttributeError):
        attribute_service.update(malformed)


def test_attribute_service_delete(attribute_service):
    attribute_url = random_attribute()
    # Can't delete if not created yet
    with pytest.raises(NotFound):
        attribute_service.delete(attribute_url)

    attribute_service.create(
        {
            "attribute": attribute_url,
            "display_name": "attr to delete",
        }
    )
    # Assert it was created
    assert attribute_service.retrieve_jwt([attribute_url])
    # Delete should return attribute if attribute was deleted.
    result = attribute_service.delete(attribute_url)
    assert result
    assert result.state == State.INACTIVE


def random_attribute():
    return f"{DEFAULT_NAMESPACE}/attr/test/value/{random_string()}"


def random_attribute_new_name():
    return f"{DEFAULT_NAMESPACE}/attr/{random_string()}/value/{random_string()}"


def random_attribute_new_namespace():
    return f"https://{random_string(lcase=True)}.com/attr/{random_string()}/value/{random_string()}"
