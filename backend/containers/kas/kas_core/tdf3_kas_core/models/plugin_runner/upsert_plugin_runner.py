"""Plugin Runner."""
import logging

from tdf3_kas_core.abstractions import AbstractUpsertPlugin

from .abstract_plugin_runner import AbstractPluginRunner

logger = logging.getLogger(__name__)


def upsert_check(plugin):
    """Test to see if the plugin is an upsert type."""
    return isinstance(plugin, AbstractUpsertPlugin)


class UpsertPluginRunner(AbstractPluginRunner):
    """Manage the upsert plugins.

    These plugins convey information to the back-end services.  This info is
    typically a set of instructions for creating and updating policies and/or
    remote keys. The plugins return status messages.  An empty status message
    indicates that everything went OK.
    """

    def __init__(self, plugins=None):
        """Construct with an array of upsert plugin instances."""
        logger.debug("=== Constructing an UpsertPluginRunner")
        msg = "Plugin is not a member of AbstractUpsertPlugin"
        super(UpsertPluginRunner, self).__init__(plugins, upsert_check, msg)
        logger.debug("=== UpsertPluginRunner constructed")

    def upsert(self, policy, entity, key_access, context):
        """Call the plugins in order."""
        logger.debug("--- Upsert method starting")

        messages = []  # list of status strings. Empty string == OK
        for plugin in self._plugins:
            logger.debug("Upserting with Plugin %s", plugin)
            message = plugin.upsert(
                policy=policy, entity=entity, key_access=key_access, context=context
            )
            logger.debug("Plugin returned %s", message)
            messages.append(message)

        logger.debug("Messages %s", messages)
        logger.debug("--- Upsert method complete")
        return messages  # XXX: Don't leak internals!!
