"""Plugin Runner."""
import logging

import logging

from tdf3_kas_core.abstractions import AbstractHealthzPlugin

from .abstract_plugin_runner import AbstractPluginRunner

logger = logging.getLogger(__name__)


def healthz_check(plugin):
    """Test to see if the plugin is a healthz type."""
    return isinstance(plugin, AbstractHealthzPlugin)


class HealthzPluginRunner(AbstractPluginRunner):
    """Manage the healthz plugins.

    If a healthz plugin determines that the server state is unhealthy, it must
    raise an exception. All other healthz plugins will not be evaluated
    """

    def __init__(self, plugins=None):
        """Construct with an array of rewrap plugin instances."""
        logger.debug("=== Constructing a HealthzPluginRunner")
        msg = "Plugin is not a member of AbstractRewrapPlugin"
        super(HealthzPluginRunner, self).__init__(plugins, healthz_check, msg)
        logger.debug("=== HealthzPluginRunner constructed")

    def healthz(self, *, probe):
        """Call the plugins in order."""
        logger.debug("--- Healthz(probe=[%s]) function called", probe)
        for plugin in self._plugins:
            # run the plugin
            logger.debug("--- Healthz with Plugin %s", plugin)
            plugin.healthz(probe=probe)
        logger.debug("--- healthz complete")
