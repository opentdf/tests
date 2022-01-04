"""Authorized function."""

import jwt
import logging
import os
import re

from cryptography.hazmat.primitives import serialization
from datetime import datetime, timedelta

from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import JWTError
from tdf3_kas_core.errors import UnauthorizedError


logger = logging.getLogger(__name__)

JWT_EXCEPTIONS = (
    jwt.exceptions.InvalidTokenError,
    jwt.exceptions.DecodeError,
    jwt.exceptions.InvalidSignatureError,
    jwt.exceptions.ExpiredSignatureError,
    jwt.exceptions.InvalidAudienceError,
    jwt.exceptions.InvalidIssuerError,
    jwt.exceptions.InvalidIssuedAtError,
    jwt.exceptions.ImmatureSignatureError,
    jwt.exceptions.InvalidKeyError,
    jwt.exceptions.InvalidAlgorithmError,
    jwt.exceptions.MissingRequiredClaimError,
)

# Number of seconds of leeway for expiry in token validation
# If you need more than 2 mins of leeway, you have a server config problem that you need to fix.
# NOTE: When we drop support <3.8, add `: typing.Final` below
max_leeway = 120
default_leeway = 30
assert 0 <= default_leeway <= max_leeway
leeway = default_leeway


try:
    suggested_leeway = int(os.environ["KAS_JWT_LEEWAY"])
    if 0 <= suggested_leeway <= max_leeway:
        leeway = suggested_leeway
        logger.info("KAS_JWT_LEEWAY set to [%s]", suggested_leeway)
    else:
        logger.error("KAS_JWT_LEEWAY out of bounds [%s] [%s]", suggested_leeway, max_leeway)
except KeyError:
    pass
except TypeError:
    logger.error("Invalid KAS_JWT_LEEWAY", exc_info=True)

def unpack_rs256_jwt(jwt_string, public_key):
    """Unpack asymmetric JWT using RSA 256 public key."""
    try:
        return jwt.decode(jwt_string, public_key, algorithms=["RS256"], leeway=leeway)
    except JWT_EXCEPTIONS as err:
        raise JWTError("Error decoding rs256 JWT") from err


def pack_rs256_jwt(payload, private_key, *, exp_hrs=None, exp_sec=None):
    """Create asymmetric JWT with RSA 256 private key."""
    try:
        if exp_hrs:
            now = datetime.now()
            delta = timedelta(hours=exp_hrs)
            payload["exp"] = (now + delta).timestamp()
        elif exp_sec:
            now = datetime.now()
            delta = timedelta(seconds=exp_sec)
            payload["exp"] = (now + delta).timestamp()
        return jwt.encode(payload, private_key, algorithm="RS256")
    except JWT_EXCEPTIONS as err:
        raise JWTError("Error encoding rs256 JWT") from err


JWT_RE = re.compile(r"^[a-zA-Z0-9\-_]+?\.[a-zA-Z0-9\-_]+?\.([a-zA-Z0-9\-_]+)?$")


def looks_like_jwt(jwt):
    match = JWT_RE.match(jwt)
    return bool(match)


def unsafe_decode_jwt(auth_token):
    try:
        # grab information out of the token without verifying it.
        decoded = jwt.decode(
            # This could be an access_token or refresh_token
            auth_token,
            options={"verify_signature": False, "verify_aud": False},
            algorithms=["RS256", "ES256", "ES384", "ES512"],
        )
    except Exception as e:
        raise UnauthorizedError("Invalid JWT") from e

    return decoded


def authorized(public_key, auth_token):
    """Raise error if the public key does not validate the JWT auth_token."""
    try:
        unpack_rs256_jwt(auth_token, public_key)
        return True

    except Exception as e:
        raise AuthorizationError("Not authorized") from e


def authorized_v2(public_key, auth_token):

    decoded = unsafe_decode_jwt(auth_token)

    audience = decoded["aud"]

    unverified_headers = jwt.get_unverified_header(auth_token)
    algorithms = unverified_headers["alg"]

    try:
        decoded = jwt.decode(
            auth_token, public_key, audience=audience, algorithms=["RS256", "ES256", "ES384", "ES512"], leeway=leeway
        )
    except Exception as e:
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        logger.warning("Unverifiable claims [%s] found in [%s], public_key=[%s]", decoded, auth_token, pem)
        raise UnauthorizedError("Not authorized") from e
    return decoded
