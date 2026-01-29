"""Pydantic settings for lmgmt configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lmgmt.config.ports import Ports


def _find_xtest_root() -> Path:
    """Find the xtest root directory by walking up from this file."""
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / "conftest.py").exists() and current.name == "xtest":
            return current
        # Also check if we're in the lmgmt package within xtest
        if (current / "lmgmt").exists() and (current.parent / "conftest.py").exists():
            return current.parent
        current = current.parent
    # Fallback to assuming we're in tests/xtest/lmgmt
    return Path(__file__).resolve().parent.parent.parent.parent.parent


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="LMGMT_",
        env_file=".env",
        extra="ignore",
    )

    # Directory paths - computed from xtest_root
    xtest_root: Path = Field(default_factory=_find_xtest_root)

    @property
    def platform_dir(self) -> Path:
        """Platform source directory."""
        return self.xtest_root.parent / "platform"

    @property
    def logs_dir(self) -> Path:
        """Logs directory."""
        return self.xtest_root / "logs"

    @property
    def keys_dir(self) -> Path:
        """Keys directory."""
        return self.xtest_root / "keys"

    @property
    def config_dir(self) -> Path:
        """Generated config files directory."""
        return self.xtest_root / "config"

    @property
    def platform_config(self) -> Path:
        """Platform config file path."""
        return self.platform_dir / "opentdf-dev.yaml"

    @property
    def kas_template_config(self) -> Path:
        """KAS config template path."""
        return self.platform_dir / "opentdf-kas-mode.yaml"

    @property
    def docker_compose_file(self) -> Path:
        """Docker compose file path."""
        return self.platform_dir / "docker-compose.yaml"

    # Service ports
    keycloak_port: int = Ports.KEYCLOAK
    postgres_port: int = Ports.POSTGRES
    platform_port: int = Ports.PLATFORM

    # URLs
    platform_url: Annotated[str, Field(default="http://localhost:8080")]
    keycloak_url: Annotated[str, Field(default="http://localhost:8888")]

    # Timeouts (seconds)
    health_timeout: int = 60
    startup_timeout: int = 120

    # Log level
    log_level: str = "info"

    def get_kas_port(self, name: str) -> int:
        """Get port for a KAS instance."""
        return Ports.get_kas_port(name)

    def get_kas_config_path(self, name: str) -> Path:
        """Get config file path for a KAS instance."""
        return self.config_dir / f"kas-{name}.yaml"

    def get_kas_log_path(self, name: str) -> Path:
        """Get log file path for a KAS instance."""
        return self.logs_dir / f"kas-{name}.log"

    def ensure_directories(self) -> None:
        """Create all required directories."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.keys_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
