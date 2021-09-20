"""Plugin Runner."""
import logging

import logging

from tdf3_kas_core.errors import PluginIsBadError

logger = logging.getLogger(__name__)


class AbstractPluginRunner(object):
    """Base class for plugin runners.

    Plugins are called in the order the arrive during construction.
    """

    def __init__(self, plugins, plugin_test, error_msg):
        """Construct with an array of plugin instances."""
        logger.debug(" --- Abstract plugin (super) constructor starting")
        self._plugins = []
        logger.info("%s Plugins = %s", self.__class__.__name__, plugins)
        if plugins is None:
            logger.info("No plugins provided")
            return
        for plugin in plugins:
            if plugin_test(plugin):
                logger.debug("Plugin %s is valid, appending", plugin)
                self._plugins.append(plugin)
            else:
                logger.error("Plugin %s is invalid", plugin)
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise PluginIsBadError(error_msg)
        logger.debug(" -- Abstract plugin (super) constructor complete")
