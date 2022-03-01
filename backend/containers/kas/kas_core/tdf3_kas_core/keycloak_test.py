"""Test the Keycloak module."""
import os
import pytest
import re
import json

from unittest.mock import MagicMock, patch
from flask import Flask, Response
from flask.testing import FlaskClient

from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import get_public_key_from_disk

from tdf3_kas_core.authorized import unsafe_decode_jwt

from tdf3_kas_core.errors import KeyNotFoundError

import tdf3_kas_core.keycloak as keycloak

KEYCLOAK_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAian19orjts+wol1BxEXo5hx7OsfqKT2soU+3COG6/WSnphqBI2RRRvI07q0+LGGq9wRpDYPRu01RG0JIIqP3VptLOVmzDH8n6ckctvxPuYDlp1NqjAKOSlxhfaAwpCLOllGn+XkpMBUHduaPRb0fl5vaxWleNT11s9FrYTMJEAJcrf56YoWeQUnp5bBSPQcNlz+UjKuppoTeSl8sxtxT5iF3lYfwq3IL5UHrupm19WNOfw+1GdCgX30hppX0TRxDTpOu99kzL4tzbfOSuG+o2IgYe9Or9GKWkP5Fg2kAYyD/bu6IGAbq3O7VOARL0/t0zm8LxS+sYFMSIndFt82X9wIDAQAB
-----END PUBLIC KEY-----"""

fakeDecodedToken = """
{
  "exp": 1623693824,
  "iat": 1623693524,
  "jti": "cb0765ea-80a6-4056-9f55-1a41e644c87a",
  "iss": "http://localhost:8080/auth/realms/tdf",
  "aud": "account",
  "sub": "8e6de020-3617-436e-a497-feded4c64f10",
  "typ": "Bearer",
  "azp": "tdf-client",
  "session_state": "423b06ff-fc8d-4f9f-8266-57b07ce340dd",
  "acr": "1",
  "allowed-origins": [
    "http://keycloak-http"
  ],
  "realm_access": {
    "roles": [
      "default-roles-tdf",
      "offline_access",
      "uma_authorization"
    ]
  },
  "resource_access": {
    "account": {
      "roles": [
        "manage-account",
        "manage-account-links",
        "view-profile"
      ]
    }
  },
  "scope": "profile email",
  "email_verified": false,
  "preferred_username": "user1"
}
"""


class FakeKeyMaster:
    def set_key_pem(self, key_name, key_type, pem_key):
        """Set a key directly with a PEM encoded string."""

    def get_key(self, name):
        public_key = get_public_key_from_disk("test", as_pem=True)
        private_key = get_private_key_from_disk("test", as_pem=True)
        if name == "KEYCLOAK-PUBLIC-tdf":
            return KEYCLOAK_PUBLIC_KEY
        elif name == "KAS-PRIVATE":
            return private_key
        raise KeyNotFoundError(f"Unknown test key: {name}")


class MockResponse:
    def __init__(self, json_data, status_code):
        self.fakejson = json_data
        self.status_code = status_code
        self.ok = status_code < 399

    def json(self):
        return self.fakejson


def mocked_requests_get(*args, **kwargs):
    fakeKeycloakPKResp = json.loads(
        '{"realm":"tdf","public_key":"MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAj/QUmaMS/4ANsz3OKRH8vU8Dw+iyVEnvgkA1Z6a9twaZglQUDegOVZwqSImI6UNsESmJMcU1l0zHNsxM/C9d+ttuZOIdnWDtQL6IrX5FBMXA+AFAIAf/SpCDZEkrjVjfhn5fH76dI7lETZrMtWpS3O0fXId63yKaOe4+HddSZ+l7J2meAuHqpBkTC60MOmFiwgCJ11xFIEKEUne10smBBtsND5uB75oceZSF/gNdEltk2u7AQLzToL50Jcnp9CV1fOQ8bbe0J2NwKyaYUX2/qBKhGOB1k0y/eHFsJ2ceQEfWzLr1z/cuH208/TAxAq2QjggokIRIm2DpnwcntSFpkQIDAQAB","token-service":"http://keycloak-http:80/auth/realms/tdf/protocol/openid-connect","account-service":"http://keycloak-http:80/auth/realms/tdf/account","tokens-not-before":0}'
    )
    if "/auth/realms/" in args[0]:
        return MockResponse(fakeKeycloakPKResp, 200)

    return MockResponse(None, 404)


def mocked_requests_get_fails(*args, **kwargs):
    return MockResponse(None, 500)


@patch("requests.Session.get", side_effect=mocked_requests_get)
def test_get_keycloak_public_key_fails_without_required_env(mock_get):
    """Tests that fetching KC pubkey, but without crucial
    env vars set, will raise."""
    with pytest.raises(Exception, match=r"KEYCLOAK_HOST"):
        del os.environ["KEYCLOAK_HOST"]
        pubkey = keycloak.get_keycloak_public_key("tdf")
    # Should bail before it makes a request if the env vars aren't set.
    assert mock_get.called == False


@patch("requests.Session.get", side_effect=mocked_requests_get)
def test_get_keycloak_public_key_succeeds_with_required_env(mock_get):
    """Tests that fetching KC pubkey, but with crucial
    env vars set, will fetch pubkey."""
    os.environ["KEYCLOAK_HOST"] = "https://mykc.com"
    pubkey = keycloak.get_keycloak_public_key("tdf")
    assert mock_get.called == True
    assert pubkey


@patch("requests.Session.get", side_effect=mocked_requests_get)
def test_try_extract_realm_returns_realmkey(mock_get):
    token = json.loads(fakeDecodedToken)
    realmKey = keycloak.try_extract_realm(token)
    assert realmKey == "tdf"


@patch("requests.Session.get", side_effect=mocked_requests_get)
def test_load_realm_key_prefers_cached_key(mock_get):
    key_master = FakeKeyMaster()
    realm = "tdf"
    os.environ["KEYCLOAK_HOST"] = "https://mykc.com"
    realmKey = keycloak.load_realm_key(realm, key_master)
    assert mock_get.called == False
    assert realmKey


@patch("requests.Session.get", side_effect=mocked_requests_get)
def test_load_realm_key_fetches_uncached_key(mock_get):
    key_master = FakeKeyMaster()
    realm = "someRealm"
    os.environ["KEYCLOAK_HOST"] = "https://mykc.com"
    realmKey = keycloak.load_realm_key(realm, key_master)
    assert mock_get.called == True
    assert realmKey


@patch("requests.Session.get", side_effect=mocked_requests_get_fails)
def test_uncached_key_fetch_fails_returns_falsy_empty(mock_get):
    key_master = FakeKeyMaster()
    realm = "someRealm"
    realmKey = ""
    os.environ["KEYCLOAK_HOST"] = "https://mykc.com"
    realmKey = keycloak.load_realm_key(realm, key_master)
    assert mock_get.called == True
    assert not realmKey
