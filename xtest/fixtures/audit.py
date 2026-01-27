"""Pytest fixtures for KAS audit log collection and assertion.

This module provides fixtures that enable automatic collection of logs from KAS
services during test execution. Tests can use the `audit_logs` fixture to
assert on log contents.

Example:
    def test_rewrap(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, audit_logs):
        ct_file = encrypt_sdk.encrypt(pt_file, ...)
        audit_logs.mark("before_decrypt")
        decrypt_sdk.decrypt(ct_file, ...)
        audit_logs.assert_contains(r"rewrap.*200", min_count=1, since_mark="before_decrypt")
"""

import logging
import os
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from audit_logs import AuditLogAsserter, AuditLogCollector

logger = logging.getLogger("xtest")


@dataclass
class AuditLogConfig:
    """Configuration for audit log collection."""

    enabled: bool
    """Whether audit log collection is enabled."""

    platform_dir: Path
    """Path to platform directory containing docker-compose.yaml."""

    services: list[str]
    """List of docker compose service names to monitor."""

    write_on_failure: bool
    """Whether to write logs to disk when tests fail."""

    output_dir: Path
    """Directory to write audit logs on failure."""


@pytest.fixture(scope="session")
def audit_log_config(request: pytest.FixtureRequest) -> AuditLogConfig:
    """Configuration for audit log collection.

    This session-scoped fixture reads CLI options and environment variables
    to configure audit log collection behavior.

    CLI Options:
        --no-audit-logs: Disable audit log collection globally
        --audit-log-services: Comma-separated list of services to monitor
        --audit-log-dir: Directory for audit logs on failure

    Environment Variables:
        PLATFORM_DIR: Path to platform directory (default: ../../platform)
        PLATFORM_LOG_FILE: Path to main KAS log file
        KAS_ALPHA_LOG_FILE, KAS_BETA_LOG_FILE, etc: Paths to additional KAS log files
    """
    # Check if disabled via CLI
    enabled = not request.config.getoption("--no-audit-logs", default=False)

    # Get platform directory from environment
    platform_dir = Path(os.getenv("PLATFORM_DIR", "../../platform"))

    # Get services to monitor from CLI or use defaults
    services_opt = request.config.getoption("--audit-log-services", default=None)
    if services_opt:
        services = [s.strip() for s in services_opt.split(",")]
    else:
        # Default KAS services
        services = [
            "kas",
            "kas-alpha",
            "kas-beta",
            "kas-gamma",
            "kas-delta",
            "kas-km1",
            "kas-km2",
        ]

    # Get output directory from CLI or use default
    output_dir_opt = request.config.getoption("--audit-log-dir", default=None)
    if output_dir_opt:
        output_dir = Path(output_dir_opt)
    else:
        output_dir = Path("tmp/audit-logs")

    return AuditLogConfig(
        enabled=enabled,
        platform_dir=platform_dir,
        services=services,
        write_on_failure=True,
        output_dir=output_dir,
    )


@pytest.fixture(scope="session")
def kas_log_files(audit_log_config: AuditLogConfig) -> dict[str, Path] | None:
    """Discover KAS log files from environment variables.

    Checks for log file paths set by GitHub Actions or other automation.
    Returns dict mapping service names to log file paths.

    Environment Variables:
        PLATFORM_LOG_FILE: Main KAS/platform log
        KAS_ALPHA_LOG_FILE, KAS_BETA_LOG_FILE, etc: Additional KAS logs
    """
    log_files = {}

    # Check for main platform log
    platform_log = os.getenv("PLATFORM_LOG_FILE")
    if platform_log:
        log_files["kas"] = Path(platform_log)

    # Check for additional KAS logs
    kas_mapping = {
        "KAS_ALPHA_LOG_FILE": "kas-alpha",
        "KAS_BETA_LOG_FILE": "kas-beta",
        "KAS_GAMMA_LOG_FILE": "kas-gamma",
        "KAS_DELTA_LOG_FILE": "kas-delta",
        "KAS_KM1_LOG_FILE": "kas-km1",
        "KAS_KM2_LOG_FILE": "kas-km2",
    }

    for env_var, service_name in kas_mapping.items():
        log_path = os.getenv(env_var)
        if log_path:
            log_files[service_name] = Path(log_path)

    # If no env vars found, try default locations
    if not log_files:
        log_dir = audit_log_config.platform_dir / "logs"
        if log_dir.exists():
            logger.debug(f"No log file env vars found, checking {log_dir}")
            for service in audit_log_config.services:
                if service == "kas":
                    log_file = log_dir / "kas-main.log"
                else:
                    log_file = log_dir / f"{service}.log"

                if log_file.exists():
                    log_files[service] = log_file

    if log_files:
        logger.info(f"Found {len(log_files)} KAS log files for collection")
        return log_files
    else:
        logger.debug("No KAS log files found, audit log collection will be disabled")
        return None


@pytest.fixture(scope="function")
def audit_logs(
    request: pytest.FixtureRequest,
    audit_log_config: AuditLogConfig,
    kas_log_files: dict[str, Path] | None,
) -> Iterator[AuditLogAsserter]:
    """Collect and assert on KAS audit logs during test execution.

    This fixture automatically collects logs from KAS services during test
    execution and provides assertion methods for validation.

    The fixture is function-scoped, meaning each test gets its own log collector
    with clean state. Logs are buffered in memory and only written to disk on
    test failure for debugging.

    Usage:
        def test_rewrap(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, audit_logs):
            ct_file = encrypt_sdk.encrypt(pt_file, ...)
            audit_logs.mark("before_decrypt")
            decrypt_sdk.decrypt(ct_file, ...)
            audit_logs.assert_contains(
                r"rewrap.*200",
                min_count=1,
                since_mark="before_decrypt"
            )

    Opt-out for specific test:
        @pytest.mark.no_audit_logs
        def test_without_logs():
            pass

    Args:
        request: Pytest request fixture
        audit_log_config: Session-scoped configuration
        kas_log_files: Session-scoped log file paths

    Yields:
        AuditLogAsserter: Object for making assertions on collected logs
    """
    # Check for opt-out marker
    if request.node.get_closest_marker("no_audit_logs"):
        logger.debug(f"Audit log collection disabled for {request.node.name} (marker)")
        yield AuditLogAsserter(None)
        return

    # Check if disabled globally
    if not audit_log_config.enabled:
        logger.debug("Audit log collection disabled globally")
        yield AuditLogAsserter(None)
        return

    # Create collector with log files if available
    collector = AuditLogCollector(
        platform_dir=audit_log_config.platform_dir,
        services=audit_log_config.services,
        log_files=kas_log_files,
    )

    # Try to start collection
    try:
        collector.start()
    except Exception as e:
        logger.warning(f"Failed to start audit log collection: {e}")
        yield AuditLogAsserter(None)
        return

    # If collection is disabled (e.g., docker compose not available), yield no-op asserter
    if collector._disabled:
        yield AuditLogAsserter(None)
        collector.stop()
        return

    # Create asserter
    asserter = AuditLogAsserter(collector)

    # Store collector reference for pytest hook
    request.node._audit_log_collector = collector

    try:
        yield asserter
    finally:
        # Stop collection
        collector.stop()

        # Write logs to disk on test failure
        if audit_log_config.write_on_failure:
            # Check if test failed
            if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
                # Generate log file name from test node id
                log_file_name = (
                    request.node.nodeid.replace("/", "_")
                    .replace("::", "_")
                    .replace("[", "_")
                    .replace("]", "")
                    + ".log"
                )
                log_file = audit_log_config.output_dir / log_file_name

                try:
                    collector.write_to_disk(log_file)
                    logger.info(f"Audit logs written to: {log_file}")

                    # Store path on node for pytest-html integration
                    request.node._audit_log_file = str(log_file)
                except Exception as e:
                    logger.error(f"Failed to write audit logs: {e}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Pytest hook to capture test results for audit log collection.

    This hook runs for each test phase (setup, call, teardown) and stores
    the test result on the item so the audit_logs fixture can check if
    the test failed.
    """
    outcome = yield
    report = outcome.get_result()

    # Store report on item for fixture to access
    setattr(item, f"rep_{report.when}", report)
    return report
