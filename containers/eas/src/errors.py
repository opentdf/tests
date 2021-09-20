"""All the custom error definitions are here."""

import logging

logger = logging.getLogger(__name__)


class Error(Exception):
    """The base class for custom expressions, including standard problem details message used for errors.

    From https://tools.ietf.org/html/draft-ietf-appsawg-http-problem-00.
    Not all fields are implemented."""

    def __init__(self, message: str = None, title: str = "Problem", status: int = 500):
        # Human-readable summary of problem
        self.title = title
        # Detail: An human readable explanation specific to this occurrence of the problem.
        self.message = message
        # http status code
        self.status = status
        logger.debug(
            f"Generating Exception: type={type(self.__class__.__name__)}, title={title}, message={message}, status={status}"
        )

    def to_raw(self):
        return {"title": self.title, "detail": self.message, "status": self.status}


class AuthorizationError(Error):  # noqa: D204
    """Raise when entity is not authorized for something."""

    def __init__(self, message="Not authorized"):
        super(AuthorizationError, self).__init__(
            message=message, title="Not Authorized", status=403
        )


class EasRequestError(Error):
    """Malformed request of some kind"""

    def __init__(self, message="Invalid request"):
        super(EasRequestError, self).__init__(
            message=message, title="Bad request", status=400
        )


class MalformedAttributeError(EasRequestError):  # noqa: D204
    """Raise when attribute body is not correct."""

    pass


class AlreadyExistsError(Error):  # noqa: D204
    """Raise when user is attempting to create an object that already exists."""

    def __init__(self, message="Already exists"):
        super(AlreadyExistsError, self).__init__(
            message=message, title="Already Exists", status=409
        )


class AttributeExistsError(AlreadyExistsError):  # noqa: D204
    """Raise when attribute already exists."""

    pass


class CryptoError(Error):  # noqa: D204
    """Raise for unknown error in cryptography module."""

    pass


class MalformedEntityError(EasRequestError):  # noqa: D204
    """Raise when user or entity body is not correct."""

    pass


class EntityExistsError(AlreadyExistsError):  # noqa: D204
    """Raise when user or entity already exists."""

    pass


class MalformedAuthorityNamespaceError(EasRequestError):  # noqa: D204
    """Raise when authority namespace body is not correct."""

    pass


class AuthorityNamespaceExistsError(AlreadyExistsError):  # noqa: D204
    """Raise when an authority namespace already exists."""

    pass


class NotFound(Error):
    """Raise a query fails to find an item, e.g. attribute, user, or key."""

    def __init__(self, message="Not Found"):
        super(NotFound, self).__init__(message=message, title="Not Found", status=404)


class KeyNotFoundError(NotFound):
    """Raise when the keymaster is asked for a key that doesn't exist."""


class ConfigurationError(Error):
    """Raise when a configuration problem prevents the application from operating."""


class NotImplementedException(Error):
    """Raise when a function or feature is not implemented, or in an abstract class."""

    def __init__(self, message="This feature has not been implemented"):
        super(NotImplementedException, self).__init__(
            message=message, title="Not Implemented", status=501
        )
