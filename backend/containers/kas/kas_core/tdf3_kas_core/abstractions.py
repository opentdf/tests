"""
# Abstract Plugins

The KAS is stateless, but it may be enhanced by adding plugin functions that
enact stateful behaviors.

There are two kinds.  Rewrap plugins are used to get policy updates from
remote sources.  Upsert plugins are used to both create and update policies
on remote sources.

### Use

Plugins are functions that accept two objects, req and res, and return a
tuple containing the same two objects.

The req object is interpreted as request object from a rewrap call. It has
four properties:

1.  The Policy object. This object may be modified.
2.  The Entity object. All modifications are ignored.
3.  The KeyAccess object. All modifications are ignored.
4.  An optional context object. All modifications are ignored.

The res object is interpreted as a response object. It has two properties:

1.  An optional rewrapped key. If this exists the KAS assumes the plugin
    is configured to make the rewrap decision and passes the wrapped key back
    to the client. If the wrapped key field is missing or contains none then
    the KAS assumes that it should operate normally.
2.  An optional metadata property. This is an object that may contain
    anything the plugin believes the client should know.

"""

import logging

logger = logging.getLogger(__name__)


class AbstractPlugin(object):
    """The abstract plugin class is the base for all plugins."""

    pass


class AbstractHealthzPlugin(AbstractPlugin):
    """Add to your health readiness checks."""

    def healthz(self, *, probe):
        """Override this method."""
        logger.error("AbstractHealthzPlugin method was called with (probe=[%s])", probe)
        logger.setLevel(logging.DEBUG)  # dynamically escalate level


class AbstractRewrapPlugin(AbstractPlugin):
    """The abstract rewrap plugin is the base class for rewrap plugins."""

    def update(self, req, res):
        """Override this method."""
        logger.error("AbstractRewrapPlugin update method was called.")
        logger.setLevel(logging.DEBUG)  # dynamically escalate level
        return (req, res)

    def fetch_attributes(self, namespaces):
        """Override this method."""
        logger.warning("AbstractUpsertPlugin fetch_attributes method was called.")
        logger.debug("namespaces = %s", namespaces)
        return {}


class AbstractUpsertPlugin(AbstractPlugin):
    """The abstract upsert plugin is the base class for upsert plugins."""

    def upsert(self, **kwargs):
        """Override this method."""
        logger.warning("AbstractUpsertPlugin upsert method was called.")
        logger.debug("kwargs = %s", kwargs)
        return ""
