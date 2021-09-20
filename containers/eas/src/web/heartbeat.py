"""Returns the version info when pinged."""

from flask import current_app
from .status import statusify
from ..util import VERSION
from ..db_connectors import SQLiteConnector
from ..errors import Error


@statusify
def ping():
    """Return version info when pinged."""
    current_app.logger.debug("Heartbeat Ping requested, version = %s", VERSION)
    return {"version": f"{VERSION}"}


@statusify(success=204)
def healthz(*, probe: str):
    """Check to make sure the database is available."""
    current_app.logger.warning(f"Health Status requested [${probe}]")
    if probe == "readiness":
        SQLiteConnector.get_instance().check_schema()
