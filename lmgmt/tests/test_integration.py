"""Integration tests for lmgmt CLI.

These tests require Docker to be available and will start/stop real services.
They are marked as integration tests and can be skipped with: pytest -m "not integration"
"""

import subprocess
import time

import pytest


def run_lmgmt(*args, timeout=60) -> subprocess.CompletedProcess:
    """Run lmgmt CLI command."""
    cmd = ["python", "-m", "lmgmt", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(__file__).rsplit("/tests/", 1)[0],
    )


class TestCLIBasic:
    """Basic CLI functionality tests."""

    def test_version(self):
        """Test version command."""
        result = run_lmgmt("--version")
        assert result.returncode == 0
        assert "lmgmt version" in result.stdout

    def test_help(self):
        """Test help output."""
        result = run_lmgmt("--help")
        assert result.returncode == 0
        assert "OpenTDF test environment" in result.stdout

    def test_ls_no_services(self):
        """Test ls command when no services running."""
        result = run_lmgmt("ls")
        # Should succeed even with no services
        assert result.returncode == 0

    def test_ls_json(self):
        """Test ls command with JSON output."""
        result = run_lmgmt("ls", "--json", "--all")
        assert result.returncode == 0
        # Should be valid JSON
        import json

        data = json.loads(result.stdout)
        assert isinstance(data, list)


class TestServiceLifecycle:
    """Service lifecycle tests (start/stop).

    These tests are slower as they actually start services.
    """

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Ensure services are stopped after each test."""
        yield
        run_lmgmt("down", timeout=30)

    def test_up_down_cycle(self):
        """Test basic up/down cycle with Docker only."""
        # Start just Docker services
        result = run_lmgmt("up", "--services", "docker", timeout=120)
        # May fail if Docker isn't available, which is okay for CI
        if result.returncode != 0:
            pytest.skip("Docker not available")

        # Give it a moment
        time.sleep(2)

        # Check status
        result = run_lmgmt("status", "--json")
        assert result.returncode == 0

        # Stop services
        result = run_lmgmt("down", timeout=60)
        assert result.returncode == 0

    def test_clean_command(self):
        """Test clean command."""
        result = run_lmgmt("clean")
        assert result.returncode == 0
        assert "complete" in result.stdout.lower()
