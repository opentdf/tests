import pytest
from flask import Flask

from .status import statusify
from ..errors import AuthorizationError, NotFound, NotImplementedException

SERVER_ERROR = "Server error"


@pytest.fixture(scope="session")
def mock_app():
    app = Flask(__name__)
    app.testing = False
    app.debug = False
    assert isinstance(app, Flask)
    return app


@pytest.fixture(scope="session")
def mock_app_debug():
    app = Flask(__name__)
    app.testing = True
    assert isinstance(app, Flask)
    return app


def test_errors_generic(mock_app):
    @statusify
    def throw_exception():
        raise Exception("Something went wrong")

    with mock_app.app_context():
        (response, code, headers) = throw_exception()
        assert code == 500
        assert response["title"] == SERVER_ERROR
        # Not in debug mode, message should be more generic
        assert response["detail"] == "A server error occurred."


def test_errors_runtime(mock_app):
    @statusify
    def throw_runtime_error():
        raise RuntimeError("Had a runtime error")

    with mock_app.app_context():
        (response, code, headers) = throw_runtime_error()
        assert code == 500
        assert response["title"] == SERVER_ERROR
        assert response["detail"] == "A server error occurred."
        assert response["status"] == 500


def test_errors_in_debug_generic(mock_app_debug):
    @statusify
    def throw_exception():
        raise Exception("Something went wrong")

    with mock_app_debug.app_context():
        (response, code, headers) = throw_exception()
        assert code == 500
        assert response["title"] == SERVER_ERROR
        # In debug mode, message should be more specific
        assert (
            response["detail"] == "Exception <class 'Exception'>: Something went wrong"
        )


def test_errors_in_debug_runtime(mock_app_debug):
    @statusify
    def throw_runtime_error():
        raise RuntimeError("Had a runtime error")

    with mock_app_debug.app_context():
        (response, code, headers) = throw_runtime_error()
        assert code == 500
        assert response["title"] == SERVER_ERROR
        # In debug mode, message should be more specific
        assert (
            response["detail"]
            == "Exception <class 'RuntimeError'>: Had a runtime error"
        )
        assert response["status"] == 500


def test_notfound():
    e = NotFound(message="Didn't find it")
    assert e.status == 404


def test_404_not_found(mock_app_debug):
    @statusify
    def throw_not_found():
        raise NotFound(message="Foo not found")

    with mock_app_debug.app_context():
        (response, code, headers) = throw_not_found()
        assert code == 404
        assert response["title"] == "Not Found"
        assert response["detail"] == "Foo not found"
        assert response["status"] == 404


def test_501_not_implemented(mock_app_debug):
    @statusify
    def throw_not_implemented():
        raise NotImplementedException

    with mock_app_debug.app_context():
        (response, code, headers) = throw_not_implemented()
        assert code == 501
        assert response["title"] == "Not Implemented"
        assert response["detail"] == "This feature has not been implemented"
        assert response["status"] == 501


def test_403_auth_failure(mock_app_debug):
    @statusify
    def throw_auth_error():
        raise AuthorizationError(message="Sorry")

    with mock_app_debug.app_context():
        (response, code, headers) = throw_auth_error()
        assert code == 403
        assert response["title"] == "Not Authorized"
        assert response["detail"] == "Sorry"


def test_success_200(mock_app_debug):
    @statusify
    def hello_world():
        return "Hello, world!"

    with mock_app_debug.app_context():
        (response, code, headers) = hello_world()
        assert code == 200
        assert response.status_code == 200
        assert "Content-Length" in response.headers


def test_success_204(mock_app_debug):
    @statusify(success=204)
    def no_body():
        return None

    with mock_app_debug.app_context():
        (response, code, headers) = no_body()
        assert code == 204
        assert response.status_code == 204
        assert "Content-Length" not in response.headers
