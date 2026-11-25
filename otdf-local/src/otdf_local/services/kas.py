"""KAS (Key Access Service) instance management."""

from pathlib import Path

from otdf_local.config.features import PlatformFeatures
from otdf_local.config.ports import Ports
from otdf_local.config.settings import Settings
from otdf_local.health.checks import check_http_health, check_port
from otdf_local.process.manager import (
    ManagedProcess,
    ProcessManager,
    kill_process_on_port,
)
from otdf_local.services.base import Service, ServiceInfo, ServiceType
from otdf_local.utils.yaml import copy_yaml_with_updates, get_nested, load_yaml

# 5 minutes, in nanoseconds -- the unit services.kas.key_cache_expiration takes.
KM3_KEY_CACHE_EXPIRATION_NS = 300_000_000_000


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

    @property
    def is_kao_uri(self) -> bool:
        """Check if this instance resolves managed keys by the KAO's KAS URI."""
        return Ports.is_kao_uri_kas(self._kas_name)

    def _generate_config(self) -> Path:
        """Generate the KAS config file from template."""
        config_path = self.settings.get_kas_config_path(self._kas_name)
        template_path = self.settings.kas_template_config

        # The platform config is the single source of the root key --
        # `PlatformService._generate_config` writes one if the template has
        # none. Starting anyway with "" produces a KAS that unwraps nothing,
        # which surfaces only at decrypt time as "cipher: message
        # authentication failed", with no pointer to the config.
        platform_config_path = self.settings.platform_config
        start_platform_first = "Start the platform first so the config is generated."
        if not platform_config_path.is_file():
            raise ValueError(
                f"No platform config at {platform_config_path}; cannot configure "
                f"KAS {self._kas_name}. {start_platform_first}"
            )
        platform_config = load_yaml(platform_config_path)
        root_key = get_nested(platform_config, "services.kas.root_key", "")
        if not root_key:
            raise ValueError(
                f"No services.kas.root_key in {platform_config_path}; cannot "
                f"configure KAS {self._kas_name}. {start_platform_first}"
            )

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
            updates["services.kas.preview.hybrid_tdf_enabled"] = True
            # registered_kas_uri should NOT have /kas suffix
            updates["services.kas.registered_kas_uri"] = f"http://localhost:{self.port}"

        # Off by default, and left off for km1 so it stays usable as the negative
        # control: with this unset, a KAO naming a URI other than registered_kas_uri
        # above should fail to resolve. km2 is off too, but only by default.
        if self.is_kao_uri:
            updates["services.kas.kas_uri_from_kao"] = True
            # Matches the km3 step in .github/workflows/xtest.yml. The cache test asserts
            # a "found private key in cache" line per registry key, which is only emitted
            # at debug and only if the entry is still live -- hence the 5-minute window.
            updates["services.kas.key_cache_expiration"] = KM3_KEY_CACHE_EXPIRATION_NS
            updates["logger.level"] = "debug"

        copy_yaml_with_updates(template_path, config_path, updates)
        return config_path

    def _preflight(self) -> bool:
        """Generate and validate the config, reporting failure via start_error.

        A bad config is reported the same way a failed launch is, so callers
        keep the single `start() -> bool` + `start_error` contract of
        `Service.start`.
        """
        self.settings.ensure_directories()
        try:
            self._generate_config()
        except (OSError, ValueError) as e:
            self.start_error = str(e)
            return False
        return True

    def start(self) -> bool:
        """Start the KAS instance."""
        # Validate before touching the port so a bad config leaves any running
        # KAS in place. (`restart` stops first, so it runs this before stop.)
        self.start_error = None
        if not self._preflight():
            return False
        config_path = self.settings.get_kas_config_path(self._kas_name)

        # Kill any existing process on the port
        kill_process_on_port(self.port)

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

        # See PlatformService.start: OPENTDF_LOG_LEVEL resolved to the config key
        # "log.level", not "logger.level", so it was never read. Level belongs in
        # the generated config -- km3's debug level is set in _generate_config.
        self._process = self._process_manager.start(
            name=self.name,
            cmd=cmd,
            cwd=self.settings.platform_dir,
            log_file=log_file,
        )

        self.start_error = self._process.startup_error()
        return self.start_error is None

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
        from otdf_local.config.settings import get_settings

        settings = get_settings()

    return KASManager(settings, _kas_process_manager)
