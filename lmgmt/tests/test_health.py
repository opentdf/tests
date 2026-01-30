"""Tests for health check utilities."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from lmgmt.health.checks import check_http_health, check_port, get_service_status
from lmgmt.health.waits import (
    WaitTimeoutError,
    wait_for_condition,
    wait_for_health,
    wait_for_port,
)


class SimpleHealthHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for testing."""

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == "/unhealthy":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Error")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logging


@pytest.fixture
def health_server():
    """Start a simple HTTP server for health check testing."""
    server = HTTPServer(("127.0.0.1", 0), SimpleHealthHandler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    yield port

    server.shutdown()


class TestCheckPort:
    """Tests for check_port function."""

    def test_open_port(self, health_server):
        """Test that check_port returns True for open port."""
        assert check_port("127.0.0.1", health_server) is True

    def test_closed_port(self):
        """Test that check_port returns False for closed port."""
        # Port 1 is unlikely to be open
        assert check_port("127.0.0.1", 59999, timeout=0.1) is False

    def test_invalid_host(self):
        """Test that check_port returns False for invalid host."""
        assert check_port("invalid.host.example", 8080, timeout=0.1) is False


class TestCheckHttpHealth:
    """Tests for check_http_health function."""

    def test_healthy_endpoint(self, health_server):
        """Test healthy endpoint returns True."""
        url = f"http://127.0.0.1:{health_server}/healthz"
        assert check_http_health(url) is True

    def test_unhealthy_endpoint(self, health_server):
        """Test unhealthy endpoint returns False."""
        url = f"http://127.0.0.1:{health_server}/unhealthy"
        assert check_http_health(url) is False

    def test_nonexistent_endpoint(self, health_server):
        """Test nonexistent endpoint returns False."""
        url = f"http://127.0.0.1:{health_server}/nonexistent"
        assert check_http_health(url) is False

    def test_connection_refused(self):
        """Test connection refused returns False."""
        url = "http://127.0.0.1:59999/healthz"
        assert check_http_health(url, timeout=0.1) is False

    def test_custom_expected_status(self, health_server):
        """Test custom expected status."""
        url = f"http://127.0.0.1:{health_server}/unhealthy"
        assert check_http_health(url, expected_status=500) is True
        assert check_http_health(url, expected_status=(500, 503)) is True


class TestGetServiceStatus:
    """Tests for get_service_status function."""

    def test_running_service(self, health_server):
        """Test running service returns 'running'."""
        url = f"http://127.0.0.1:{health_server}/healthz"
        status = get_service_status(health_server, url)
        assert status == "running"

    def test_unhealthy_service(self, health_server):
        """Test unhealthy service returns 'unhealthy'."""
        url = f"http://127.0.0.1:{health_server}/unhealthy"
        status = get_service_status(health_server, url)
        assert status == "unhealthy"

    def test_stopped_service(self):
        """Test stopped service returns 'stopped'."""
        status = get_service_status(59999)
        assert status == "stopped"

    def test_no_health_url(self, health_server):
        """Test service without health URL returns 'running' if port open."""
        status = get_service_status(health_server, None)
        assert status == "running"


class TestWaitForPort:
    """Tests for wait_for_port function."""

    def test_port_already_open(self, health_server):
        """Test returns immediately when port is already open."""
        assert wait_for_port(health_server, timeout=1.0) is True

    def test_timeout_on_closed_port(self):
        """Test raises WaitTimeoutError when port stays closed."""
        with pytest.raises(WaitTimeoutError) as exc_info:
            wait_for_port(59999, timeout=0.1, poll_interval=0.05)
        assert "59999" not in str(exc_info.value)  # Uses service_name
        assert "0.1s" in str(exc_info.value)


class TestWaitForHealth:
    """Tests for wait_for_health function."""

    def test_already_healthy(self, health_server):
        """Test returns immediately when already healthy."""
        url = f"http://127.0.0.1:{health_server}/healthz"
        assert wait_for_health(url, timeout=1.0) is True

    def test_timeout_on_unhealthy(self, health_server):
        """Test raises WaitTimeoutError when stays unhealthy."""
        url = f"http://127.0.0.1:{health_server}/unhealthy"
        with pytest.raises(WaitTimeoutError):
            wait_for_health(url, timeout=0.2, poll_interval=0.05)


class TestWaitForCondition:
    """Tests for wait_for_condition function."""

    def test_condition_already_true(self):
        """Test returns immediately when condition is true."""
        assert wait_for_condition(lambda: True, timeout=1.0) is True

    def test_condition_becomes_true(self):
        """Test waits for condition to become true."""
        counter = {"value": 0}

        def condition():
            counter["value"] += 1
            return counter["value"] >= 3

        assert wait_for_condition(condition, timeout=1.0, poll_interval=0.05) is True

    def test_timeout_when_condition_stays_false(self):
        """Test raises WaitTimeoutError when condition stays false."""
        with pytest.raises(WaitTimeoutError):
            wait_for_condition(lambda: False, timeout=0.1, poll_interval=0.05)

    def test_handles_exception_in_condition(self):
        """Test treats exceptions as 'not ready'."""
        counter = {"value": 0}

        def condition():
            counter["value"] += 1
            if counter["value"] < 3:
                raise RuntimeError("Not ready")
            return True

        assert wait_for_condition(condition, timeout=1.0, poll_interval=0.05) is True
