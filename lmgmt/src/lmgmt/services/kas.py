"""KAS (Key Access Service) instance management."""

from pathlib import Path

from lmgmt.config.features import PlatformFeatures
from lmgmt.config.ports import Ports
from lmgmt.config.settings import Settings
from lmgmt.health.checks import check_http_health, check_port
from lmgmt.process.manager import ManagedProcess, ProcessManager, kill_process_on_port
from lmgmt.services.base import Service, ServiceInfo, ServiceType
from lmgmt.utils.yaml import copy_yaml_with_updates, get_nested, load_yaml


class KASService(Service):
    """Manages a single KAS instance."""

    def __init__(
        self,
        settings: Settings,
        kas_name: str,
        process_manager: ProcessManager | None = None,
    ) -> None:
        super().__init__(settings)
        self._kas_name = kas_name
        self._process_manager = process_manager or ProcessManager()
        self._process: ManagedProcess | None = None

    @property
    def name(self) -> str:
        return f"kas-{self._kas_name}"

    @property
    def port(self) -> int:
        return Ports.get_kas_port(self._kas_name)

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.SUBPROCESS

    @property
    def health_url(self) -> str:
        return f"http://localhost:{self.port}/healthz"

    @property
    def is_key_management(self) -> bool:
        """Check if this is a key management KAS instance."""
        return Ports.is_km_kas(self._kas_name)

    def _generate_config(self) -> Path:
        """Generate the KAS config file from template."""
        config_path = self.settings.get_kas_config_path(self._kas_name)
        template_path = self.settings.kas_template_config

        # Load platform config to get root_key
        platform_config = load_yaml(self.settings.platform_config)
        root_key = get_nested(platform_config, "services.kas.root_key", "")

        # Detect platform features to determine supported config options
        features = PlatformFeatures.detect(self.settings.platform_dir)

        # Use stderr if supported, otherwise stdout (v0.9.0 only supports stdout)
        logger_output = "stderr" if features.supports("logger_stderr") else "stdout"

        # Base updates for all KAS instances
        updates = {
            "logger.type": "json",
            "logger.output": logger_output,
            "server.port": self.port,
            "services.kas.root_key": root_key,
        }

        # Key management KAS instances need additional config
        if self.is_key_management:
            updates["services.kas.preview.key_management"] = True
            updates["services.kas.preview.ec_tdf_enabled"] = True
            # registered_kas_uri should NOT have /kas suffix
            updates["services.kas.registered_kas_uri"] = f"http://localhost:{self.port}"

        copy_yaml_with_updates(template_path, config_path, updates)
        return config_path

    def start(self) -> bool:
        """Start the KAS instance."""
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
        log_file = self.settings.get_kas_log_path(self._kas_name)

        self._process = self._process_manager.start(
            name=self.name,
            cmd=cmd,
            cwd=self.settings.platform_dir,
            log_file=log_file,
            env={"OPENTDF_LOG_LEVEL": "info"},
        )

        return self._process is not None

    def stop(self) -> bool:
        """Stop the KAS instance."""
        if self._process:
            self._process.stop()
            self._process = None

        # Also kill any processes on the port
        kill_process_on_port(self.port)
        return True

    def is_running(self) -> bool:
        """Check if the KAS instance is running."""
        if self._process and self._process.running:
            return True
        return check_port("localhost", self.port)

    def is_healthy(self) -> bool | None:
        """Check if the KAS instance is healthy."""
        if not self.is_running():
            return None
        return check_http_health(self.health_url)

    def get_info(self) -> ServiceInfo:
        """Get service information."""
        info = super().get_info()
        if self._process:
            info.pid = self._process.pid
        return info


class KASManager:
    """Manages all KAS instances."""

    def __init__(
        self,
        settings: Settings,
        process_manager: ProcessManager | None = None,
    ) -> None:
        self.settings = settings
        self._process_manager = process_manager or ProcessManager()
        self._instances: dict[str, KASService] = {}

        # Create instances for all configured KAS
        for kas_name in Ports.all_kas_names():
            self._instances[kas_name] = KASService(
                settings, kas_name, self._process_manager
            )

    def get(self, name: str) -> KASService | None:
        """Get a KAS instance by name."""
        return self._instances.get(name)

    def start_all(self) -> dict[str, bool]:
        """Start all KAS instances."""
        results = {}
        for name, instance in self._instances.items():
            results[name] = instance.start()
        return results

    def stop_all(self) -> dict[str, bool]:
        """Stop all KAS instances."""
        results = {}
        for name, instance in self._instances.items():
            results[name] = instance.stop()
        return results

    def start_standard(self) -> dict[str, bool]:
        """Start only standard (non-km) KAS instances."""
        results = {}
        for name in Ports.standard_kas_names():
            results[name] = self._instances[name].start()
        return results

    def start_km(self) -> dict[str, bool]:
        """Start only key management KAS instances."""
        results = {}
        for name in Ports.km_kas_names():
            results[name] = self._instances[name].start()
        return results

    def get_all_info(self) -> list[ServiceInfo]:
        """Get info for all KAS instances."""
        return [instance.get_info() for instance in self._instances.values()]

    def get_running(self) -> list[str]:
        """Get names of running KAS instances."""
        return [name for name, inst in self._instances.items() if inst.is_running()]

    def __iter__(self):
        return iter(self._instances.values())


# Global process manager for singleton behavior
_kas_process_manager: ProcessManager | None = None


def get_kas_manager(settings: Settings | None = None) -> KASManager:
    """Get a KASManager instance with shared process manager."""
    global _kas_process_manager
    if _kas_process_manager is None:
        _kas_process_manager = ProcessManager()

    if settings is None:
        from lmgmt.config.settings import get_settings

        settings = get_settings()

    return KASManager(settings, _kas_process_manager)
