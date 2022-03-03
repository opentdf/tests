import pytest  # noqa: F401

import os
import sys
import json
import jwt
import functools
import base64
import pytest

import tdf3_kas_core

from unittest.mock import MagicMock, patch

from tdf3_kas_core.models import ClaimsAttributes
from tdf3_kas_core.models import Context
from tdf3_kas_core.models import EntityAttributes
from tdf3_kas_core.models import KeyAccess
from tdf3_kas_core.models import KeyMaster
from tdf3_kas_core.models import Claims

from tdf3_kas_core.services import *

from tdf3_kas_core.util import get_private_key_from_disk
from tdf3_kas_core.util import get_public_key_from_disk


KEYCLOAK_ACCESS_TOKEN = """eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI5a3VoOTdoakRXX2IyQkNmM243b1lTRXo5bUVaVGtmMllrMDRaR2dlN3lNIn0.eyJleHAiOjE2MTkxMTc1NzMsImlhdCI6MTYxOTExNzI3MywianRpIjoiYjJiZWQxMzktMDkzYy00NTFlLWJkNjUtY2JiNjI1ZDQ4NzBlIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL3RkZiIsImF1ZCI6ImFjY291bnQiLCJzdWIiOiJiYTUxNjJjNC0wNmUxLTRjM2EtYTYwYy1jYTk1MjcyZjQ0ZTMiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJ0ZGYtY2xpZW50Iiwic2Vzc2lvbl9zdGF0ZSI6IjBkOGJmODA0LTQ1ZjktNDliNS05NzUyLWFjNzFlNjkzN2ZmNCIsImFjciI6IjEiLCJhbGxvd2VkLW9yaWdpbnMiOlsiaHR0cDovL2xvY2FsaG9zdDo4MDgwIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJlbWFpbCBwcm9maWxlIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJ2aXJ0cnVfZW50aXR5X29iamVjdCI6eyJhbGlhc2VzIjpbXSwiYXR0cmlidXRlcyI6W3sib2JqIjp7ImF0dHJpYnV0ZSI6Imh0dHBzOi8vZXhhbXBsZS5jb20vYXR0ci9DbGFzc2lmaWNhdGlvbi92YWx1ZS9TIn19LHsib2JqIjp7ImF0dHJpYnV0ZSI6Imh0dHBzOi8vZXhhbXBsZS5jb20vYXR0ci9DT0kvdmFsdWUvUFJYIn19XSwicHVibGljS2V5IjoiLS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS1cbk1JSUJJakFOQmdrcWhraUc5dzBCQVFFRkFBT0NBUThBTUlJQkNnS0NBUUVBek1hQXJaN1VwV3VaMWt6aVVvT1NcblU1RmVmaXVxN2UyZUpIaWF0Z2RMNk9WeER3UjhDM09KTDMwR0JQN0JaWVIxYWczSkNlOW11TURnd2xIY1p1NDlcbmhManZJc2ZFcGQ5ZlpKdTExL3RocnljbXhBZ2p6OEdKcExCRnJBSHpPLzRwUVdNdkpXQkppOHlNVm9abnVMTE1cbmhNUnlLZ3ZFRUU3ZVVzcjNHT0RUMlZYUEoyYlJMOHZnTTJNcURFVnhycDFUZVBISEkza2VpeWVGVGM1aDA5RThcblFvZ3A3ME1YMVRkdURzZVRKNmR5V1o3TkwySmFPenZFNmFmSk1kZCtJSVRCMmpuRm4xejdFaDVOKy96TnB3cmJcbjFJK29ranpmS1hHL3MrYVVyNWFiMnZGRmlNbWhmWWlyMm9OckhwTXRFcFhnclFycmxoOUpxUE4xQzZST0FiZ3pcbnVRSURBUUFCXG4tLS0tLUVORCBQVUJMSUMgS0VZLS0tLS1cbiIsInNjaGVtYVZlcnNpb246IjoiMS4yLjMiLCJ1c2VySWQiOiJ1c2VyMUB2aXJ0cnUuY29tIn0sInByZWZlcnJlZF91c2VybmFtZSI6InVzZXIxIn0.NzhxhaV0z41Sz_f1ID5Fn3j7FmGZizTtZ0GbpX3AeE7tBFJpgMOWbcQdJ9F-OYXipP_Q7sutK0jpBaUEhy9HY-ozJfJqADjqDAFYzcUkmbNg4T_4PCOZL1Bv5w61Ftu0i7NYcXLGtRZaACTByVQyUTByDY7eOvWtMnEGZ9aC7o9iV2sMHp9W632EDmv-OlzDME3VTmmIazhdLYmMQG0lFtC_qf5dXwT0l8LhuoMCs8g3e_j6OKBOo0uaDrxZ584JD9amvcIZ6CjeWCfSFghlxVQFdrE7Dn5SmWnqdp682qWS3aBylfjgx8sdgX05YK93pE-MHUVhu12swWpkjh1oYA"""

KEYCLOAK_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAian19orjts+wol1BxEXo5hx7OsfqKT2soU+3COG6/WSnphqBI2RRRvI07q0+LGGq9wRpDYPRu01RG0JIIqP3VptLOVmzDH8n6ckctvxPuYDlp1NqjAKOSlxhfaAwpCLOllGn+XkpMBUHduaPRb0fl5vaxWleNT11s9FrYTMJEAJcrf56YoWeQUnp5bBSPQcNlz+UjKuppoTeSl8sxtxT5iF3lYfwq3IL5UHrupm19WNOfw+1GdCgX30hppX0TRxDTpOu99kzL4tzbfOSuG+o2IgYe9Or9GKWkP5Fg2kAYyD/bu6IGAbq3O7VOARL0/t0zm8LxS+sYFMSIndFt82X9wIDAQAB
-----END PUBLIC KEY-----"""

CLIENT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAprXL2d2XLy76hxexI6ye
jp7/S0e+x84/hMcmNqi2FPw/Oforc9kUoJp7oGgnq72SjrKxXnnFXnnFbQCXRmiz
FQY1FRGebYfJbNBdPK8eWg2G6DoTH5wRX5spY8nvUyEM5X27Z6DM88nIVhJhVg4e
4FdCAd0brviaVLYtZq4LFSgjQRzat7GK3IZe4+MIRN/D2YfSFVosmhh3tvsc0BMC
+mxTZjkykE8OluOkikEPxJBIZ9NY/RptNL0/zaqMoSRVZnDAYloTSKDmTogk146h
nVmobbyo5m23ZIlqnPrd2wDjfkn578SHG5wxwtBvxaFQnBURvmYZg/jZKcsYxajQ
4wIDAQAB
-----END PUBLIC KEY-----"""

CLIENT_SIGNING_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAm1SpwGyP/lMKAYJs9bJxwX35Y2bF3wmKCO4LtGRT1A+eY7mB
iF0vrVaLSDoiofwF31MtYyMsrU8PgJwD671pN5JftndFJIq4Cw18vMTP7+jSpucj
4YhxGLWCJbd2Urhsz/KJuhvJJXpmpIrOr+L6wNQPqDk5iDK1qXE/OBN4MQRwOjR0
ww8RVq2sW3dIr+0oKVeWY5TlLZDyBCa+tsZJoTGr3kosCv5lmx78W93f2nM/Hvgx
1UQYNL8ZXmCZnh0bm4Z0OLA0RlxeQ3seC8V9AH4B5EaUMzz+j0lw+Qb/wQiRXA+c
u40miCMreg99N3jtGyjNJV475P1AlQh0nAz4rQIDAQABAoIBAHI5xkNNEm7SHe+S
PBJKUUEbJIQmlag42ZtLgqv7g3HUsoNfbZQcAu2TUQWiSsmYDbF290+KFFa2Zw4K
rQ900KUfLOd/ugbvQ/xMxMgEa21fZ1l5bHdz4Mds4vJdgdO+77XUA9gqirbW1hh2
Qxww7HlU+NaajmZL9C9Qqk7QcniIR1Bcka3N1v2lv7IbX45e6744zLE1jeda8Zyf
FDn7uZ+42jA35moBhJHXwt1KMYmSKb2QM+Dt6Z1TbeGV25UvxUuvaQQyXxyPQXTp
lgcpqhiBHYamUo8gGucAo2bluAwoxXG5TYF9pZ6/6Ytq3TpEEWc4FUyYV02A/MAJ
G+V7FsECgYEA0n0das5eb81bwhy2XNngYZpIneJKqg+qHT39a5VExKEZC4mvtDeh
KGL4lqX7EEtwuAi/jlpOBMuFAyn+4cFWABdTsO2jHYw6+z0PdZ/odL1qqtIycU73
fP7H4h2hvCzAuKIb+cwgLCdKKUZkiexTYa0ix/LHytAFU6YBVrpsSXkCgYEAvOp2
7a8g2xk25wFy8eHkkG97XBo6VPhaWTN/Rt2Oi9sJwOhjvevnx7aytjYmuVBU2sgw
tKRqh76zK2oxOa3IJWOEFXLUYgtbhRAHi6X3WeeLsjk053G5EiXFnIr3zXyK+uPA
ilkE+fj18jIHkIo77jv3nJ0wJXlBQoCdus0jz9UCgYAE7HJMtkkVOmuEDeHiKCKM
hexe7RUsBzPGfVW5N4OlSdNpJq5ae9akODRyaa2Gwwz+8Q1yCgC7MfuJiGjy5O/b
DrChed2P6mDS0anT6YqpeGjPWB1f8yXs4ZTRYDoRSca0Su52mGTEQ6MDdicR5tpI
daFTpgUwZE9Llp1/ZtrzmQKBgQCNoIlAb4aGO0T5shBmXh9oWOt2hQMuKHIzZXQJ
wJfZKYEKai48d9rv0nvwNnCZhSvYSTSaeJiU49aWuanlv+7IeO7Q1aF7T2BxRS8i
9m2VrQ0Bs/mBebRxcnfPgC9+kdvvc0cpcMtWS9q2k+Mv7TI4zCQ5+W3a6iiOnrWh
EaHDcQKBgQDL3fjaKZ68TG2/QS/fRGvJvLuZSolN2FhL+qmn0AF7ATHrAh0zt8vF
pXRw69UoUN8sBz+VwROgFoBm03yZUs1C+8KSd3FIDmVgc9ktD1WMmJn+PZc3ADH4
iJPjf/RI+tvX9NDoBPmAUwexFXWBIdreHCiR2ucLRnL8lT1XBYyQRg==
-----END RSA PRIVATE KEY-----"""

CLIENT_SIGNING_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAm1SpwGyP/lMKAYJs9bJx
wX35Y2bF3wmKCO4LtGRT1A+eY7mBiF0vrVaLSDoiofwF31MtYyMsrU8PgJwD671p
N5JftndFJIq4Cw18vMTP7+jSpucj4YhxGLWCJbd2Urhsz/KJuhvJJXpmpIrOr+L6
wNQPqDk5iDK1qXE/OBN4MQRwOjR0ww8RVq2sW3dIr+0oKVeWY5TlLZDyBCa+tsZJ
oTGr3kosCv5lmx78W93f2nM/Hvgx1UQYNL8ZXmCZnh0bm4Z0OLA0RlxeQ3seC8V9
AH4B5EaUMzz+j0lw+Qb/wQiRXA+cu40miCMreg99N3jtGyjNJV475P1AlQh0nAz4
rQIDAQAB
-----END PUBLIC KEY-----"""


@pytest.fixture
def with_idp():
    old_value = flags["idp"]
    flags["idp"] = True
    yield
    flags["idp"] = old_value


@pytest.fixture
def without_idp():
    old_value = flags["idp"]
    flags["idp"] = False
    yield
    flags["idp"] = old_value


# This partial is necessary because we're wrapping jwt.decode() and
# adding an option that turns off checks for token expiration.
# BUT, we're going to mock.patch() jwt.decode() itself, so we
# can't call jwt.decode() in the wrapper or we'll have infinite
# recursion.  So the solution is to save jwt.decode in a partial
# and call the partial.
jwt_decode = functools.partial(jwt.decode)


def jwt_decode_no_expiration(*args, **kwargs):
    kwargs.setdefault("options", {})
    # if you removed this next line, the access token would fail to
    # verify due to an expired timestamp.
    kwargs["options"].update({"verify_exp": False})
    return jwt_decode(*args, **kwargs)


def test_claims_object():
    TDF_CLAIMS = {
        "sub":"user@virtru.com",
        "tdf_claims":{
            "client_public_signing_key": CLIENT_SIGNING_PUBLIC_KEY,
            "entitlements":[
            {
                "entity_identifier":"clientsubjectId1-14443434-1111343434-asdfdffff",
                "entity_attributes":[
                {
                    "attribute":"https://example.com/attr/Classification/value/S",
                    "displayName":"classification"
                },
                {
                    "attribute":"https://example.com/attr/COI/value/PRX",
                    "displayName":"category of intent"
                }
                ]
            },
            {
                "entity_identifier":"user@virtru.com",
                "entity_attributes":[
                {
                    "attribute":"https://example.com/attr/Classification/value/S",
                    "displayName":"classification"
                },
                {
                    "attribute":"https://example.com/attr/COI/value/PRX",
                    "displayName":"category of intent"
                }
                ]
            }
            ]
        },
        "tdf_spec_version":"4.0.0"
    }

    return Claims.load_from_raw_data(TDF_CLAIMS)


class FakeKeyMaster:
    def get_key(self, name):
        public_key = get_public_key_from_disk("test", as_pem=True)
        private_key = get_private_key_from_disk("test", as_pem=True)
        if name == "KEYCLOAK-PUBLIC-tdf":
            return KEYCLOAK_PUBLIC_KEY
        elif name == "KAS-PRIVATE":
            return private_key
        raise Exception(f"Unknown test key: {name}")


def test_kas_public_rsa_key():
    """Test the getter for the KAS public key."""
    km = KeyMaster()
    km.set_key_path("KAS-PUBLIC", "PUBLIC", "test")
    expected = km.get_export_string("KAS-PUBLIC")
    actual = kas_public_key(km, "rsa:2048")
    assert actual == expected


def test_kas_public_ec_key():
    """Test the getter for the KAS public key."""
    km = KeyMaster()
    km.set_key_path("KAS-EC-SECP256R1-PUBLIC", "PUBLIC", "test")
    expected = km.get_export_string("KAS-EC-SECP256R1-PUBLIC")
    actual = kas_public_key(km, "ec:secp256r1")
    assert actual == expected


def test_ping():
    """Test the health ping."""
    expected = {"version": "1.2.3"}
    actual = ping("1.2.3")
    assert actual == expected


@patch("jwt.decode", side_effect=jwt_decode_no_expiration)
@patch("tdf3_kas_core.services._nano_tdf_rewrap")
@patch("tdf3_kas_core.services._tdf3_rewrap_v2", return_value=True)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object()
)
def test_rewrap_v2(entity_load_mock, tdf3_mock, nano_mock, jwt_mock, with_idp):
    """Test the rewrap_v2 service."""
    os.environ["KEYCLOAK_HOST"] = "https://keycloak.dev"
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}

    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": policy,
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    context.add("Authorization", f"Bearer {KEYCLOAK_ACCESS_TOKEN}")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    rewrap_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.services._nano_tdf_rewrap")
@patch("tdf3_kas_core.services._tdf3_rewrap", return_value=True)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object
)
def test_rewrap_v2_expired_token(entity_load_mock, tdf3_mock, nano_mock, with_idp):
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}
    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": policy,
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }
    context = Context()
    context.add("Authorization", f"Bearer {KEYCLOAK_ACCESS_TOKEN}")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    # This token is expired, should fail.
    # Actual exception is:  jwt.exceptions.ExpiredSignatureError
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        rewrap_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.services._nano_tdf_rewrap")
@patch("tdf3_kas_core.services._tdf3_rewrap", return_value=True)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object
)
def test_rewrap_v2_no_auth_header(entity_load_mock, tdf3_mock, nano_mock, with_idp):
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}
    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": policy,
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": "rsa:2048",
            }
        )
    }
    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    # Skip context.add("Authorization", ...)
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    # This token is expired, should fail.
    # Actual exception is:  jwt.exceptions.ExpiredSignatureError
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        rewrap_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.services._nano_tdf_rewrap")
@patch("tdf3_kas_core.services._tdf3_rewrap", return_value=True)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object
)
def test_rewrap_v2_invalid_auth_header(
    entity_load_mock, tdf3_mock, nano_mock, with_idp
):
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}

    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": policy,
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": "rsa:2048",
            }
        )
    }
    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    context.add("Authorization", f"Chair-er Token:{KEYCLOAK_ACCESS_TOKEN}")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    # This token is expired, should fail.
    # Actual exception is:  jwt.exceptions.ExpiredSignatureError
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        rewrap_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.services._nano_tdf_rewrap")
@patch("tdf3_kas_core.services._tdf3_rewrap", return_value=True)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object
)
def test_rewrap_v2_invalid_auth_jwt(entity_load_mock, tdf3_mock, nano_mock, with_idp):
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {"type": "remote", "url": "http://127.0.0.1:4000", "protocol": "kas"}
    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": policy,
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }

    context = Context()
    context.add("Authorization", "Bearer DO I LOOK LIKE A JWT TO YOU?")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    # This token is expired, should fail.
    # Actual exception is:  jwt.exceptions.ExpiredSignatureError
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        rewrap_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.models.KeyAccess.from_raw")
@patch("jwt.decode", side_effect=jwt_decode_no_expiration)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object()
)
def test_upsert_v2(entity_load_mock, jwt_mock, ka_mock):
    """Test the upsert_v2 service."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {
        "type": "remote",
        "url": "http://127.0.0.1:4000",
        "protocol": "kas",
        "type": "wrapped",
        "policyBinding": bytes.decode(
            base64.b64encode(str.encode(json.dumps("foo bar baz")))
        ),
        # this is not correct, but let's see if it makes the test pass
        "wrappedKey": bytes.decode(
            base64.b64encode(str.encode(json.dumps(KEYCLOAK_PUBLIC_KEY)))
        ),
    }
    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": bytes.decode(
                    base64.b64encode(str.encode(json.dumps(policy)))
                ),
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    context.add("Authorization", f"Bearer {KEYCLOAK_ACCESS_TOKEN}")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    upsert_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.models.KeyAccess.from_raw")
@patch("jwt.decode", side_effect=jwt_decode_no_expiration)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object()
)
def test_upsert_v2_no_auth_header(entity_load_mock, jwt_mock, ka_mock, with_idp):
    """Test the upsert_v2 service."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {
        "type": "remote",
        "url": "http://127.0.0.1:4000",
        "protocol": "kas",
        "type": "wrapped",
        "policyBinding": bytes.decode(
            base64.b64encode(str.encode(json.dumps("foo bar baz")))
        ),
        # this is not correct, but let's see if it makes the test pass
        "wrappedKey": bytes.decode(
            base64.b64encode(str.encode(json.dumps(KEYCLOAK_PUBLIC_KEY)))
        ),
    }
    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": bytes.decode(
                    base64.b64encode(str.encode(json.dumps(policy)))
                ),
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    # context.add("Authorization", "Bearer {0}".format(KEYCLOAK_ACCESS_TOKEN))
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        upsert_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.models.KeyAccess.from_raw")
@patch("jwt.decode", side_effect=jwt_decode_no_expiration)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object()
)
def test_upsert_v2_invalid_auth_header(entity_load_mock, jwt_mock, ka_mock, with_idp):
    """Test the upsert_v2 service."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {
        "type": "remote",
        "url": "http://127.0.0.1:4000",
        "protocol": "kas",
        "type": "wrapped",
        "policyBinding": bytes.decode(
            base64.b64encode(str.encode(json.dumps("foo bar baz")))
        ),
        # this is not correct, but let's see if it makes the test pass
        "wrappedKey": bytes.decode(
            base64.b64encode(str.encode(json.dumps(KEYCLOAK_PUBLIC_KEY)))
        ),
    }
    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": bytes.decode(
                    base64.b64encode(str.encode(json.dumps(policy)))
                ),
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    context.add("Authorization", f"Terr-or Token {KEYCLOAK_ACCESS_TOKEN}")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        upsert_v2(request_data, context, plugin_runner, key_master)
    assert True


@patch("tdf3_kas_core.models.KeyAccess.from_raw")
@patch("jwt.decode", side_effect=jwt_decode_no_expiration)
@patch(
    "tdf3_kas_core.models.Claims.load_from_raw_data", return_value=test_claims_object()
)
def test_upsert_v2_invalid_auth_jwt(entity_load_mock, jwt_mock, ka_mock, with_idp):
    """Test the upsert_v2 service."""
    expected_uuid = "1111-2222-33333-44444-abddef-timestamp"
    expected_canonical = "This is a canonical string"
    attributes = [
        {"attribute": "https://example.com/attr/Classification/value/S"},
        {"attribute": "https://example.com/attr/COI/value/PRX"},
    ]
    policy = {
        "uuid": "1111-2222-33333-44444-abddef-timestamp",
        "body": {"dataAttributes": attributes},
    }
    key_access = {
        "type": "remote",
        "url": "http://127.0.0.1:4000",
        "protocol": "kas",
        "type": "wrapped",
        "policyBinding": bytes.decode(
            base64.b64encode(str.encode(json.dumps("foo bar baz")))
        ),
        # this is not correct, but let's see if it makes the test pass
        "wrappedKey": bytes.decode(
            base64.b64encode(str.encode(json.dumps(KEYCLOAK_PUBLIC_KEY)))
        ),
    }

    data = {
        "requestBody": json.dumps(
            {
                "keyAccess": key_access,
                "policy": bytes.decode(
                    base64.b64encode(str.encode(json.dumps(policy)))
                ),
                "clientPublicKey": CLIENT_PUBLIC_KEY,
                "algorithm": None,
            }
        )
    }

    signedToken = jwt.encode(data, CLIENT_SIGNING_PRIVATE_KEY, "RS256")
    request_data = {"signedRequestToken": signedToken}

    context = Context()
    context.add("Authorization", "Bearer DO I LOOK LIKE A JWT TO YOU?")
    plugin_runner = MagicMock()
    key_master = FakeKeyMaster()
    with pytest.raises(tdf3_kas_core.errors.UnauthorizedError):
        upsert_v2(request_data, context, plugin_runner, key_master)
    assert True
