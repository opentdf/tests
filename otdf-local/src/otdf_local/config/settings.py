"""Pydantic settings for otdf_local configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from otdf_local.config.ports import Ports


def _find_project_root(project_name: str, start: Path) -> Path | None:
    """Walk up from start looking for a pyproject.toml with the given project name."""
    current = start.resolve()
    while current != current.parent:
        pyproject = current / "pyproject.toml"
        if pyproject.is_file():
            try:
                content = pyproject.read_text()
                if f'name = "{project_name}"' in content:
                    return current
            except OSError:
                pass
        current = current.parent
    return None


def _find_xtest_root() -> Path:
    """Find the xtest root directory by locating pyproject.toml with name = 'xtest'."""
    found = _find_project_root("xtest", Path(__file__))
    if found is not None:
        return found
    # Fallback to assuming we're in tests/otdf-local
    return Path(__file__).resolve().parent.parent.parent.parent


def _find_platform_dir(xtest_root: Path) -> Path:
    """Find the platform directory by searching for a sibling of an ancestor.

    Searches up the directory tree from xtest_root looking for a 'platform' directory
    that has the expected shape (contains docker-compose.yaml and opentdf-dev.yaml).

    Raises:
        FileNotFoundError: If platform directory is not found with expected shape.
    """
    # Start from xtest_root and walk up
    current = xtest_root
    while current != current.parent:
        # Check siblings at this level
        platform_candidate = current.parent / "platform"
        if platform_candidate.exists() and platform_candidate.is_dir():
            # Verify it has the expected shape
            has_compose = (platform_candidate / "docker-compose.yaml").exists()
            has_config = (platform_candidate / "opentdf-dev.yaml").exists()
            if has_compose and has_config:
                return platform_candidate
        current = current.parent

    # If we get here, we didn't find it
    raise FileNotFoundError(
        f"Could not find platform directory with expected shape "
        f"(docker-compose.yaml and opentdf-dev.yaml) searching from {xtest_root}"
    )


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="OTDF_LOCAL_",
        env_file=".env",
        extra="ignore",
    )

    # Directory paths - computed from xtest_root
    xtest_root: Path = Field(default_factory=_find_xtest_root)
    platform_dir: Path = Field(
        default_factory=lambda: _find_platform_dir(_find_xtest_root())
    )

    @property
    def logs_dir(self) -> Path:
        """Logs directory."""
        return self.xtest_root / "tmp" / "logs"

    @property
    def keys_dir(self) -> Path:
        """Keys directory."""
        return self.xtest_root / "tmp" / "keys"

    @property
    def config_dir(self) -> Path:
        """Generated config files directory."""
        return self.xtest_root / "tmp" / "config"

    @property
    def platform_config(self) -> Path:
        """Platform config file path."""
        return self.platform_dir / "opentdf-dev.yaml"

    @property
    def platform_template_config(self) -> Path:
        """Platform config template path."""
        return self.platform_dir / "opentdf.yaml"

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
    platform_url: str = "http://localhost:8080"
    keycloak_url: str = "http://localhost:8888"

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
