"""REST Web handler for rewrap."""
import connexion
import logging

from tdf3_kas_core.kas import Kas
from tdf3_kas_core.schema import get_schema
from tdf3_kas_core.server_timing import Timing

from .create_context import create_context
from .run_service_with_exceptions import run_service_with_exceptions

TDF3_REWRAP_SCHEMA = get_schema("tdf3_rewrap_schema")
logger = logging.getLogger(__name__)


def rewrap_helper(body, session_rewrap):
    """Handle the '/rewrap' route.

    This endpoint performs the primary service of the KAS; to re-wrap
    data keys as needed to provide access for enties with a TDF that they
    would like to open.
    """
    Timing.start("rewrap")
    logger.debug("+=+=+=+=+=+ Rewrap service runner starting")

    # Data validation performed by Connexion library against openapi.yaml

    # create the context object. Connexion provides Flask request headers:
    context = create_context(connexion.request.headers)

    logger.debug("+=+=+=+=+=+ Rewrap Request is Valid")

    # process the request. Throws a variety of errors.
    res = session_rewrap(body, context)
    # package up the response and send it.

    logger.debug("+=+=+=+=+=+ Rewrap request complete")
    Timing.stop("rewrap")
    return res


@run_service_with_exceptions
def rewrap(body):
    return rewrap_helper(body, Kas.get_instance().get_session_rewrap())


@run_service_with_exceptions
def rewrap_v2(body):
    return rewrap_helper(body, Kas.get_instance().get_session_rewrap_v2())
