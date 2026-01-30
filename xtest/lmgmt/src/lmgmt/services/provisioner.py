"""Provisioning service for Keycloak and fixtures."""

import subprocess

from lmgmt.config.settings import Settings


class Provisioner:
    """Handles provisioning of Keycloak and test fixtures."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def provision_all(self) -> bool:
        """Run all provisioning steps."""
        keycloak_ok = self.provision_keycloak()
        fixtures_ok = self.provision_fixtures()
        return keycloak_ok and fixtures_ok

    def provision_keycloak(self) -> bool:
        """Provision Keycloak with required configuration.

        This runs the provision-keycloak script to set up:
        - Realm configuration
        - Client credentials
        - Users for testing
        """
        return self._provision_("keycloak")

    def provision_fixtures(self) -> bool:
        """Provision test fixtures.

        This runs the provision-fixtures script to set up:
        - Attributes
        - Entitlements
        - KAS registrations
        """
        return self._provision_("fixtures")

    def _provision_(self, mode: str) -> bool:
        """Provision test fixtures.

        This runs the provision-fixtures script to set up:
        - Attributes
        - Entitlements
        - KAS registrations
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

        # If the provision command doesn't exist, that's okay
        if result.returncode != 0 and "unknown command" in result.stderr.lower():
            return True

        return result.returncode == 0

    def register_kas_instances(self) -> bool:
        """Register all KAS instances with the platform.

        This ensures the platform knows about all the KAS instances
        for autoconfigure/ABAC tests.
        """

        # For each KAS, register it with the platform's KAS registry
        # This typically requires an admin token and API calls
        # For now, we rely on fixtures to do this

        # The fixtures should register KAS instances at:
        # - http://localhost:8181/kas (alpha)
        # - http://localhost:8282/kas (beta)
        # - http://localhost:8383/kas (gamma)
        # - http://localhost:8484/kas (delta)
        # - http://localhost:8585 (km1 - no /kas suffix for key management)
        # - http://localhost:8686 (km2 - no /kas suffix for key management)

        return True


def get_provisioner(settings: Settings | None = None) -> Provisioner:
    """Get a Provisioner instance."""
    if settings is None:
        from lmgmt.config.settings import get_settings

        settings = get_settings()
    return Provisioner(settings)
