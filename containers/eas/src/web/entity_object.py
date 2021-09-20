"""Entity Object Interface."""
import os

from flask import current_app, request

from .status import statusify
from ..eas_config import EASConfig
from ..errors import AuthorizationError
from ..server_timing import Timing
from ..services import ServiceSingleton
from ..util.keys.get_keys_from_disk import get_public_key_for_algorithm

eas_config = EASConfig.get_instance()
EAS_ENTITY_ID_HEADER = os.environ.get("EAS_ENTITY_ID_HEADER")


@statusify
@Timing.timer
def generate(body):
    """Generate an entity object for the specified user."""
    Timing.start("entity_object")
    entity_object_service = ServiceSingleton.get_instance().entity_object_service
    logger = current_app.logger
    logger.debug("Entity Object = %s", body)
    logger.debug("request.headers.environ = %s", request.headers.environ)
    logger.debug("EAS_ENTITY_ID_HEADER = %s", EAS_ENTITY_ID_HEADER)
    public_key = body["publicKey"]
    signer_public_key = body.get("signerPublicKey", None)
    kas_certificate = get_public_key_for_algorithm(body.get("algorithm", None))

    # Use Entity Id from header - Trusted authentication service populated.
    if not EAS_ENTITY_ID_HEADER:
        logger.warning(
            "Unauthenticated mode: userId [%s]",
            body["userId"],
        )
        return entity_object_service.generate(
            publicKey=public_key,
            signerPublicKey=signer_public_key,
            userId=body["userId"],
            kas_certificate=kas_certificate,
        )
    if EAS_ENTITY_ID_HEADER not in request.headers:
        raise AuthorizationError(f"Missing auth header [{EAS_ENTITY_ID_HEADER}]")

    dn = request.headers[EAS_ENTITY_ID_HEADER]
    logger.debug("DN=[%s], from header=[%s]", dn, EAS_ENTITY_ID_HEADER)
    if not dn:
        raise AuthorizationError("dn required")

    # We used to support the userId field as a method for authentication, possibly
    # in concert with an HMAC or application ID. However, that is vulnerable to insider
    # threat.
    if "userId" in body:
        if body["userId"] != dn:
            raise AuthorizationError(f"userId[{body['userId']}] != [{dn}]")
        logger.info("Deprecated field: userId [%s]", body["userId"])
    response = entity_object_service.generate(
        publicKey=public_key,
        signerPublicKey=signer_public_key,
        userId=dn,
        kas_certificate=kas_certificate,
    )
    Timing.stop("entity_object")
    return response
