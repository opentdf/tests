"""Revocation blocklist/allowlist filter plugin.

This plugin allows creation of a blocklist or allowlist for EOs.
"""

import logging

from tdf3_kas_core.abstractions import AbstractRewrapPlugin, AbstractUpsertPlugin
from tdf3_kas_core.errors import AuthorizationError

logger = logging.getLogger(__name__)


class RevocationPlugin(AbstractRewrapPlugin, AbstractUpsertPlugin):
    """ """

    def __init__(self, *, allows=None, blocks=None):
        """Initialize the plugin."""
        self.allows = allows
        self.blocks = blocks

    def update(self, req, res):
        """Validate the entity in the request is allowed."""
        self.match_or_raise(entity=req["entity"])
        return (req, res)

    def upsert(self, *, entity):
        """validate the entity is unrevoked, and allowed."""
        self.match_or_raise(entity=entity)
        return ""

    def match_or_raise(self, *, entity):
        def match(v):
            if v == "*":
                return True
            return v == entity.user_id

        if self.allows:
            if not any(match(v) for v in self.allows):
                raise AuthorizationError(f"Not allowed user [{entity.user_id}]")
        if self.blocks:
            if any(match(v) for v in self.blocks):
                raise AuthorizationError(f"Blocked user [{entity.user_id}]")
