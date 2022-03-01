"""REST Web handler for Kas public key."""

from tdf3_kas_core.kas import Kas
import logging
from .run_service_with_exceptions import run_service_with_exceptions

logger = logging.getLogger(__name__)


@run_service_with_exceptions
def get(algorithm: str = "rsa:2048"):
    """Handle the '/kas_public_key' route.

    This endpoint provides a public key for the private key that the
    kas has internally. The public key is used to wrap object keys in
    the TDF3 or NanoTDF files.

    OIDC flow removes EOs and EAS calls, and so uses this to dynamically
    fetch the KAS public key, if the client not explicitly set a KAS public
    key in clientside config, and if an alternate key endpoint is not defined
    in Virtru custom claims.
    """
    logger.debug(f"web.kas_public_key.get(algorithm=${algorithm})")
    return (Kas.get_instance().get_session_public_key())(algorithm)
