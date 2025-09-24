"""Root conftest.py for the entire test suite."""

import pytest

# Load the framework pytest plugin for universal test framework support
# This provides profile-based testing, evidence collection, and service discovery
pytest_plugins = ["framework.pytest_plugin"]

def pytest_configure(config):
    """Register custom markers used across test suites."""
    config.addinivalue_line(
        "markers", "req(id): Mark test with business requirement ID"
    )
    config.addinivalue_line(
        "markers", "cap(**kwargs): Mark test with required capabilities"
    )
    config.addinivalue_line(
        "markers", "large: Mark tests that generate large files (>4GB)"
    )
    config.addinivalue_line(
        "markers", "integration: Mark integration tests that require external services"
    )
    config.addinivalue_line(
        "markers", "smoke: Mark smoke tests for quick validation"
    )

def pytest_addoption(parser):
    """Add command-line options for test configuration."""
    parser.addoption(
        "--large",
        action="store_true",
        help="generate a large (greater than 4 GiB) file for testing",
    )
    parser.addoption(
        "--sdks",
        help="select which sdks to run by default, unless overridden",
        type=str,
    )
    parser.addoption(
        "--focus",
        help="skips tests which don't use the requested sdk",
        type=str,
    )
    parser.addoption(
        "--sdks-decrypt",
        help="select which sdks to run for decrypt only",
        type=str,
    )
    parser.addoption(
        "--sdks-encrypt",
        help="select which sdks to run for encrypt only",
        type=str,
    )
    parser.addoption(
        "--containers",
        help="which container formats to test",
        type=str,
    )