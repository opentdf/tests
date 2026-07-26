"""Pytest fixtures for end-to-end OpenTelemetry tracing.

Wraps each test in a ``pytest.test`` span and exports a ``TRACEPARENT`` into the
environment so the SDK CLI subprocess (and, through it, platform/KAS) join the
same trace. On failure the trace's Jaeger URL is printed so the failure links
directly to the full request chain.

Tracing is opt-in and a strict no-op unless enabled — it activates when either
``--tracing`` is passed or ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. When disabled
nothing is imported or initialized, so normal runs pay no cost.

See ``fixtures/audit.py`` for the sibling log-collection fixture this mirrors.
"""

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

logger = logging.getLogger("xtest")

# Default local collector (Jaeger all-in-one, OTLP gRPC) and UI, matching the
# `tracing` docker-compose profile started by `otdf-local up --tracing`.
_DEFAULT_OTLP_ENDPOINT = "localhost:4317"
_DEFAULT_JAEGER_UI = "http://localhost:16686"


@dataclass
class TracingSession:
    """Holds the initialized tracer and the Jaeger UI base URL for a session."""

    tracer: object  # opentelemetry.trace.Tracer
    provider: object  # opentelemetry.sdk.trace.TracerProvider
    jaeger_ui_url: str


@pytest.fixture(scope="session")
def _tracing(request: pytest.FixtureRequest) -> Iterator[TracingSession | None]:
    """Initialize an OTLP tracer for the session, or yield None when disabled.

    Enabled when ``--tracing`` is passed or ``OTEL_EXPORTER_OTLP_ENDPOINT`` is
    set; otherwise this is a no-op and no OpenTelemetry code runs.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    enabled = bool(request.config.getoption("--tracing", default=False)) or bool(
        endpoint
    )
    if not enabled:
        yield None
        return

    endpoint = endpoint or _DEFAULT_OTLP_ENDPOINT

    # Imported lazily so the disabled path never requires the OTel packages.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "xtest"}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    logger.info("xtest tracing enabled, exporting to %s", endpoint)

    session = TracingSession(
        tracer=provider.get_tracer("xtest"),
        provider=provider,
        jaeger_ui_url=os.getenv("JAEGER_UI_URL", _DEFAULT_JAEGER_UI),
    )
    try:
        yield session
    finally:
        # Flush any buffered spans before the process exits.
        provider.shutdown()


def _test_span_attributes(request: pytest.FixtureRequest) -> dict[str, str]:
    """Derive span attributes (sdk, container) from the test's parametrization."""
    attrs: dict[str, str] = {"test.name": request.node.name}
    callspec = getattr(request.node, "callspec", None)
    if callspec is None:
        return attrs
    params = callspec.params
    for key in ("encrypt_sdk", "decrypt_sdk", "sdk"):
        if key in params:
            attrs["test.sdk"] = str(params[key])
            break
    if "container" in params:
        attrs["test.container"] = str(params["container"])
    return attrs


@pytest.fixture(autouse=True)
def _trace_test(
    request: pytest.FixtureRequest, _tracing: TracingSession | None
) -> Iterator[None]:
    """Wrap each test in a ``pytest.test`` span and propagate it to subprocesses.

    Sets ``TRACEPARENT`` in the environment for the duration of the test so the
    SDK CLI (invoked via ``subprocess.run`` in ``tdfs.py``, which copies
    ``os.environ``) starts a child span under this one. Prints the Jaeger trace
    URL on failure.
    """
    if _tracing is None:
        yield
        return

    from opentelemetry import trace
    from opentelemetry.propagate import inject

    tracer = _tracing.tracer
    with tracer.start_as_current_span("pytest.test") as span:  # type: ignore[attr-defined]
        for key, value in _test_span_attributes(request).items():
            span.set_attribute(key, value)

        # Export the active context so child processes continue this trace.
        carrier: dict[str, str] = {}
        inject(carrier)
        prev_traceparent = os.environ.get("TRACEPARENT")
        if "traceparent" in carrier:
            os.environ["TRACEPARENT"] = carrier["traceparent"]

        trace_id = format(span.get_span_context().trace_id, "032x")
        trace_url = f"{_tracing.jaeger_ui_url}/trace/{trace_id}"
        try:
            yield
        finally:
            # Restore prior TRACEPARENT to avoid leaking across tests.
            if prev_traceparent is None:
                os.environ.pop("TRACEPARENT", None)
            else:
                os.environ["TRACEPARENT"] = prev_traceparent

            rep = getattr(request.node, "rep_call", None)
            if rep is not None and rep.failed:
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                print(f"\nTrace: {trace_url}")
