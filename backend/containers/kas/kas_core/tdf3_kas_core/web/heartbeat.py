"""REST Web handler for heartbeat ping."""

from tdf3_kas_core.kas import Kas
import logging
from .run_service_with_exceptions import run_service_with_exceptions

logger = logging.getLogger(__name__)


@run_service_with_exceptions
def ping():
    """Handle the '/' route.

    This endpoint is for OPS so they have something to ping on to verify
    that the server hasn't died.
    """
    logger.debug("web.heartbeat.get()")
    return (Kas.get_instance().get_session_ping())()


@run_service_with_exceptions(success=204)
def healthz(*, probe: str = "liveness"):
    """Check to make sure the EAS service is available."""
    logger.debug(f"healthz(probe=${probe})")
    (Kas.get_instance().get_session_healthz())(probe=probe)
