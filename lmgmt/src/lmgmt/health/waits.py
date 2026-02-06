"""Wait-for-ready utilities for services."""

import time
from collections.abc import Callable

from lmgmt.health.checks import check_http_health, check_port


class WaitTimeoutError(Exception):
    """Raised when a wait operation times out."""

    def __init__(self, service: str, timeout: float) -> None:
        self.service = service
        self.timeout = timeout
        super().__init__(f"Timeout waiting for {service} after {timeout}s")


def wait_for_port(
    port: int,
    host: str = "localhost",
    timeout: float = 30.0,
    poll_interval: float = 0.5,
    service_name: str = "service",
) -> bool:
    """Wait for a port to become available.

    Args:
        port: Port number to wait for
        host: Host to check
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        service_name: Name for error messages

    Returns:
        True when port is available

    Raises:
        WaitTimeoutError: If timeout is reached
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if check_port(host, port):
            return True
        time.sleep(poll_interval)

    raise WaitTimeoutError(service_name, timeout)


def wait_for_health(
    url: str,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
    service_name: str = "service",
    expected_status: int | tuple[int, ...] = 200,
) -> bool:
    """Wait for an HTTP health endpoint to return healthy.

    Args:
        url: Health check URL
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        service_name: Name for error messages
        expected_status: Expected HTTP status code(s)

    Returns:
        True when healthy

    Raises:
        WaitTimeoutError: If timeout is reached
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if check_http_health(url, expected_status=expected_status):
            return True
        time.sleep(poll_interval)

    raise WaitTimeoutError(service_name, timeout)


def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 30.0,
    poll_interval: float = 0.5,
    service_name: str = "condition",
) -> bool:
    """Wait for an arbitrary condition to become true.

    Args:
        condition: Callable that returns True when ready
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        service_name: Name for error messages

    Returns:
        True when condition is met

    Raises:
        WaitTimeoutError: If timeout is reached
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            if condition():
                return True
        except Exception:
            pass  # Treat exceptions as "not ready yet"
        time.sleep(poll_interval)

    raise WaitTimeoutError(service_name, timeout)


def wait_for_multiple(
    checks: list[tuple[str, Callable[[], bool]]],
    timeout: float = 60.0,
    poll_interval: float = 1.0,
) -> dict[str, bool]:
    """Wait for multiple conditions, returning status of each.

    Args:
        checks: List of (name, condition_callable) tuples
        timeout: Maximum time to wait in seconds
        poll_interval: Time between check rounds

    Returns:
        Dict mapping service names to their final status (True if ready)
    """
    deadline = time.monotonic() + timeout
    results = {name: False for name, _ in checks}
    pending = list(checks)

    while pending and time.monotonic() < deadline:
        still_pending = []
        for name, condition in pending:
            try:
                if condition():
                    results[name] = True
                else:
                    still_pending.append((name, condition))
            except Exception:
                still_pending.append((name, condition))

        pending = still_pending
        if pending:
            time.sleep(poll_interval)

    return results
