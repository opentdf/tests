"""Platform service management."""

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
from otdf_local.utils.keys import get_golden_keyring_entries, setup_golden_keys
from otdf_local.utils.yaml import (
    append_to_list,
    copy_yaml_with_updates,
    load_yaml,
    save_yaml,
)


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
        instance = self.settings.load_instance()
        if instance is not None:
            return Ports.platform_port_for(instance.ports.base)
        return Ports.PLATFORM

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.SUBPROCESS

    @property
    def health_url(self) -> str:
        return f"http://localhost:{self.port}/healthz"

    def _instance_dist_paths(self) -> tuple[Path, Path] | None:
        """Return (binary, worktree) for an instance-pinned platform, or None.

        The platform binary is at `xtest/platform/dist/<dist>/service` and its
        `.version` file records the source worktree path that should be used
        as `cwd` so the binary finds its embedded resources.
        """
        from otdf_sdk_mgr.semver import normalize_version

        instance = self.settings.load_instance()
        if instance is None:
            return None

        if instance.platform.dist is not None:
            dist_label = instance.platform.dist
        elif instance.platform.source is not None:
            dist_label = normalize_version(instance.platform.source.ref)
        else:
            return None

        binary = self.settings.platform_binary_for(dist_label)
        if not binary.exists():
            raise FileNotFoundError(
                f"Platform binary not found at {binary}. "
                f"Run `otdf-sdk-mgr install scenario` to provision it."
            )
        worktree = binary.parent  # safe fallback
        version_file = binary.parent / ".version"
        if version_file.exists():
            for line in version_file.read_text().splitlines():
                if line.startswith("worktree="):
                    worktree = Path(line.split("=", 1)[1].strip())
                    break
        return binary, worktree

    def _generate_config(self) -> Path:
        """Generate the platform config file from template."""
        instance_paths = self._instance_dist_paths()
        if instance_paths is not None:
            _, worktree = instance_paths
            platform_dir = worktree
        else:
            platform_dir = self.settings._require_platform_dir()

        config_path = self.settings.platform_config
        template_path = platform_dir / "opentdf.yaml"
        if not template_path.exists():
            template_path = platform_dir / "opentdf-dev.yaml"

        # Detect platform features to determine supported config options
        features = PlatformFeatures.detect(platform_dir)

        # Use stderr if supported, otherwise stdout (v0.9.0 only supports stdout)
        logger_output = "stderr" if features.supports("logger_stderr") else "stdout"

        # Updates for platform config
        updates = {
            "logger.level": "debug",
            "logger.type": "json",
            "logger.output": logger_output,
        }

        copy_yaml_with_updates(template_path, config_path, updates)

        # Set up golden keys for legacy TDF tests
        self._setup_golden_keys(config_path)

        return config_path

    def _setup_golden_keys(self, config_path: Path) -> None:
        """Add golden keys to platform config for legacy TDF decryption.

        Extracts keys from extra-keys.json and adds them to the platform config
        so legacy golden TDFs can be decrypted.
        """
        # In multi-instance mode, golden keys live alongside the instance
        # config; otherwise they go into the legacy platform_dir.
        target_dir = (
            self.settings.keys_dir
            if self.settings.has_instance()
            else (self.settings._require_platform_dir())
        )
        golden_keys = setup_golden_keys(
            self.settings.xtest_root,
            target_dir,
        )

        if not golden_keys:
            return

        # Load config, append golden keys, and save
        data = load_yaml(config_path)

        # Add keys to cryptoProvider.standard.keys
        append_to_list(data, "server.cryptoProvider.standard.keys", golden_keys)

        # Add keyring entries for legacy decryption
        keyring_entries = get_golden_keyring_entries()
        append_to_list(data, "services.kas.keyring", keyring_entries)

        save_yaml(config_path, data)

    def start(self) -> bool:
        """Start the platform service."""
        # Ensure directories exist
        self.settings.ensure_directories()

        # Kill any existing process on the port
        kill_process_on_port(self.port)

        # Generate config
        config_path = self._generate_config()

        # Build the command — pinned binary when an instance is loaded,
        # legacy `go run ./service` otherwise.
        instance_paths = self._instance_dist_paths()
        if instance_paths is not None:
            binary, worktree = instance_paths
            cmd = [str(binary), "start", "--config-file", str(config_path)]
            cwd = worktree
        else:
            cmd = ["go", "run", "./service", "start", "--config-file", str(config_path)]
            cwd = self.settings._require_platform_dir()

        # Start the process
        log_file = self.settings.logs_dir / "platform.log"

        self._process = self._process_manager.start(
            name=self.name,
            cmd=cmd,
            cwd=cwd,
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
        from otdf_local.config.settings import get_settings

        settings = get_settings()

    return PlatformService(settings, _process_manager)
