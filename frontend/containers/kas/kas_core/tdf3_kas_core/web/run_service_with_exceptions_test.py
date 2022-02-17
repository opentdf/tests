"""Test the exceptions."""

import pytest

import flask

from tdf3_kas_core.errors import AttributePolicyConfigError
from tdf3_kas_core.errors import AdjudicatorError
from tdf3_kas_core.errors import AuthorizationError
from tdf3_kas_core.errors import BadRequestError
from tdf3_kas_core.errors import CryptoError
from tdf3_kas_core.errors import EntityError
from tdf3_kas_core.errors import ForbiddenError
from tdf3_kas_core.errors import InvalidAttributeError
from tdf3_kas_core.errors import InvalidBindingError
from tdf3_kas_core.errors import KeyAccessError
from tdf3_kas_core.errors import KeyNotFoundError
from tdf3_kas_core.errors import JWTError
from tdf3_kas_core.errors import PluginBackendError
from tdf3_kas_core.errors import PluginIsBadError
from tdf3_kas_core.errors import PluginFailedError
from tdf3_kas_core.errors import PolicyError
from tdf3_kas_core.errors import PrivateKeyInvalidError
from tdf3_kas_core.errors import RequestError
from tdf3_kas_core.errors import UnauthorizedError
from tdf3_kas_core.errors import UnknownAttributePolicyError
from tdf3_kas_core.errors import RequestTimeoutError
from tdf3_kas_core.errors import PolicyCreateError
from tdf3_kas_core.errors import PolicyNotFoundError
from tdf3_kas_core.errors import RouteNotFoundError
from tdf3_kas_core.errors import ContractNotFoundError

from .run_service_with_exceptions import run_service_with_exceptions


def create_service(ex):
    """Create a service function that throws the exception."""

    def service(req):
        """Throw the exception."""
        raise ex("error message delivered")

    return service


@pytest.fixture
def req():
    """Generate generic Flask requests."""
    app = flask.Flask(__name__)
    with app.test_request_context("/"):
        yield flask.request


def test_AttributePolicyConfigError(req):
    """Test AttributePolicyConfigError."""
    serv = create_service(AttributePolicyConfigError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 500


def test_AdjudicatorError(req):
    """Test AdjudicatorError."""
    serv = create_service(AdjudicatorError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_AuthorizationError(req):
    """Test AuthorizationError."""
    serv = create_service(AuthorizationError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_CryptoError(req):
    """Test CryptoError."""
    serv = create_service(CryptoError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_EntityError(req):
    """Test EntityError."""
    serv = create_service(EntityError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 400


def test_InvalidAttributeError(req):
    """Test InvalidAttributeError."""
    serv = create_service(InvalidAttributeError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 502


def test_InvalidBindingError(req):
    """Test InvalidBindingError."""
    serv = create_service(InvalidBindingError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_KeyAccessError(req):
    """Test KeyAccessError."""
    serv = create_service(KeyAccessError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_KeyNotFoundError(req):
    """Test KeyNotFoundError."""
    serv = create_service(KeyNotFoundError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_JWTError(req):
    """Test JWTError."""
    serv = create_service(JWTError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_PluginBackendError(req):
    """Test PluginBackendError."""
    serv = create_service(PluginBackendError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 502


def test_PluginFailedError(req):
    """Test PluginFailedError."""
    serv = create_service(PluginFailedError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 500


def test_PluginIsBadError(req):
    """Test PluginIsBadError."""
    serv = create_service(PluginIsBadError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 500


def test_PolicyError(req):
    """Test PolicyError."""
    serv = create_service(PolicyError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_PrivateKeyInvalidError(req):
    """Test PrivateKeyInvalidError."""
    serv = create_service(PrivateKeyInvalidError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_RequestError(req):
    """Test RequestError."""
    serv = create_service(RequestError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_BadRequestError(req):
    """Test RequestError."""
    serv = create_service(BadRequestError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 400


def test_UnauthorizedError(req):
    """Test UnauthorizedError."""
    serv = create_service(UnauthorizedError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 401


def test_ForbiddenError(req):
    """Test ForbiddenError."""
    serv = create_service(ForbiddenError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_UnknownAttributePolicyError(req):
    """Test UnknownAttributePolicyError."""
    serv = create_service(UnknownAttributePolicyError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_RequestTimeoutError(req):
    """Test RequestTimeoutError."""
    serv = create_service(RequestTimeoutError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 503


def test_PolicyCreateError(req):
    """Test PolicyCreateError."""
    serv = create_service(PolicyCreateError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 403


def test_PolicyNotFoundError(req):
    """Test PolicyNotFoundError."""
    serv = create_service(PolicyNotFoundError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 404


def test_RouteNotFoundError(req):
    """Test RouteNotFoundError."""
    serv = create_service(RouteNotFoundError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 404


def test_ContractNotFoundError(req):
    """Test ContractNotFoundError."""
    serv = create_service(ContractNotFoundError)
    actual = (run_service_with_exceptions(serv))(req)
    assert isinstance(actual, flask.Response)
    assert actual.status_code == 404
