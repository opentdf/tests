"""This is where the services are found.

The services layer serves the web layer with internal interfaces to the
business logic.  None of the code downstream of these function calls should
have any awareness of the external or web technology used.  This makes
providing another web interface easy so the same KAS code can be used many
different environments.

Each service should either return the result of the service call or raise
an error. The web layer handles any communication of these errors that might
be required by external system elements.

The ideal service is like a table of contents or a flowchart that a maintainer
can use to quickly jump to the relevant modules and packages. It should be
an easy-to-follow living document.

In general, services should be a very compact functions - no more than a
page - that lay out the steps with high level abstractions.  The calls to
model methods, utility functions, data connectors, and other elements should
tell an easy-to-read story. If a service grows to more than a page it is ripe
for refactoring. Following the "one level of abstraction per module" principal,
only the very simplest of services will contain low-level computations.
"""

import logging
import jwt
import base64
import os
import hashlib
import json

import tdf3_kas_core.keycloak as keycloak

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from pkg_resources import packaging

from tdf3_kas_core.errors import AdjudicatorError
from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import BadRequestError
from tdf3_kas_core.errors import KeyAccessError
from tdf3_kas_core.errors import KeyNotFoundError
from tdf3_kas_core.errors import NanoTDFParseError
from tdf3_kas_core.errors import PolicyError
from tdf3_kas_core.errors import PolicyBindingError
from tdf3_kas_core.errors import UnauthorizedError
from tdf3_kas_core.errors import RouteNotFoundError

from tdf3_kas_core.models import Adjudicator
from tdf3_kas_core.models import AttributePolicyCache
from tdf3_kas_core.models import Entity
from tdf3_kas_core.models import KeyAccess
from tdf3_kas_core.models import Policy
from tdf3_kas_core.models import WrappedKey
from tdf3_kas_core.models import Claims

from tdf3_kas_core.models.nanotdf import Policy as PolicyInfo
from tdf3_kas_core.models.nanotdf import ResourceLocator
from tdf3_kas_core.models.nanotdf import ECCMode
from tdf3_kas_core.models.nanotdf import SymmetricAndPayloadConfig

from tdf3_kas_core.server_timing import Timing

from tdf3_kas_core.authorized import authorized
from tdf3_kas_core.authorized import authorized_v2
from tdf3_kas_core.authorized import looks_like_jwt

logger = logging.getLogger(__name__)


flags = {
    # TODO(PLAT-1212) Remove (set to False)
    "default_to_small_iv": os.environ.get("LEGACY_NANOTDF_IV") == "1",
    "idp": os.environ.get("USE_KEYCLOAK") == "1",
}


def kas_public_key(key_master, algorithm):
    """Serve the current KAS public key.

    OIDC flow removes EOs and EAS calls, and so uses this to dynamically
    fetch the KAS public key, if the client not explicitly set a KAS public
    key in clientside config, and if an alternate key endpoint is not defined
    in Virtru custom claims.
    """
    logger.debug("===== KAS PUBLIC KEY SERVICE START ====")

    public_key = None
    if algorithm == "rsa:2048":
        public_key = key_master.get_export_string("KAS-PUBLIC")
    elif algorithm == "ec:secp256r1":
        public_key = key_master.get_export_string("KAS-EC-SECP256R1-PUBLIC")

    if public_key is None:
        msg = "Could not produce a public key"
        logger.error(msg)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise KeyNotFoundError(msg)

    logger.debug("===== KAS PUBLIC KEY SERVICE FINISH ====")
    return public_key


def ping(version):
    """Service health check."""
    logger.debug("heartbeat ping with VERSION = %s", version)
    return {"version": f"{version}"}


def rewrap(data, context, plugin_runner, key_master):
    """Rewrap a key split.

    The rewrap service is the guts of the whole KAS.  It takes a raw data
    object that conforms to the JSON data schema for the /reqrap API call,
    processes it, and returns an object ready to be converted to the web
    response.  Context contains any other information.
    """
    logger.debug("===== REWRAP SERVICE START ====")
    if "signedRequestToken" in data:
        try:
            decoded = jwt.decode(
                data["signedRequestToken"],
                options={"verify_signature": False},
                algorithms=["RS256", "ES256", "ES384", "ES512"],
            )

            requestBody = decoded["requestBody"]
            json_string = requestBody.replace("'", '"')
            dataJson = json.loads(json_string)
        except ValueError as e:
            raise BadRequestError(f"Error in jwt or content [{e}]") from e

        signer_public_key = serialization.load_pem_public_key(
            str.encode(dataJson["entity"]["signerPublicKey"]), backend=default_backend()
        )
        try:
            jwt.decode(
                data["signedRequestToken"],
                signer_public_key,
                algorithms=["RS256", "ES256", "ES384", "ES512"],
            )
        except Exception as e:
            raise UnauthorizedError("Not authorized") from e

        try:
            entity = Entity.load_from_raw_data(
                dataJson["entity"], key_master.get_key("AA-PUBLIC")
            )
        except ValueError as e:
            raise BadRequestError(f"Error in EO [{e}]") from e

        return _nano_tdf_rewrap(dataJson, context, plugin_runner, key_master, entity)
    else:
        # Upack and validate the entity object.
        if "entity" not in data:
            raise UnauthorizedError("No Entity object")

        try:
            entity = Entity.load_from_raw_data(
                data["entity"], key_master.get_key("AA-PUBLIC")
            )
        except ValueError as e:
            raise BadRequestError(f"Error in EO [{e}]") from e

        # Check the auth token.
        if "authToken" not in data:
            raise AuthorizationError("Entity not authorized")

        try:
            jwt.decode(
                data["authToken"],
                entity.public_key,
                algorithms=["RS256", "ES256", "ES384", "ES512"],
            )
        except Exception as e:
            raise AuthorizationError("Not authorized") from e

        if "keyAccess" not in data:
            logger.error("Key Access missing from %s", data)
            logger.setLevel(logging.DEBUG)  # dynamically escalate level
            raise KeyAccessError("No key access object")

        algorithm = data.get("algorithm", None)
        if algorithm is None:
            logger.warning("'algorithm' is missing and defaulting to TDF3 rewrap.")
            algorithm = "rsa:2048"

        if algorithm == "ec:secp256r1":
            return _nano_tdf_rewrap(data, context, plugin_runner, key_master, entity)
        else:
            return _tdf3_rewrap(data, context, plugin_runner, key_master, entity)


def _get_bearer_token_from_header(context):
    # Get bearer token
    try:
        authToken = context.data["Authorization"]
        bearer, _, idpJWT = authToken.partition(" ")
    except KeyError as e:
        raise UnauthorizedError("Missing auth header") from e
    else:
        if bearer != "Bearer" or not looks_like_jwt(idpJWT):
            raise UnauthorizedError("Invalid auth header")

    logger.debug("Obtained auth token from header")

    return idpJWT


def _get_tdf_claims(context, key_master):
    idpJWT = _get_bearer_token_from_header(context)

    realmKey = keycloak.fetch_realm_key_by_jwt(idpJWT, key_master)
    decoded_payload = authorized_v2(realmKey, idpJWT)

    claims = Claims.load_from_raw_data(decoded_payload)

    return claims


def rewrap_v2(data, context, plugin_runner, key_master):
    """Rewrap a key split.

    The rewrap service is the guts of the whole KAS.  It takes a raw data
    object that conforms to the JSON data schema for the /v2/rewrap API call,
    processes it, and returns an object ready to be converted to the web
    response.  Context contains any other information.
    """
    logger.debug("===== REWRAPV2 SERVICE START ====")

    claims = _get_tdf_claims(context, key_master)
    signer_public_key = claims.client_public_signing_key

    if "signedRequestToken" not in data:
        raise AuthorizationError("Request not authorized")

    try:
        decoded = jwt.decode(
            data["signedRequestToken"],
            signer_public_key,
            algorithms=["RS256", "ES256", "ES384", "ES512"],
        )

        requestBody = decoded["requestBody"]
        json_string = requestBody.replace("'", '"')
        dataJson = json.loads(json_string)
    except ValueError as e:
        raise BadRequestError(f"Error in jwt or content [{e}]") from e
    except Exception:
        raise UnauthorizedError("Not authorized")

    algorithm = dataJson.get("algorithm", None)
    if algorithm is None:
        logger.warning(
            "'algorithm' is missing; defaulting to TDF3 rewrap standard, RSA-2048."
        )
        algorithm = "rsa:2048"

    client_public_key = serialization.load_pem_public_key(
        str.encode(dataJson["clientPublicKey"]), backend=default_backend()
    )

    entity = Entity(claims.user_id, client_public_key, claims.attributes)

    if algorithm == "ec:secp256r1":
        return _nano_tdf_rewrap(dataJson, context, plugin_runner, key_master, entity)
    else:

        if "keyAccess" not in dataJson:
            logger.error("Key Access missing from %s", dataJson)
            raise KeyAccessError("No key access object")

        return _tdf3_rewrap(dataJson, context, plugin_runner, key_master, entity)


def _tdf3_rewrap(data, context, plugin_runner, key_master, entity):
    """
    Handle rewrap request for tdf3 type.
    """

    # Unpack the policy.
    if "policy" not in data:
        raise PolicyError("No policy")

    try:
        canonical_policy = data["policy"]
        original_policy = Policy.construct_from_raw_canonical(canonical_policy)

        kas_private = key_master.get_key("KAS-PRIVATE")
        key_access = KeyAccess.from_raw(
            data["keyAccess"],
            private_key=kas_private,
            canonical_policy=canonical_policy,
            use="rewrap",
        )
    except ValueError as e:
        raise BadRequestError(f"Error in Policy or Key Binding [{e}]") from e

    #
    # Run the plugins
    #

    # Fetch attributes from EAS and create attribute policy cache.
    attribute_policy_cache = AttributePolicyCache()
    data_attributes_namespaces = list(
        original_policy.data_attributes.cluster_namespaces
    )
    if data_attributes_namespaces:
        config = plugin_runner.fetch_attributes(data_attributes_namespaces)
        attribute_policy_cache.load_config(config)

    # Create adjudicator from the attributes from EAS.
    adjudicator = Adjudicator(attribute_policy_cache)

    (policy, res) = plugin_runner.update(original_policy, entity, key_access, context)

    # Execute a premature bailout if the plugins provide a rewrapped key.
    if "entityWrappedKey" in res:
        logger.debug(
            "REMOTE RETURNED AN ENTITY WRAPPED KEY [res = %s] REWRAP SERVICE FINISH",
            res,
        )
        # Assume this is ok as is; DO NOT CHECK CREDENTIALS (?)
        return res

    elif "kasWrappedKey" in res:
        # replace the wrapped key object in key_access with the new key
        logger.debug(
            "REMOTE RETURNED A KAS WRAPPED KEY; B64 KAS Wrapped key=[%s]",
            res["kasWrappedKey"],
        )
        key_access.wrapped_key = res["kasWrappedKey"]

    else:
        logger.debug("KEY TO REWRAP CAME FROM REQUEST")
        # A purely KAS operation
        pass

    # Check to see if the policy will grant the entity access.
    # Raises an informative error if access is denied.
    allowed = adjudicator.can_access(policy, entity)

    if allowed is True:
        logger.debug("========= Rewrap allowed = %s", allowed)
        # Re-wrap the kas-wrapped key with the entity's public key.
        if key_access.wrapped_key is not None:
            wrapped_key = WrappedKey.from_raw(key_access.wrapped_key, kas_private)
            res["entityWrappedKey"] = wrapped_key.rewrap_key(entity.public_key)
            logger.debug("REWRAP SERVICE FINISH")
            return res
        else:
            logger.error("Wrapped key missing from %s", key_access)
            raise KeyAccessError("No wrapped key in key access model")

    else:
        # should never get to here. Bug in adjudicator.
        m = f"Adjudicator returned {allowed} without raising an error"
        logger.error(m)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise AdjudicatorError(m)


def _nano_tdf_rewrap(data, context, plugin_runner, key_master, entity):
    """
    Handle rewrap request for tdf3 type.
    """
    Timing.start("_nano_tdf_rewrap")
    try:
        key_access = data["keyAccess"]

        # extract the nano tdf header in binary format.
        header = base64.b64decode(key_access["header"])
    except ValueError as e:
        raise BadRequestError(f"Error in KAO [{e}]") from e

    client_version = packaging.version.parse(
        context.get("virtru-ntdf-version") or "0.0.0"
    )
    legacy_wrapping = flags[
        "default_to_small_iv"
    ] and client_version < packaging.version.parse("0.0.1")
    logger.info(
        f"virtru-ntdf-version: [{client_version}]; legacy_wrapping: {legacy_wrapping}"
    )

    try:
        # extract the ecc mode from header.
        (_, header) = ResourceLocator.parse(header[3:])
        (ecc_mode, header) = ECCMode.parse(header)

        # extract payload config from header.
        (payload_config, header) = SymmetricAndPayloadConfig.parse(header)

        # extract policy from header.
        (policy_info, header) = PolicyInfo.parse(ecc_mode, payload_config, header)

        # extract ephemeral key from the header.
        ephemeral_key = header[0 : ecc_mode.curve.public_key_byte_length]

    except Exception as e:
        logger.error(e)
        raise NanoTDFParseError("Fail to parse the nanoTDF header.")

    # NOTE: The KAS and EAS only support secp256r1 curve for now.
    # generate a symmetric key.
    kas_private = key_master.get_key("KAS-EC-SECP256R1-PRIVATE")
    private_key_bytes = kas_private.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    decryptor = ecc_mode.curve.create_decryptor(ephemeral_key, private_key_bytes)

    # extract the cipher from payload config.
    zero_iv = b"\0" * (3 if legacy_wrapping else 12)
    assert isinstance(zero_iv, bytes)
    assert isinstance(decryptor.symmetric_key, bytes)
    symmetric_cipher = payload_config.symmetric_cipher(decryptor.symmetric_key, zero_iv)
    policy_data = policy_info.body.data
    policy_data_len = len(policy_data) - payload_config.symmetric_tag_length

    auth_tag = policy_data[-payload_config.symmetric_tag_length :]
    logger.debug(
        f"virtru-ntdf-version: [{client_version}]; legacy_wrapping: {legacy_wrapping}; tag_length: {payload_config.symmetric_tag_length}, context: {context.data}"
    )

    policy_data_as_byte = base64.b64encode(
        symmetric_cipher.decrypt(policy_data[0:policy_data_len], auth_tag)
    )

    if ecc_mode.use_ecdsa_binding:
        try:
            # verify the binding
            verifier = ecc_mode.curve.create_verifier(ephemeral_key)
            verifier.verify(policy_info.binding.data, policy_data)
        except Exception as e:
            logger.error(e)
            raise PolicyBindingError("ECDSA policy binding" " verification failed.")
    else:
        hash_alg = hashlib.sha256()
        hash_alg.update(policy_data)
        digest = hash_alg.digest()
        if digest[-len(policy_info.binding.data) :] != policy_info.binding.data:
            raise PolicyBindingError("Gmac Policy binding" " verification failed.")

    original_policy = Policy.construct_from_raw_canonical(
        policy_data_as_byte.decode("utf-8")
    )

    #
    # Run the plugins
    #

    # Fetch attributes from EAS and create attribute policy cache.
    attribute_policy_cache = AttributePolicyCache()
    data_attributes_namespaces = list(
        original_policy.data_attributes.cluster_namespaces
    )
    if data_attributes_namespaces:
        config = plugin_runner.fetch_attributes(data_attributes_namespaces)
        attribute_policy_cache.load_config(config)

    # Create adjudicator from the attributes from EAS.
    adjudicator = Adjudicator(attribute_policy_cache)

    (policy, res) = plugin_runner.update(original_policy, entity, key_access, context)

    # Check to see if the policy will grant the entity access.
    # Raises an informative error if access is denied.
    allowed = adjudicator.can_access(policy, entity)
    if allowed is False:
        m = "Adjudicator returned {} without raising an error".format(allowed)
        logger.error(m)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        raise AdjudicatorError(m)

    # Generate ephemeral rewrap key-pair
    public_key_bytes = entity.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
    )
    encryptor = ecc_mode.curve.create_encryptor(public_key_bytes)

    if legacy_wrapping:
        logger.warning(
            "Failing back to short i.v. for rewrap, client_version=[%s]",
            client_version,
        )
        iv = os.urandom(3)
    else:
        iv = os.urandom(12)
    symmetric_kak = encryptor.symmetric_key
    symmetric_cipher = payload_config.symmetric_cipher(symmetric_kak, iv)
    cipher_text, tag = symmetric_cipher.encrypt(decryptor.symmetric_key)
    encrypted_symmetric_kak = iv + cipher_text + tag

    ephemeral_rewrap_public_key = encryptor.public_key_as_pem().decode("utf-8")
    encrypted_symmetric_kak_base64 = base64.b64encode(encrypted_symmetric_kak).decode(
        "utf-8"
    )

    res = {
        "entityWrappedKey": encrypted_symmetric_kak_base64,
        "sessionPublicKey": ephemeral_rewrap_public_key,
    }
    Timing.stop("_nano_tdf_rewrap")
    return res


def upsert(data, context, plugin_runner, key_master):
    """Upsert a policy/key.

    The upsert service is a proxy to the back-end services that persist
    policies and keys.
    """
    logger.debug("UPSERT SERVICE START")

    # Upack and validate the entity object.
    if "entity" not in data:
        raise AuthorizationError("No Entity object")

    entity = Entity.load_from_raw_data(data["entity"], key_master.get_key("AA-PUBLIC"))

    # Check the auth token.
    if "authToken" not in data:
        raise AuthorizationError("Entity not authorized")

    authorized(entity.public_key, data["authToken"])

    # Unpack the policy.
    if "policy" not in data:
        raise PolicyError("No policy")

    try:
        canonical_policy = data["policy"]
        original_policy = Policy.construct_from_raw_canonical(canonical_policy)
    except ValueError as e:
        raise BadRequestError("Error in Policy definition") from e

    # Get the key access object. Wrapped key may be in this object.
    if "keyAccess" not in data:
        raise KeyAccessError("No key access object")

    kas_private = key_master.get_key("KAS-PRIVATE")
    try:
        key_access = KeyAccess.from_raw(
            data["keyAccess"],
            private_key=kas_private,
            canonical_policy=canonical_policy,
            use="upsert",
        )
    except ValueError as e:
        raise BadRequestError("Error in KAO") from e

    # Run the plugins
    messages = plugin_runner.upsert(original_policy, entity, key_access, context)

    if messages:
        logger.info("Upsert Status Messages = %s", messages)
    logger.debug("UPSERT SERVICE FINISH")

    return messages  # XXX: Don't return internals!!


def upsert_v2(data, context, plugin_runner, key_master):
    """Upsert a policy/key.

    The upsert service is a proxy to the back-end services that persist
    policies and keys.
    """
    logger.debug("===== UPSERTV2 SERVICE START ====")

    claims = _get_tdf_claims(context, key_master)
    signer_public_key = claims.client_public_signing_key

    if "signedRequestToken" not in data:
        raise AuthorizationError("Request not authorized")

    try:
        decoded = jwt.decode(
            data["signedRequestToken"],
            signer_public_key,
            algorithms=["RS256"],
        )

        requestBody = decoded["requestBody"]
        json_string = requestBody.replace("'", '"')
        dataJson = json.loads(json_string)
    except ValueError as e:
        raise BadRequestError(f"Error in jwt or content [{e}]") from e
    except Exception:
        raise UnauthorizedError("Not authorized")

    algorithm = dataJson.get("algorithm", None)
    if algorithm is None:
        logger.warning("'algorithm' is missing and defaulting to TDF3 rewrap.")
        algorithm = "rsa:2048"

    client_public_key = serialization.load_pem_public_key(
        str.encode(dataJson["clientPublicKey"]), backend=default_backend()
    )

    entity = Entity(claims.user_id, client_public_key, claims.attributes)

    # Unpack the policy.
    if "policy" not in dataJson:
        raise PolicyError("No policy")

    canonical_policy = dataJson["policy"]
    original_policy = Policy.construct_from_raw_canonical(canonical_policy)

    # Get the key access object. Wrapped key may be in this object.
    if "keyAccess" not in dataJson:
        raise KeyAccessError("No key access object")

    kas_private = key_master.get_key("KAS-PRIVATE")
    key_access = KeyAccess.from_raw(
        dataJson["keyAccess"],
        private_key=kas_private,
        canonical_policy=canonical_policy,
        use="upsert",
    )

    # Run the plugins
    messages = plugin_runner.upsert(original_policy, entity, key_access, context)

    logger.debug("UPSERTV2 SERVICE FINISH: Upsert Status Messages = [%s]", messages)

    return messages
