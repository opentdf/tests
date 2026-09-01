"""Provisioning service for Keycloak and fixtures."""

import subprocess
from dataclasses import dataclass

from otdf_local.config.settings import Settings

# Seed for the multi-strategy ERS test fixtures. Idempotent so
# `otdf-local restart` doesn't fail on repeat runs. Read by the
# xtest_sql_call1_by_azp / xtest_sql_call2_by_username strategies
# defined in xtest/platform-configs/opentdf-multistrategy.yaml.
_ERS_MS_SEED_SQL = """
CREATE TABLE IF NOT EXISTS ers_attributes (
    username   TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    active     BOOLEAN NOT NULL DEFAULT true
);
INSERT INTO ers_attributes (username, department)
VALUES ('opentdf', 'finance')
ON CONFLICT (username) DO UPDATE
SET department = EXCLUDED.department,
    active     = true;
"""


@dataclass
class ProvisionResult:
    """Result of a provisioning operation."""

    success: bool
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0

    def __bool__(self) -> bool:
        """Allow boolean checks for backward compatibility."""
        return self.success


class Provisioner:
    """Handles provisioning of Keycloak and test fixtures."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def provision_all(self) -> ProvisionResult:
        """Run all provisioning steps."""
        keycloak_result = self.provision_keycloak()
        fixtures_result = self.provision_fixtures()
        ers_ms_result = self.provision_ers_ms_seed()

        # If all succeeded, return success
        if keycloak_result and fixtures_result and ers_ms_result:
            return ProvisionResult(success=True)

        # Otherwise, return failure with first error
        if not keycloak_result:
            return keycloak_result
        if not fixtures_result:
            return fixtures_result
        return ers_ms_result

    def provision_keycloak(self) -> ProvisionResult:
        """Provision Keycloak with required configuration.

        This runs the provision-keycloak script to set up:
        - Realm configuration
        - Client credentials
        - Users for testing
        """
        return self._provision_("keycloak")

    def provision_fixtures(self) -> ProvisionResult:
        """Provision test fixtures.

        This runs the provision-fixtures script to set up:
        - Attributes
        - Entitlements
        - KAS registrations
        """
        return self._provision_("fixtures")

    def provision_ers_ms_seed(self) -> ProvisionResult:
        """Seed the ers-postgres database used by the multi-strategy ERS platform.

        Executes CREATE TABLE + INSERT via `docker exec ers_test_postgres psql`.
        Idempotent so `otdf-local restart` doesn't fail on repeat runs.

        No-op when the ers_test_postgres container isn't running — otdf-local
        is used by many contributors who don't need multi-strategy ERS, and
        a missing container is not a provisioning failure for them.
        """
        # Skip cleanly if the container is not running (users who aren't
        # exercising multi-strategy ERS don't need this seed).
        check_running = subprocess.run(
            [
                "docker",
                "ps",
                "-q",
                "-f",
                "name=ers_test_postgres",
                "-f",
                "status=running",
            ],
            capture_output=True,
            text=True,
        )
        if not check_running.stdout.strip():
            return ProvisionResult(
                success=True,
                stdout="ers_test_postgres container not running; skipping seed.",
            )

        cmd = [
            "docker",
            "exec",
            "-i",
            "ers_test_postgres",
            "psql",
            "-U",
            "ers_test_user",
            "-d",
            "ers_test",
            "-v",
            "ON_ERROR_STOP=1",
        ]
        result = subprocess.run(
            cmd,
            input=_ERS_MS_SEED_SQL,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error_lines = result.stderr.strip().split("\n")
            return ProvisionResult(
                success=False,
                error_message=error_lines[-1] if error_lines else "seed failed",
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
        return ProvisionResult(
            success=True,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
        )

    def _provision_(self, mode: str) -> ProvisionResult:
        """Execute a provisioning operation.

        Args:
            mode: The provisioning mode ("keycloak" or "fixtures")

        Returns:
            ProvisionResult with success status and error details
        """
        cmd = [
            "go",
            "run",
            "./service",
            "provision",
            mode,
            "--config-file",
            str(self.settings.platform_config),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.settings.platform_dir,
        )

        # If provisioning failed, extract error message from stderr
        if result.returncode != 0:
            error_lines = result.stderr.strip().split("\n")
            error_message = error_lines[-1] if error_lines else "Unknown error"
            return ProvisionResult(
                success=False,
                error_message=error_message,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )

        # Success
        return ProvisionResult(
            success=True,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode,
        )


def get_provisioner(settings: Settings | None = None) -> Provisioner:
    """Get a Provisioner instance."""
    if settings is None:
        from otdf_local.config.settings import get_settings

        settings = get_settings()
    return Provisioner(settings)
