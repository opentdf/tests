"""Main export point for the src directory."""

import logging
import sys

from pythonjsonlogger import jsonlogger

# Primary export
from .eas_app import eas_app  # noqa: F401
from .eas_config import EASConfig

eas_config = EASConfig.get_instance()

logging.getLogger(__name__).debug("Logging is set up on %s", __name__)
