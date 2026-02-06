"""Docker compose service management."""

import subprocess

from lmgmt.config.ports import Ports
from lmgmt.config.settings import Settings
from lmgmt.health.checks import check_http_health, check_port
from lmgmt.services.base import Service, ServiceInfo, ServiceType


class DockerService(Service):
    """Manages Docker compose services (Keycloak, PostgreSQL)."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._compose_file = settings.docker_compose_file

    @property
    def name(self) -> str:
        return "docker"

    @property
    def port(self) -> int:
        return Ports.KEYCLOAK  # Primary port for status

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.DOCKER

    @property
    def health_url(self) -> str:
        return f"http://localhost:{Ports.KEYCLOAK}/auth/realms/master"

    def start(self) -> bool:
        """Start Docker compose services."""
        if not self._compose_file.exists():
            return False

        result = subprocess.run(
            ["docker", "compose", "-f", str(self._compose_file), "up", "-d"],
            capture_output=True,
            text=True,
            cwd=self._compose_file.parent,
        )
        return result.returncode == 0

    def stop(self) -> bool:
        """Stop Docker compose services."""
        if not self._compose_file.exists():
            return False

        result = subprocess.run(
            ["docker", "compose", "-f", str(self._compose_file), "down"],
            capture_output=True,
            text=True,
            cwd=self._compose_file.parent,
        )
        return result.returncode == 0

    def is_running(self) -> bool:
        """Check if Docker services are running."""
        # Check if both Keycloak and PostgreSQL ports are open
        keycloak_up = check_port("localhost", Ports.KEYCLOAK)
        postgres_up = check_port("localhost", Ports.POSTGRES)
        return keycloak_up and postgres_up

    def is_healthy(self) -> bool | None:
        """Check if Keycloak is responding."""
        if not self.is_running():
            return None
        return check_http_health(self.health_url)

    def get_container_status(self) -> dict[str, dict]:
        """Get detailed status of each container."""
        if not self._compose_file.exists():
            return {}

        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(self._compose_file),
                "ps",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            cwd=self._compose_file.parent,
        )

        if result.returncode != 0:
            return {}

        # Parse JSON output (one object per line)
        import json

        containers = {}
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    data = json.loads(line)
                    containers[data.get("Service", data.get("Name", "unknown"))] = {
                        "state": data.get("State", "unknown"),
                        "status": data.get("Status", "unknown"),
                        "health": data.get("Health", ""),
                    }
                except json.JSONDecodeError:
                    pass

        return containers

    def get_all_info(self) -> list[ServiceInfo]:
        """Get info for all Docker services."""
        keycloak_running = check_port("localhost", Ports.KEYCLOAK)
        postgres_running = check_port("localhost", Ports.POSTGRES)

        keycloak_healthy = None
        if keycloak_running:
            keycloak_healthy = check_http_health(
                f"http://localhost:{Ports.KEYCLOAK}/auth/realms/master"
            )

        return [
            ServiceInfo(
                name="keycloak",
                port=Ports.KEYCLOAK,
                service_type=ServiceType.DOCKER,
                running=keycloak_running,
                healthy=keycloak_healthy,
                health_url=f"http://localhost:{Ports.KEYCLOAK}/auth/realms/master",
            ),
            ServiceInfo(
                name="postgres",
                port=Ports.POSTGRES,
                service_type=ServiceType.DOCKER,
                running=postgres_running,
                healthy=None,  # No HTTP health check for postgres
            ),
        ]


def get_docker_service(settings: Settings | None = None) -> DockerService:
    """Get a DockerService instance."""
    if settings is None:
        from lmgmt.config.settings import get_settings

        settings = get_settings()
    return DockerService(settings)
