"""Provisioning service for Keycloak and fixtures."""

import subprocess
from dataclasses import dataclass

from otdf_local.config.settings import Settings


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

        # If both succeeded, return success
        if keycloak_result and fixtures_result:
            return ProvisionResult(success=True)

        # Otherwise, return failure with first error
        if not keycloak_result:
            return keycloak_result
        return fixtures_result

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
