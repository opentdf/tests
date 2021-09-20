import pytest

from flask import Flask
from json import loads
from unittest.mock import Mock, patch

from .heartbeat import healthz, ping
from ..db_connectors import SQLiteConnector
from ..util import VERSION

SERVER_ERROR = "Server error"


@pytest.fixture(scope="session")
def mock_app_debug():
    app = Flask(__name__)
    app.testing = True
    assert isinstance(app, Flask)
    return app


def test_ping(mock_app_debug):
    with mock_app_debug.app_context():
        (response, code, headers) = ping()
        assert code == 200
        assert VERSION in response.get_data(as_text=True)
        assert loads(response.get_data()) == {"version": VERSION}


def test_healthz_liveness_success(mock_app_debug):
    with mock_app_debug.app_context():
        (response, code, headers) = healthz(probe="liveness")
        assert code == 204
        assert not response.get_data()


def test_healthz_readiness_success(mock_app_debug):
    with mock_app_debug.app_context():
        (response, code, headers) = healthz(probe="readiness")
        assert code == 204
        assert not response.get_data()


def test_healthz_error(mock_app_debug):
    db = SQLiteConnector.get_instance()
    mock = Mock()
    mock.side_effect = Exception("atabase!")
    with mock_app_debug.app_context(), patch.object(db, "check_schema", mock):
        (response, code, headers) = healthz(probe="readiness")
        assert code == 500
        assert response["title"] == SERVER_ERROR
        # In debug mode, message should be more specific
        assert "atabase" in response["detail"]
