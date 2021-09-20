"""Wrappers for handling flask and openapi routes."""
import functools
import logging
import traceback
from pprint import pprint

from flask import current_app, jsonify

from ..errors import (
    AlreadyExistsError,
    AuthorizationError,
    EasRequestError,
    Error,
    NotFound,
    NotImplementedException,
)

NUM_ITEMS_HEADER = "meta-total-count"

# https://owasp.org/www-community/Security_Headers
# https://flask.palletsprojects.com/en/master/security/
security_headers = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
}


def statusify(f=None, *, success=200):
    """Convert return value to JSON, or error to a status code, as appropriate."""
    if f is None:
        # If passed with no arguments, generate yourself.
        # See: https://pybit.es/decorator-optional-argument.html
        return functools.partial(statusify, success=success)

    @functools.wraps(f)
    def wrapper_handle_error(*args, **kwargs):
        get_logger().debug("%s(args: %s; kwargs: %s)", f.__name__, args, kwargs)

        try:
            content = f(*args, **kwargs)

        except (
            NotFound,
            NotImplementedException,
            EasRequestError,
            AlreadyExistsError,
        ) as err:
            get_logger().warning(err.message, exc_info=is_debug())
            return err.to_raw(), err.status, security_headers
        except AuthorizationError as err:
            get_logger().error(err.message, exc_info=is_debug())
            return err.to_raw(), 403, security_headers
        except Exception as err:
            get_logger().error(traceback.format_exc(), exc_info=True)
            if is_debug():
                return (
                    Error(
                        f"Exception {type(err)}: {err}", title="Server error"
                    ).to_raw(),
                    500,
                    security_headers,
                )
            else:
                return (
                    Error("A server error occurred.", title="Server error").to_raw(),
                    500,
                    security_headers,
                )

        else:  # if no errors
            if current_app.testing:
                print("returning response:")
                pprint(content)
            to_response = jsonify
            if success == 204:
                to_response = lambda _: current_app.response_class(
                    status=204, mimetype=current_app.config["JSONIFY_MIMETYPE"]
                )
            if type(content) is tuple:
                (content_only, headers) = content
                for key in security_headers.keys():
                    headers.setdefault(key, security_headers[key])
                return to_response(content_only), success, headers
            else:
                return to_response(content), success, security_headers

    return wrapper_handle_error


def is_debug():
    """Should we provide extra information for debugging? Boolean"""
    return not current_app or current_app.testing or current_app.debug


def get_logger():
    """Get the appropriate logger - Flask logger or python logging logger"""
    if not current_app or current_app.testing:
        # If app isn't running (like in unit testing) use basic logger
        # If testing, address an issue where Flask logger is not printing during pytest runs
        return logging.getLogger(__name__)

    return current_app.logger
