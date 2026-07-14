"""Multi-strategy ERS platform instance.

Runs a second `platform` process alongside the default one, configured to
resolve entities via the multi-strategy ERS with a SQL provider pointed at
the ers-postgres container. Exists so xtest can exercise the multi-strategy
code path against the same shared policy DB without disturbing the default
Keycloak-ERS platform.

The pattern mirrors KASService: always up on `otdf-local up`, dedicated
port, log file, and health check. Tests that don't reference the ers-ms
fixtures are unaffected.
"""

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


class PlatformERSMultiStrategyService(Service):
    """Second platform instance running in multi-strategy ERS mode."""

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
        return "platform-ers-ms"

    @property
    def port(self) -> int:
        return Ports.PLATFORM_ERS_MS

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.SUBPROCESS

    @property
    def health_url(self) -> str:
        return f"http://localhost:{self.port}/healthz"

    def _generate_config(self) -> Path:
        template_path = self.settings.platform_ers_ms_template_config
        if not template_path.exists():
            raise FileNotFoundError(
                f"Multi-strategy platform template not found at {template_path}. "
                "Expected xtest/platform-configs/opentdf-multistrategy.yaml."
            )

        features = PlatformFeatures.detect(self.settings.platform_dir)
        logger_output = "stderr" if features.supports("logger_stderr") else "stdout"

        # Sync the primary platform's root_key so both KAS instances can
        # unwrap each other's wrapped DEKs. Mirrors KASService's approach.
        primary_config = load_yaml(self.settings.platform_config)
        root_key = get_nested(primary_config, "services.kas.root_key", "")

        updates = {
            "logger.level": "debug",
            "logger.type": "json",
            "logger.output": logger_output,
            "server.port": self.port,
            "services.kas.registered_kas_uri": f"http://localhost:{self.port}",
            "services.kas.root_key": root_key,
        }
        dest = self.settings.platform_ers_ms_config
        copy_yaml_with_updates(template_path, dest, updates)
        return dest

    def start(self) -> bool:
        self.settings.ensure_directories()
        kill_process_on_port(self.port)

        config_path = self._generate_config()

        cmd = [
            "go",
            "run",
            "./service",
            "start",
            "--config-file",
            str(config_path),
        ]
        log_file = self.settings.platform_ers_ms_log_path

        self._process = self._process_manager.start(
            name=self.name,
            cmd=cmd,
            cwd=self.settings.platform_dir,
            log_file=log_file,
            env={"OPENTDF_LOG_LEVEL": "info"},
        )
        return self._process is not None

    def stop(self) -> bool:
        if self._process:
            self._process.stop()
            self._process = None
        kill_process_on_port(self.port)
        return True

    def is_running(self) -> bool:
        if self._process and self._process.running:
            return True
        return check_port("localhost", self.port)

    def is_healthy(self) -> bool | None:
        if not self.is_running():
            return None
        return check_http_health(self.health_url)

    def get_info(self) -> ServiceInfo:
        info = super().get_info()
        if self._process:
            info.pid = self._process.pid
        return info


_ers_ms_process_manager: ProcessManager | None = None


def get_platform_ers_ms_service(
    settings: Settings | None = None,
) -> PlatformERSMultiStrategyService:
    """Get a PlatformERSMultiStrategyService with shared process manager."""
    global _ers_ms_process_manager
    if _ers_ms_process_manager is None:
        _ers_ms_process_manager = ProcessManager()

    if settings is None:
        from otdf_local.config.settings import get_settings

        settings = get_settings()

    return PlatformERSMultiStrategyService(settings, _ers_ms_process_manager)
