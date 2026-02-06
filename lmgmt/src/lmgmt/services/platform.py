"""Platform service management."""

from pathlib import Path

from lmgmt.config.ports import Ports
from lmgmt.config.settings import Settings
from lmgmt.health.checks import check_http_health, check_port
from lmgmt.process.manager import ManagedProcess, ProcessManager, kill_process_on_port
from lmgmt.services.base import Service, ServiceInfo, ServiceType
from lmgmt.utils.yaml import copy_yaml_with_updates


class PlatformService(Service):
    """Manages the OpenTDF platform service."""

    def __init__(
        self,
        settings: Settings,
        process_manager: ProcessManager | None = None,
    ) -> None:
        super().__init__(settings)
        self._process_manager = process_manager or ProcessManager()
        self._process: ManagedProcess | None = None

    @property
    def name(self) -> str:
        return "platform"

    @property
    def port(self) -> int:
        return Ports.PLATFORM

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.SUBPROCESS

    @property
    def health_url(self) -> str:
        return f"http://localhost:{self.port}/healthz"

    def _generate_config(self) -> Path:
        """Generate the platform config file from template."""
        config_path = self.settings.platform_config
        template_path = self.settings.platform_template_config

        # Updates for platform config
        updates = {
            "logger.level": "debug",
            "logger.type": "json",
        }

        copy_yaml_with_updates(template_path, config_path, updates)
        return config_path

    def start(self) -> bool:
        """Start the platform service."""
        # Ensure directories exist
        self.settings.ensure_directories()

        # Kill any existing process on the port
        kill_process_on_port(self.port)

        # Generate config
        config_path = self._generate_config()

        # Build the command
        cmd = [
            "go",
            "run",
            "./service",
            "start",
            "--config-file",
            str(config_path),
        ]

        # Start the process
        log_file = self.settings.logs_dir / "platform.log"

        self._process = self._process_manager.start(
            name=self.name,
            cmd=cmd,
            cwd=self.settings.platform_dir,
            log_file=log_file,
            env={"OPENTDF_LOG_LEVEL": "info"},
        )

        return self._process is not None

    def stop(self) -> bool:
        """Stop the platform service."""
        if self._process:
            self._process.stop()
            self._process = None

        # Also kill any processes on the port
        kill_process_on_port(self.port)
        return True

    def is_running(self) -> bool:
        """Check if the platform is running."""
        # First check our managed process
        if self._process and self._process.running:
            return True

        # Fall back to port check (may have been started externally)
        return check_port("localhost", self.port)

    def is_healthy(self) -> bool | None:
        """Check if the platform is healthy."""
        if not self.is_running():
            return None
        return check_http_health(self.health_url)

    def get_info(self) -> ServiceInfo:
        """Get service information."""
        info = super().get_info()
        if self._process:
            info.pid = self._process.pid
        return info


# Global process manager for singleton behavior
_process_manager: ProcessManager | None = None


def get_platform_service(settings: Settings | None = None) -> PlatformService:
    """Get a PlatformService instance with shared process manager."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()

    if settings is None:
        from lmgmt.config.settings import get_settings

        settings = get_settings()

    return PlatformService(settings, _process_manager)
