"""Utility functions to get schema."""

import json
import logging

import importlib_resources


logger = logging.getLogger(__name__)


def get_schema(name):
    """Get a schema from disk."""
    schemata = importlib_resources.files(__package__) / "schema"
    raw = (schemata / f"{name}.json").read_text()
    return json.loads(raw)
