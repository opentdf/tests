"""HTTP and port health check utilities."""

import socket
from typing import Literal

import httpx


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open and accepting connections.

    Args:
        host: Host to check
        port: Port number
        timeout: Connection timeout in seconds

    Returns:
        True if port is accepting connections
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def check_http_health(
    url: str,
    timeout: float = 5.0,
    expected_status: int | tuple[int, ...] = 200,
) -> bool:
    """Check if an HTTP endpoint returns a healthy status.

    Args:
        url: Full URL to check (e.g., http://localhost:8080/healthz)
        timeout: Request timeout in seconds
        expected_status: Expected HTTP status code(s)

    Returns:
        True if endpoint returns expected status
    """
    if isinstance(expected_status, int):
        expected_status = (expected_status,)

    try:
        response = httpx.get(url, timeout=timeout)
        return response.status_code in expected_status
    except (httpx.RequestError, httpx.TimeoutException):
        return False


def get_health_url(service: str, port: int) -> str:
    """Get the health check URL for a service.

    Args:
        service: Service name (platform, kas, keycloak)
        port: Service port

    Returns:
        Health check URL
    """
    if service == "keycloak":
        return f"http://localhost:{port}/auth/realms/master"
    elif service in ("platform", "kas"):
        return f"http://localhost:{port}/healthz"
    else:
        return f"http://localhost:{port}/healthz"


ServiceStatus = Literal["running", "stopped", "unhealthy", "unknown"]


def get_service_status(
    port: int,
    health_url: str | None = None,
) -> ServiceStatus:
    """Get comprehensive status of a service.

    Args:
        port: Service port
        health_url: Optional health check URL

    Returns:
        Service status string
    """
    # First check if port is open
    if not check_port("localhost", port):
        return "stopped"

    # If no health URL provided, assume running
    if not health_url:
        return "running"

    # Check health endpoint
    if check_http_health(health_url):
        return "running"

    return "unhealthy"
