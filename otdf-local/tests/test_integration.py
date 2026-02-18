"""Integration tests for otdf-local CLI.

These tests require Docker to be available and will start/stop real services.
"""

import subprocess
import time
from pathlib import Path

import pytest


def _find_otdf_local_root() -> Path:
    """Find the otdf-local root by locating pyproject.toml with name = 'otdf-local'."""
    current = Path(__file__).resolve()
    while current != current.parent:
        pyproject = current / "pyproject.toml"
        if pyproject.is_file() and 'name = "otdf-local"' in pyproject.read_text():
            return current
        current = current.parent
    raise FileNotFoundError("otdf-local root (pyproject.toml with name = 'otdf-local') not found")


def run_otdf_local(*args, timeout=60) -> subprocess.CompletedProcess:
    """Run otdf-local CLI command."""
    cmd = ["python", "-m", "otdf_local", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_find_otdf_local_root(),
    )


class TestCLIBasic:
    """Basic CLI functionality tests."""

    def test_version(self):
        """Test version command."""
        result = run_otdf_local("--version")
        assert result.returncode == 0
        assert "otdf-local version" in result.stdout

    def test_help(self):
        """Test help output."""
        result = run_otdf_local("--help")
        assert result.returncode == 0
        assert "OpenTDF test environment" in result.stdout

    def test_ls_no_services(self):
        """Test ls command when no services running."""
        result = run_otdf_local("ls")
        # Should succeed even with no services
        assert result.returncode == 0

    def test_ls_json(self):
        """Test ls command with JSON output."""
        result = run_otdf_local("ls", "--json", "--all")
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
        run_otdf_local("down", timeout=30)

    def test_up_down_cycle(self):
        """Test basic up/down cycle with Docker only."""
        # Start just Docker services
        result = run_otdf_local("up", "--services", "docker", timeout=120)
        # May fail if Docker isn't available, which is okay for CI
        if result.returncode != 0:
            pytest.skip("Docker not available")

        # Give it a moment
        time.sleep(2)

        # Check status
        result = run_otdf_local("status", "--json")
        assert result.returncode == 0

        # Stop services
        result = run_otdf_local("down", timeout=60)
        assert result.returncode == 0

    def test_clean_command(self):
        """Test clean command."""
        result = run_otdf_local("clean")
        assert result.returncode == 0
        assert "complete" in result.stdout.lower()
