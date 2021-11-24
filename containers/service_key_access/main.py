import base64
import json
import os
import sys
from enum import Enum
from typing import Optional

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from pydantic import BaseModel

from tdf3_kas_core.models import KeyMaster, RewrapPluginRunner, Entity
from tdf3_kas_core.services import _nano_tdf_rewrap, _tdf3_rewrap

app = FastAPI()

private_key = ""


@app.on_event("startup")
async def startup():
    global private_key
    private_key = str.encode(os.getenv("KAS_PRIVATE_KEY"))
    serialization.load_pem_private_key(private_key, password=None)
    eas_certificate = x509.load_pem_x509_certificate(
        str.encode(os.getenv("EAS_CERTIFICATE"))
    )
    eas_certificate.public_bytes(
        encoding=serialization.Encoding.PEM,
    ).decode("utf-8")


@app.on_event("shutdown")
async def shutdown():
    pass


@app.get("/", include_in_schema=False)
async def read_semver():
    return {"Hello": "World"}


class ProbeType(str, Enum):
    liveness = "liveness"
    readiness = "readiness"


@app.get("/healthz", include_in_schema=False)
async def read_liveness(probe: ProbeType = ProbeType.liveness):
    return {"healthz": probe}


class EntityObject(BaseModel):
    publicKey: str
    userId: str
    cert: Optional[str] = None
    exp: Optional[float] = None
    aliases: Optional[list] = []
    attributes: list

    class Config:
        schema_extra = {
            "example": {
                "aliases": ["string"],
                "attributes": [
                    {
                        "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
                    }
                ],
                "cert": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
                "exp": 1611387008.338341,
                "publicKey": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA2Q9axUqaxEfhOO2+0Xw+\nswa5Rb2RV0xeTX3GC9DeORv9Ip49oNy+RXvaMsdNKspPWYZZEswrz2+ftwcQOSU+\nefRCbGIwbSl8QBfKV9nGLlVmpDydcAIajc7YvWjQnDTEpHcJdo9y7/oogG7YcEmq\nS3NtVJXCmbc4DyrZpc2BmZD4y9417fSiNjTTYY3Fc19lQz07hxDQLgMT21N4N0Fz\nmD6EkiEpG5sdpDT/NIuGjFnJEPfqIs6TnPaX2y1OZ2/JzC+mldJFZuEqJZ/6qq/e\nYlp04nWrSnXhPpTuxNZ5J0GcPbpcFgdT8173qmm5m5jAjiFCr735lH7USl15H2fW\nTwIDAQAB\n-----END PUBLIC KEY-----\n",
                "schemaVersion": "1.1.0",
                "userId": "Charlie_1234",
            }
        }


class Metadata(BaseModel):
    data: dict


class KeyAccess(BaseModel):
    type: str
    url: str
    protocol: str
    wrappedKey: str
    policyBinding: str
    # metadata: Metadata


class WrappedKeyRequest(BaseModel):
    policy: str
    entity: EntityObject
    authToken: str
    algorithm: Optional[str] = None
    keyAccess: KeyAccess


class WrappedKey(BaseModel):
    entityWrappedKey: str


@app.post("/rewrap", response_model=WrappedKey)
async def rewrap(request: WrappedKeyRequest):
    # authToken
    try:
        jwt.decode(
            request.authToken,
            request.entity.publicKey,
            algorithms=["RS256", "ES256", "ES384", "ES512"],
        )
    except Exception as e:
        raise AuthorizationError("Not authorized") from e
    context = {}
    key_master = KeyMaster()
    key_master.set_key_pem("KAS-PRIVATE", "PRIVATE", private_key)
    plugin_runner = RewrapPluginRunner()
    # entity
    entity_public_key = serialization.load_pem_public_key(
        str.encode(request.entity.publicKey)
    )
    entity = Entity(request.entity.userId, entity_public_key)
    if request.algorithm == "ec:secp256r1":
        return _nano_tdf_rewrap(
            request.dict(), context, plugin_runner, key_master, entity
        )
    else:
        return _tdf3_rewrap(request.dict(), context, plugin_runner, key_master, entity)


def construct_from_raw_canonical(canonical):
    """Build a policy object up from the raw canonical form.

    The canonical raw form is a base64 encoded version of the policy,
    encoded as string in json form. A copy of this canonical string is
    preserved as is for use in hmac validation.  Note that this string
    is not to be trusted as a representation of the policy as changes
    may occur in the attribute list and/or the dissem list.
    """
    raw_policy = json.JSONDecoder().decode(
        bytes.decode(base64.b64decode(str.encode(canonical)))
    )

    if isinstance(raw_policy, str):  # special case for remote types
        return {"uuid": raw_policy, "canonical": canonical}

    else:  # all other types
        # Construct an "empty" policy object
        if "uuid" not in raw_policy:
            raise PolicyError("PolicyError: Polices must have uuids")

        uuid = raw_policy["uuid"]
        if not isinstance(uuid, str):
            raise PolicyError("PolicyError: UUID is not a string")

        return {
            "uuid": raw_policy,
            "canonical": canonical,
            "dissem": raw_policy["body"]["dissem"],
            "dataAttributes": raw_policy["body"]["dataAttributes"],
        }

    # wrapped_key = base64.b64decode(raw_wrapped_key)
    # crypto = Crypto(wrap_method)
    # plain_key = crypto.decrypt(wrapped_key, private_unwrap_key)
    # hmac_message = str.encode(canonical_policy)
    # hmac_binding = base64.b64decode(str.encode(kao.policy_binding))
    # perform_hmac_check(hmac_binding, hmac_message)
    # # Policies currently work with a single KAS environment.
    # # Future implementations may support a multi-KAS environment.
    # object_key = WrappedKey.from_raw(wrapped_key, private_key)


class Error(Exception):
    """The base class for custom expressions."""

    def __init__(self, message=None):
        """Record an optional message string."""
        self.message = message


class PolicyError(Error):
    """Raise if a policy is malformed."""


class PolicyBindingError(Error):
    """Raise if a policy is malformed."""


class AuthorizationError(Error):
    """Raise if a authToken is malformed."""


class KeyAccessError(Error):
    """Raise if a key access is malformed."""


if __name__ == "__main__":
    print(json.dumps(app.openapi()), file=sys.stdout)
