"""Base service class defining the service interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from lmgmt.config.settings import Settings


class ServiceType(str, Enum):
    """Type of service."""

    DOCKER = "docker"
    SUBPROCESS = "subprocess"


@dataclass
class ServiceInfo:
    """Information about a service."""

    name: str
    port: int
    service_type: ServiceType
    running: bool
    healthy: bool | None = None
    pid: int | None = None
    health_url: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON output."""
        return {
            "name": self.name,
            "port": self.port,
            "type": self.service_type.value,
            "running": self.running,
            "healthy": self.healthy,
            "pid": self.pid,
        }


class Service(ABC):
    """Abstract base class for managed services."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    @abstractmethod
    def name(self) -> str:
        """Service name."""
        ...

    @property
    @abstractmethod
    def port(self) -> int:
        """Service port."""
        ...

    @property
    @abstractmethod
    def service_type(self) -> ServiceType:
        """Type of service (docker or subprocess)."""
        ...

    @property
    @abstractmethod
    def health_url(self) -> str:
        """Health check URL, if applicable."""
        pass

    @abstractmethod
    def start(self) -> bool:
        """Start the service.

        Returns:
            True if started successfully
        """
        ...

    @abstractmethod
    def stop(self) -> bool:
        """Stop the service.

        Returns:
            True if stopped successfully
        """
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """Check if the service is currently running."""
        ...

    def is_healthy(self) -> bool | None:
        """Check if the service is healthy.

        Returns:
            True if healthy, False if unhealthy, None if health check not available
        """
        from lmgmt.health.checks import check_http_health

        if not self.is_running():
            return None

        if self.health_url:
            return check_http_health(self.health_url)

        return None

    def get_info(self) -> ServiceInfo:
        """Get service information."""
        return ServiceInfo(
            name=self.name,
            port=self.port,
            service_type=self.service_type,
            running=self.is_running(),
            healthy=self.is_healthy(),
            health_url=self.health_url,
        )

    def restart(self) -> bool:
        """Restart the service.

        Returns:
            True if restarted successfully
        """
        self.stop()
        return self.start()
