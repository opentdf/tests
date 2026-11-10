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
from types import SimpleNamespace

import pytest

import fixtures.kas
import tdfs
from fixtures.kas import kas_health_error, require_km3

#: For the two tests that never reach the network. Keeping them off `_closed_port`
#: leaves it with the single caller that genuinely needs a live socket.
UNCONNECTED_URL = "http://127.0.0.1:1"


def _closed_port() -> int:
    """A port that was bound and then released, so nothing is listening on it.

    Racy in principle -- another process can bind the port between the release and
    the connect -- and deliberately kept anyway, for the one test that has to see a
    real connection refused reach the ``except`` clause in ``kas_health_error``.
    Stubbing the transport there would reduce it to asserting that an f-string
    interpolates. The race costs a flaky failure, never a false pass: anything that
    did answer on that port would fail every assertion in the test.

    Holding the socket bound-but-unlistening would reserve the port, but on macOS
    that drops the SYN instead of refusing it, so the probe times out after
    HEALTH_TIMEOUT_S and reports the wrong reason.
    """
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


def _stub_platform_features(
    monkeypatch: pytest.MonkeyPatch, *, supported: bool
) -> None:
    def skip_if_unsupported(*features: str) -> None:
        if not supported:
            pytest.skip(f"platform does not support {features}")

    monkeypatch.setattr(
        tdfs,
        "get_platform_features",
        lambda: SimpleNamespace(skip_if_unsupported=skip_if_unsupported),
    )


def test_require_km3_skips_when_the_platform_gate_is_shut(
    monkeypatch: pytest.MonkeyPatch,
):
    """A build that can't do KAO-URI lookup is not a failure.

    The URL is never probed -- the gate raises first -- which is the point: reaching
    the network here at all would mean the gate ran in the wrong order.
    """
    _stub_platform_features(monkeypatch, supported=False)

    def unreachable_probe(kas_url: str) -> str | None:
        pytest.fail(f"probed {kas_url} despite the platform gate being shut")

    monkeypatch.setattr(fixtures.kas, "kas_health_error", unreachable_probe)

    with pytest.raises(pytest.skip.Exception):
        require_km3(UNCONNECTED_URL)


def test_require_km3_fails_when_the_gate_is_open_but_km3_is_absent(
    monkeypatch: pytest.MonkeyPatch,
):
    """Past the gate the caller asked for these tests, so a missing km3 is an error.

    This is the case the old skip hid: pytest prints captured logs for errors but
    not for skips, so a mistyped KASURL7 read exactly like an unsupported build.

    What the probe failed *on* is covered by the kas_health_error tests above; here
    it is stubbed, so the branch under test cannot flake on host port activity and
    the reason can be asserted against a known string.
    """
    _stub_platform_features(monkeypatch, supported=True)
    monkeypatch.setattr(
        fixtures.kas, "kas_health_error", lambda _url: "nothing listening on 8787"
    )

    with pytest.raises(pytest.fail.Exception) as excinfo:
        require_km3(UNCONNECTED_URL)

    message = str(excinfo.value)
    assert "km3 KAS is not answering" in message
    # The probe's reason has to survive into the failure, or the message says only
    # that something is wrong and not what.
    assert "nothing listening on 8787" in message
    # The three ways out, so the reader does not have to go find them.
    assert "otdf-local up" in message
    assert "KASURL7" in message
    assert "XT_FORCE_PLATFORM_SUPPORTS" in message


def test_require_km3_passes_when_the_gate_is_open_and_km3_answers(
    kas_stub, monkeypatch: pytest.MonkeyPatch
):
    _stub_platform_features(monkeypatch, supported=True)
    url, _ = kas_stub()

    require_km3(url)


def test_proxy_environment_is_ignored(kas_stub, monkeypatch: pytest.MonkeyPatch):
    """These are loopback services; a proxy would have the probe report on itself."""
    url, _ = kas_stub()
    # Points somewhere nothing can answer, so if the proxy were honoured this fails.
    monkeypatch.setenv("http_proxy", UNCONNECTED_URL)
    monkeypatch.setenv("HTTP_PROXY", UNCONNECTED_URL)

    assert kas_health_error(url) is None
