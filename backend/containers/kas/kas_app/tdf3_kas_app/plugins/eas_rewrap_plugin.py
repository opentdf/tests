"""OSS rewrap plugin."""

import logging

from .eas_connector import EASConnector
from tdf3_kas_core.abstractions import AbstractHealthzPlugin, AbstractRewrapPlugin
from tdf3_kas_core.errors import BadRequestError

logger = logging.getLogger(__name__)


class EASRewrapPlugin(AbstractHealthzPlugin, AbstractRewrapPlugin):
    """Fetch attributes from EAS"""

    def __init__(self, eas_host):
        """Initialize the plugin.

        No need to override __init__() from AbstractUpsertPlugin. The super
        __init__ will run by default since none is defined here.
        """
        self.connector = EASConnector(eas_host)

    def fetch_attributes(self, namespaces):
        """fetch attributes for KAS to make rewrap decision."""

        attribute_config = self.connector.fetch_attributes(namespaces)
        return attribute_config

    def healthz(self, *, probe):
        """Override this method."""
        if "readiness" == probe:
            self.connector.ping()
        elif not probe or probe == "liveness":
            pass
        else:
            raise BadRequestError(f"Unrecognized healthz probe name {probe}")
