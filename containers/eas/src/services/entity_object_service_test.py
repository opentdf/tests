"""Test create entity object."""

import pytest

from .attribute_service_setup import setup_attribute_service
from .entity_object_service import EntityObjectService
from .entity_service_setup import setup_entity_service
from .entity_attr_rel_setup import setup_entity_attr_rel_service
from ..errors import AuthorizationError, EasRequestError

client_public_key = """
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC+6gvHdCUCjnc4hSMwbdIIspk4
69pVAzjjb8tDJsCH/QpiK9vXe4nDZ7p9kiw2ACw0fkWaPnApKBwXNB9Nd9Sf+XFt
cIzdqKKBcAqZZCu2pA729amNRug9DoZdkstaBG+VfTxXhdzQRSTxxqJQWgdV8ejK
kt4D1M6pAiTkAyD0eQIDAQAB
-----END PUBLIC KEY-----
"""


@pytest.fixture
def entity_object_service():
    # Create the service instances
    ear_service = setup_entity_attr_rel_service()
    entity_service = setup_entity_service(ear_service)
    attribute_service = setup_attribute_service()
    return EntityObjectService(entity_service, attribute_service)


def test_entity_object_generate(entity_object_service):
    """EOS.generate makes a sensible thing."""
    eo = entity_object_service.generate(userId="bob_5678", publicKey=client_public_key)
    assert eo["userId"] == "bob_5678"
    assert eo["cert"]


def test_entity_object_not_found(entity_object_service):
    """EOS.generate throws 'unauthorized' for unrecognized users."""
    with pytest.raises(AuthorizationError) as _:
        entity_object_service.generate(userId="unknown", publicKey=client_public_key)


def test_entity_object_is_inactive(entity_object_service):
    """EOS.generate throws 'unauthorized' for inactive entity."""
    with pytest.raises(AuthorizationError) as _:
        entity_object_service.generate(userId="tom_1234", publicKey=client_public_key)


def test_entity_object_generate_bogus(entity_object_service):
    """EOS.generate fails on bad keys."""
    # Expect the exception.
    invalid_public_key = "bogusdata"
    with pytest.raises(EasRequestError) as _:
        entity_object_service.generate(userId="user1", publicKey=invalid_public_key)
