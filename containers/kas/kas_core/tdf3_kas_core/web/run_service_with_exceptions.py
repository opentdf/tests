"""This utility function consolidates exception handling for the server."""

import functools
import logging

from cryptography.exceptions import InvalidTag
from flask import current_app, jsonify
from jsonschema.exceptions import ValidationError

from tdf3_kas_core.errors import AttributePolicyConfigError
from tdf3_kas_core.errors import AdjudicatorError
from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import BadRequestError
from tdf3_kas_core.errors import CryptoError
from tdf3_kas_core.errors import EntityError
from tdf3_kas_core.errors import ForbiddenError
from tdf3_kas_core.errors import InvalidAttributeError
from tdf3_kas_core.errors import InvalidBindingError
from tdf3_kas_core.errors import JWTError
from tdf3_kas_core.errors import KeyAccessError
from tdf3_kas_core.errors import KeyNotFoundError
from tdf3_kas_core.errors import PluginBackendError
from tdf3_kas_core.errors import PluginIsBadError
from tdf3_kas_core.errors import PluginFailedError
from tdf3_kas_core.errors import PolicyError
from tdf3_kas_core.errors import RequestError
from tdf3_kas_core.errors import PrivateKeyInvalidError
from tdf3_kas_core.errors import UnauthorizedError
from tdf3_kas_core.errors import UnknownAttributePolicyError
from tdf3_kas_core.errors import RequestTimeoutError
from tdf3_kas_core.errors import ContractNotFoundError
from tdf3_kas_core.errors import PolicyNotFoundError
from tdf3_kas_core.errors import RouteNotFoundError
from tdf3_kas_core.errors import PolicyCreateError

# https://owasp.org/www-community/Security_Headers
# https://flask.palletsprojects.com/en/master/security/
security_headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
}


def run_service_with_exceptions(service=None, *, success=200):
    """Convert return value to JSON, or error to a status code, as appropriate."""
    if service is None:
        # If passed with no arguments, generate yourself.
        # See: https://pybit.es/decorator-optional-argument.html
        return functools.partial(run_service_with_exceptions, success=success)

    """Decorates a service method to return appropriate HTTP status code."""

    @functools.wraps(service)
    def wrap_service(*args, **kwargs):
        logger = logging.getLogger(service.__module__)

        def handle_exception(code, exception):
            """Handle the exception."""
            try:
                err_msg = f"[{code}] Error: [{exception.message}]"
            except AttributeError:
                err_msg = f"[{code}] Error: [{exception}]"

            res = jsonify(err_msg)
            res.status_code = code
            for key in security_headers.keys():
                res.headers.setdefault(key, security_headers[key])

            if code < 500:
                logger.warning(err_msg, exc_info=1)
            elif code == 500:
                logger.critical(err_msg, exc_info=1)
            else:
                logger.error(err_msg, exc_info=1)
            return res

        try:
            logger.debug(
                "Request Start: %s(args: %s; kwargs: %s)",
                service.__name__,
                args,
                kwargs,
            )

            response = service(*args, **kwargs)

            logger.debug(
                "Request Finish: %s(args: %s; kwargs: %s)",
                service.__name__,
                args,
                kwargs,
            )
            to_response = jsonify
            if success == 204:
                to_response = lambda _: current_app.response_class(
                    status=204, mimetype=current_app.config["JSONIFY_MIMETYPE"]
                )
            return to_response(response), success, security_headers

        except AttributePolicyConfigError as err:
            # We've received a bad attribute schema somehow.
            return handle_exception(500, err)

        except AdjudicatorError as err:
            # User not authorized, most likely
            return handle_exception(403, err)

        except AuthorizationError as err:
            return handle_exception(403, err)

        except CryptoError as err:
            return handle_exception(403, err)

        except InvalidTag as err:
            return handle_exception(400, err)

        except EntityError as err:
            return handle_exception(400, err)

        except InvalidAttributeError as err:
            return handle_exception(502, err)

        except InvalidBindingError as err:
            return handle_exception(403, err)

        except JWTError as err:
            return handle_exception(403, err)

        except KeyAccessError as err:
            return handle_exception(403, err)

        except KeyNotFoundError as err:
            return handle_exception(403, err)

        except PluginBackendError as err:
            # Like a 500, but for somebody else.
            return handle_exception(502, err)

        except PluginFailedError as err:
            # Plugins should throw specific, actionable exceptions
            # This indicates there is something wrong about the plugin
            # contract, e.g. an assertion about plugin request or response
            # invariants failed to hold.
            return handle_exception(500, err)

        except PluginIsBadError as err:
            # Error in the plugin configuration itself.
            return handle_exception(500, err)

        except PolicyError as err:
            return handle_exception(403, err)

        except PrivateKeyInvalidError as err:
            return handle_exception(403, err)

        except RequestError as err:
            return handle_exception(403, err)

        except ValidationError as err:
            return handle_exception(400, err)

        except UnknownAttributePolicyError as err:
            return handle_exception(403, err)

        except RequestTimeoutError as err:
            return handle_exception(503, err)

        except PolicyNotFoundError as err:
            return handle_exception(404, err)

        except RouteNotFoundError as err:
            return handle_exception(404, err)

        except ContractNotFoundError as err:
            return handle_exception(404, err)

        except PolicyCreateError as err:
            return handle_exception(403, err)

        except BadRequestError as err:
            return handle_exception(400, err)

        except UnauthorizedError as err:
            return handle_exception(401, err)

        except ForbiddenError as err:
            return handle_exception(403, err)

        except Exception as err:
            return handle_exception(500, err)

    return wrap_service
