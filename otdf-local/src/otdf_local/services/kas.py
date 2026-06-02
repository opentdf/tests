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
        return self.settings.get_kas_port(self._kas_name)

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.SUBPROCESS

    @property
    def health_url(self) -> str:
        return f"http://localhost:{self.port}/healthz"

    @property
    def is_key_management(self) -> bool:
        """Check if this is a key management KAS instance.

        When an instance.yaml pins this KAS, prefer the manifest's `mode`
        field. Otherwise fall back to the legacy name-based heuristic.
        """
        instance = self.settings.load_instance()
        if instance is not None and self._kas_name in instance.kas:
            return instance.kas[self._kas_name].mode == "key_management"
        return Ports.is_km_kas(self._kas_name)

    def _instance_paths(self) -> tuple[Path, Path] | None:
        """Return (binary, worktree) for an instance-pinned KAS, or None."""
        instance = self.settings.load_instance()
        if instance is None:
            return None
        pin = instance.kas.get(self._kas_name)
        if pin is None or pin.dist is None:
            return None
        binary = self.settings.platform_binary_for(pin.dist)
        if not binary.exists():
            raise FileNotFoundError(
                f"KAS {self._kas_name} binary not found at {binary}. "
                f"Run `otdf-sdk-mgr install release platform:{pin.dist}`."
            )
        worktree = binary.parent
        version_file = binary.parent / ".version"
        if version_file.exists():
            for line in version_file.read_text().splitlines():
                if line.startswith("worktree="):
                    worktree = Path(line.split("=", 1)[1].strip())
                    break
        return binary, worktree

    def _generate_config(self) -> Path:
        """Generate the KAS config file from template."""
        instance_paths = self._instance_paths()
        if instance_paths is not None:
            _, worktree = instance_paths
            platform_dir = worktree
        else:
            platform_dir = self.settings._require_platform_dir()

        config_path = self.settings.get_kas_config_path(self._kas_name)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        template_path = platform_dir / "opentdf-kas-mode.yaml"

        # Load platform config to get root_key
        platform_config = load_yaml(self.settings.platform_config)
        root_key = get_nested(platform_config, "services.kas.root_key", "")

        # Detect platform features to determine supported config options
        features = PlatformFeatures.detect(platform_dir)
        logger_output = "stderr" if features.supports("logger_stderr") else "stdout"

        updates = {
            "logger.type": "json",
            "logger.output": logger_output,
            "server.port": self.port,
            "services.kas.root_key": root_key,
        }

        # Per-KAS features from instance.yaml override the legacy heuristic.
        instance = self.settings.load_instance()
        kas_pin = instance.kas.get(self._kas_name) if instance is not None else None
        extra_features: dict[str, bool] = (
            dict(kas_pin.features) if kas_pin is not None else {}
        )

        if self.is_key_management:
            updates["services.kas.preview.key_management"] = True
            updates["services.kas.preview.ec_tdf_enabled"] = True
            updates["services.kas.preview.hybrid_tdf_enabled"] = True
            # registered_kas_uri should NOT have /kas suffix
            updates["services.kas.registered_kas_uri"] = f"http://localhost:{self.port}"

        for feature_key, feature_val in extra_features.items():
            updates[f"services.kas.preview.{feature_key}"] = feature_val

        copy_yaml_with_updates(template_path, config_path, updates)
        return config_path

    def start(self) -> bool:
        """Start the KAS instance."""
        self.settings.ensure_directories()
        kill_process_on_port(self.port)
        config_path = self._generate_config()

        instance_paths = self._instance_paths()
        if instance_paths is not None:
            binary, worktree = instance_paths
            cmd = [str(binary), "start", "--config-file", str(config_path)]
            cwd = worktree
        else:
            cmd = ["go", "run", "./service", "start", "--config-file", str(config_path)]
            cwd = self.settings._require_platform_dir()

        log_file = self.settings.get_kas_log_path(self._kas_name)

        self._process = self._process_manager.start(
            name=self.name,
            cmd=cmd,
            cwd=cwd,
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
    """Manages KAS instances.

    When an `instance.yaml` is loaded, the managed set is restricted to the
    KAS names listed in the manifest. Otherwise the legacy full set
    (alpha/beta/gamma/delta/km1/km2) is managed.
    """

    def __init__(
        self,
        settings: Settings,
        process_manager: ProcessManager | None = None,
    ) -> None:
        self.settings = settings
        self._process_manager = process_manager or ProcessManager()
        self._instances: dict[str, KASService] = {}

        instance = settings.load_instance()
        if instance is not None and instance.kas:
            kas_names = list(instance.kas.keys())
        else:
            kas_names = Ports.all_kas_names()

        for kas_name in kas_names:
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
        """Start only standard (non-key-management) KAS instances under management."""
        results = {}
        for name, inst in self._instances.items():
            if not inst.is_key_management:
                results[name] = inst.start()
        return results

    def start_km(self) -> dict[str, bool]:
        """Start only key-management KAS instances under management."""
        results = {}
        for name, inst in self._instances.items():
            if inst.is_key_management:
                results[name] = inst.start()
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
