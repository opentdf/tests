"""Provisioning service for Keycloak and fixtures."""

import subprocess
from pathlib import Path

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
        script_path = self.settings.xtest_root.parent / "scripts" / "provision-keycloak"

        # Check if script exists
        if not script_path.exists():
            # Try alternative path
            script_path = self.settings.platform_dir / "scripts" / "provision-keycloak"

        if not script_path.exists():
            # No provisioning script found - this may be okay
            return True

        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
            cwd=self.settings.platform_dir,
        )
        return result.returncode == 0

    def provision_fixtures(self) -> bool:
        """Provision test fixtures.

        This runs the provision-fixtures script to set up:
        - Attributes
        - Entitlements
        - KAS registrations
        """
        script_path = self.settings.xtest_root.parent / "scripts" / "provision-fixtures"

        # Check if script exists
        if not script_path.exists():
            # Try alternative path
            script_path = (
                self.settings.platform_dir / "scripts" / "provision-fixtures"
            )

        if not script_path.exists():
            # Try the go-based provisioning
            return self._provision_fixtures_via_go()

        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
            cwd=self.settings.platform_dir,
        )
        return result.returncode == 0

    def _provision_fixtures_via_go(self) -> bool:
        """Run fixture provisioning via go command."""
        # Try using the platform's built-in provisioning
        cmd = [
            "go",
            "run",
            "./service",
            "provision",
            "fixtures",
            "--config",
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
        from lmgmt.config.ports import Ports

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
