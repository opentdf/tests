"""All the custom errors are here."""


class Error(Exception):
    """The base class for custom expressions."""

    def __init__(self, message=None):
        """Record an optional message string."""
        self.message = message


class AttributePolicyConfigError(Error):
    """Raise if the attribute policy is not correct.

    The attribute policy is loaded from the Attribute server (EAS).
    If loading the policy fails, the server is in a bad state."""


class AdjudicatorError(Error):
    """Raise if the adjudicator does something unusual."""


class AuthorizationError(Error):
    """Raise when entity is not authorized for something."""


class CryptoError(Error):  # noqa: D204
    """Raise for unknown error in cryptography module."""


class EntityError(Error):
    """Raise when the entity instance cannot be formed."""


class ClaimsError(Error):
    """Raise when the claims instance cannot be formed."""


class InvalidAttributeError(Error):
    """Raise on attribute exceptions (e.g. descriptor won't parse)."""


class InvalidBindingError(Error):
    """Raise when the binding does not pass the checks."""


class KeyAccessError(Error):
    """Raise when the provided key access object is invalid."""


class KeyNotFoundError(Error):
    """Raise when the keymaster is asked for a key that doesn't exist."""


class JWTError(Error):
    """Raise when there is some failure creating or verifying a JWT."""


class PluginBackendError(Error):
    """Generic 502 errors, for use by plugins."""


class PluginIsBadError(Error):
    """Throw when something other than a plugin is provided."""


class PluginFailedError(Error):
    """Raise if a plugin fails to return a valid response."""


class PolicyError(Error):
    """Raise if a policy is malformed."""


class PrivateKeyInvalidError(Error):
    """Raise if the private key for unwrapping the wrapped key is not ok."""


class RequestError(Error):
    """DEPRECATED

    This always threw a 403 despite sounding like a 400.

    Raise if the request is not ok. Body should be json, etc."""


class BadRequestError(Error):
    """Raise if the request is not ok, usually due to a ValueError. Generic 400"""


class UnauthorizedError(Error):
    """Raise if the request is not authorized or unable to be authorized due to a request error. Generic 401

    As MDN says, this is really 'unauthenticated'."""


class ForbiddenError(Error):
    """Raise if the backend reprots an error, or sometimes if the key is bad maybe. Generic 403"""


class UnknownAttributePolicyError(Error):
    """Raise if the policy for the attribute cannot be found."""


class RequestTimeoutError(Error):
    """Raise if the request is timed out."""


class PolicyCreateError(Error):
    """Raise when the backend fail to create a policy"""


class PolicyNotFoundError(Error):
    """Raise when policy is missing on the backend."""


class RouteNotFoundError(Error):
    """Raise when route is missing in current config."""


class ContractNotFoundError(Error):
    """Raise when contract is missing."""


class ServerStartupError(Error):
    """Raise when there is an error starting the KAS server."""


class PolicyBindingError(Error):
    """Raise when the verification of policy binding fails."""


class NanoTDFParseError(Error):
    """Raise when fail to parse the nano TDF."""
