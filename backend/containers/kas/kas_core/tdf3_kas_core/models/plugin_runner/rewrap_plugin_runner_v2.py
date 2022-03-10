"""Plugin Runner."""
import logging

from tdf3_kas_core.errors import PluginFailedError
from tdf3_kas_core.errors import AuthorizationError

from tdf3_kas_core.models import Policy

from tdf3_kas_core.abstractions import AbstractRewrapPlugin

from .abstract_plugin_runner import AbstractPluginRunner

logger = logging.getLogger(__name__)


def rewrap_check(plugin):
    """Test to see if the plugin is a rewrap type."""
    return isinstance(plugin, AbstractRewrapPlugin)


class RewrapPluginRunnerV2(AbstractPluginRunner):
    """Manage the rewrap plugins.

    If a rewrap plugin determines that the rewrap should not proceed it
    should return either a None or an error message string to indicate
    the denial.  Any other non-Policy return is considered a failure of
    the plugin.
    """

    def __init__(self, plugins=None):
        """Construct with an array of rewrap plugin instances."""
        logger.debug("=== Constructing a RewrapPluginRunnerV2")
        msg = "Plugin is not a member of AbstractRewrapPlugin"
        super(RewrapPluginRunnerV2, self).__init__(plugins, rewrap_check, msg)
        logger.debug("=== RewrapPluginRunnerV2 constructed")

    def update(self, policy, claims, key_access, context):
        """Call the plugins in order."""
        logger.debug("--- Update function called")
        req = {
            "policy": policy,
            "claims": claims,
            "keyAccess": key_access,
            "context": context,
        }
        logger.debug("req = %s", req)
        res = {"metadata": {}}

        logger.debug("number of plugins = %s", len(self._plugins))
        for plugin in self._plugins:
            # run the plugin
            logger.debug("--- Updating with Plugin %s", plugin)
            (new_req, new_res) = plugin.update(req, res)

            # Check the new_res value.  Recycle if it is ok.
            if new_res is None:
                message = "Plugin canceled rewrap"
                logger.error(message)
                raise AuthorizationError(message)
            if isinstance(new_res, str):
                # Signale rejection with rejection message
                logger.error(new_res)
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise AuthorizationError(new_res)
            res = new_res

            # Check the req.policy value. Recycle if it is ok.
            if "policy" not in new_req:
                message = "Plugin return value did not contain policy."
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise PluginFailedError(message)
            new_policy = new_req["policy"]
            if not isinstance(new_policy, Policy):
                # Some sort of bug occured
                message = f"returned policy is type {type(policy)}"
                logger.setLevel(logging.DEBUG)  # dynamically escalate level
                raise PluginFailedError(message)

            # We're redeclaring `req` here because while we want to
            # feed any updated policy from a plugin to the next plugin
            # in the chain, we don't want plugins to modify any other part
            # of the payload (I think)
            req = {
                "policy": new_policy,
                "claims": claims,
                "keyAccess": key_access,
                "context": context,
            }

        # if no errors have been thrown, assume everything is ok and
        # return the meaningful values.
        logger.debug(
            "--- Rewrap.update complete with res = [%s]; policy = [%s]", res, policy
        )

        return req["policy"], res

    def fetch_attributes(self, namespaces):
        """Call the plugins in order."""
        logger.debug("--- fetch_attributes function called")
        result = {}
        logger.debug("number of plugins = %s", len(self._plugins))
        for plugin in self._plugins:
            # run the plugin
            logger.debug("--- Updating with Plugin %s", plugin)
            result = plugin.fetch_attributes(namespaces)

        # if no errors have been thrown, assume everything is ok and
        # return the meaningful values.
        logger.debug("--- fetch_attributes complete with result = %s", result)

        return result
