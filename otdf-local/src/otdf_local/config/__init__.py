"""Configuration module for otdf-local."""

from otdf_local.config.ports import Ports
from otdf_local.config.settings import Settings, get_settings

__all__ = ["Ports", "Settings", "get_settings"]
