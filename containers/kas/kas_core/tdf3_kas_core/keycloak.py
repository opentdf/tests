"""Keycloak function."""

import os
import logging
import requests
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from tdf3_kas_core.errors import KeyNotFoundError
from tdf3_kas_core.errors import AuthorizationError

from tdf3_kas_core.authorized import unsafe_decode_jwt

logger = logging.getLogger(__name__)


def _get_keycloak_host():
    kc_host = os.environ.get("KEYCLOAK_HOST")
    if not kc_host:
        raise AuthorizationError("KEYCLOAK_HOST not set! Can't fetch keys")

    return kc_host


def get_retryable_request():
    retry_strategy = Retry(total=3, backoff_factor=1)

    adapter = HTTPAdapter(max_retries=retry_strategy)

    http = requests.Session()
    http.mount("https://", adapter)
    http.mount("http://", adapter)
    return http


# Given a realm ID, request that realm's public key from Keycloak's endpoint
#
# If anything fails, raise an exception
#
# TODO Consider replacing the endpoint here with the OIDC JWKS endpoint
# Keycloak exposes: `/auth/realms/{realm-name}/.well-known/openid-configuration`
# This is a low priority though since it doesn't save us from having to get the
# realmId first and so is a largely cosmetic difference
def get_keycloak_public_key(realmId):
    KEYCLOAK_HOST = _get_keycloak_host()
    url = f"{KEYCLOAK_HOST}/auth/realms/{realmId}"

    http = get_retryable_request()

    response = http.get(
        url, headers={"Content-Type": "application/json"}, timeout=5  # seconds
    )

    if not response.ok:
        logger.warning("No public key found for Keycloak realm %s", realmId)
        raise KeyNotFoundError(
            f"Failed to download Keycloak public key: [{response.text}]"
        )

    try:
        resp_json = response.json()
    except:
        logger.warning(
            f"Could not parse response from Keycloak pubkey endpoint: {response}"
        )
        raise

    keycloak_public_key = f"""-----BEGIN PUBLIC KEY-----
{resp_json['public_key']}
-----END PUBLIC KEY-----""".encode()

    logger.debug("Keycloak public key for realm %s: [%s]", realmId, keycloak_public_key)
    return keycloak_public_key


# Looks as `iss` header field of token - if this is a Keycloak-issued token,
# `iss` will have a value like 'https://<KEYCLOAK_SERVER>/auth/realms/<REALMID>
# so we can parse the URL parts to obtain the realm this token was issued from.
# Once we know that, we know where to get a pubkey to validate it.
#
# `urlparse` should be safe to use as a parser, and if the result is
# an invalid realm name, no validation key will be fetched, which simply will result
# in an access denied
def try_extract_realm(unverified_jwt):
    issuer_url = unverified_jwt["iss"]
    # Split the issuer URL once, from the right, on /,
    # then get the last element of the result - this will be
    # the realm name for a keycloak-issued token.
    return urlparse(issuer_url).path.rsplit("/", 1)[-1]


# If key_master already has a key for that realm, use that.
# Otherwise, use the realm identifier to fetch the realm PK from Keycloak.
#
# If we get nothing in either case, return an empty/falsy result
#
# For now, we're relying on key_master to handle caching, and just using
# a cached pubkey if one exists - this (and key_master itself) could stand to be
# more robust in terms of key validity checks, rotations, refreshes, etc.
def load_realm_key(realmId, key_master):
    KEYCLOAK_HOST = _get_keycloak_host()
    realmKey = {}
    try:
        realmKey = key_master.get_key(f"KEYCLOAK-PUBLIC-{realmId}")
    except KeyNotFoundError:
        try:
            realmKey = get_keycloak_public_key(realmId)
        except Exception:
            logger.warning(
                f"Unable to fetch public key for realm: {realmId} from Keycloak endpoint: {KEYCLOAK_HOST}"
            )
        else:
            key_master.set_key_pem(f"KEYCLOAK-PUBLIC-{realmId}", "PUBLIC", realmKey)

    return realmKey


# Given a JWT and the keymaster, attempt to obtain the right pubkey from
# Keycloak for the realm this JWT was issued from.
# If anything goes wrong, return an empty/falsy value
def fetch_realm_key_by_jwt(idpJWT, key_master):
    # We must extract `iss` without validating the JWT,
    # because we need `iss` to know which specific realm endpoint to hit
    # to get the public key we would verify it with
    unverified_jwt = unsafe_decode_jwt(idpJWT)

    realmId = ""
    # If we can't parse or extract the realm ID from the issuer JWT
    # for any reason, swallow the error and return an empty value for the key
    try:
        realmId = try_extract_realm(unverified_jwt)
    except:
        logger.warn(
            "Unable to extract realm identifier from JWT, assuming invalid token"
        )
        return {}

    return load_realm_key(realmId, key_master)
