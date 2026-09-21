"""Offline tests for the KAS health probe in ``fixtures/kas.py``.

No platform, no SDK. ``kas_health_error`` is what stands between "km3 was never
started" and a connection-refused buried in an SDK CLI's stderr, so what matters
is that it reports the right *reason* -- and in particular that a typo'd
``KASURL7`` is reported as a bad URL rather than as a dead service, which would
send you to debug a KAS that is running fine.
"""

import http.server
import socket
import threading

import pytest

from fixtures.kas import kas_health_error


def _closed_port() -> int:
    """A port that was bound and then released, so nothing is listening on it."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def kas_stub():
    """Start throwaway HTTP servers; returns ``(url, requested_paths)`` per call."""
    servers: list[http.server.ThreadingHTTPServer] = []

    def _start(status: int = 200) -> tuple[str, list[str]]:
        paths: list[str] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                paths.append(self.path)
                self.send_response(status)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                """Silence the default stderr access log."""

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_port}", paths

    yield _start

    for server in servers:
        server.shutdown()
        server.server_close()


def test_healthy_kas_reports_no_error(kas_stub):
    url, _ = kas_stub()
    assert kas_health_error(url) is None


def test_probe_hits_healthz_at_the_root_not_under_the_url_path(kas_stub):
    """/healthz is served from the root, so a /kas suffix must not be carried over."""
    url, paths = kas_stub()

    assert kas_health_error(f"{url}/kas") is None
    assert paths == ["/healthz"]


def test_unreachable_kas_reports_the_url_and_the_cause():
    reason = kas_health_error(f"http://127.0.0.1:{_closed_port()}")

    assert reason is not None
    assert "/healthz" in reason
    # Without the cause the message is just "it didn't work", which is where the
    # old bool-returning probe left you.
    assert "refused" in reason.lower() or "connection" in reason.lower()


def test_non_200_is_an_error_not_a_pass(kas_stub):
    url, _ = kas_stub(status=204)

    reason = kas_health_error(url)

    assert reason is not None
    assert "204" in reason


def test_server_error_reports_the_status(kas_stub):
    url, _ = kas_stub(status=503)

    reason = kas_health_error(url)

    assert reason is not None
    assert "503" in reason


@pytest.mark.parametrize(
    "bad", ["", "   ", "localhost:8787", "/kas", "ftp://localhost:8787", "8787"]
)
def test_a_url_that_is_not_an_absolute_http_url_raises(bad: str):
    """A bad KASURL7 is a bug in the environment, not evidence about the KAS."""
    with pytest.raises(ValueError, match="not a usable KAS URL"):
        kas_health_error(bad)


def test_proxy_environment_is_ignored(kas_stub, monkeypatch: pytest.MonkeyPatch):
    """These are loopback services; a proxy would have the probe report on itself."""
    url, _ = kas_stub()
    # Points at a port nothing is on, so if the proxy were honoured this fails.
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{_closed_port()}")
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{_closed_port()}")

    assert kas_health_error(url) is None
