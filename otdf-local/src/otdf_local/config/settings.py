"""Pydantic settings for otdf_local configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from otdf_local.config.ports import Ports


def _pyproject_has_name(path: Path, project_name: str) -> bool:
    """Return True if path/pyproject.toml contains the given project name."""
    pyproject = path / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        return f'name = "{project_name}"' in pyproject.read_text()
    except OSError:
        return False


def _find_project_root(project_name: str, start: Path) -> Path | None:
    """Walk up from start looking for a directory whose pyproject.toml has the given name.

    Checks both the current directory and immediate subdirectories at each level,
    so sibling projects (e.g. xtest alongside otdf-local) are discovered correctly.
    """
    current = start.resolve()
    while current != current.parent:
        if _pyproject_has_name(current, project_name):
            return current
        # Check immediate subdirectories (finds sibling projects via common parent)
        try:
            for child in current.iterdir():
                if child.is_dir() and _pyproject_has_name(child, project_name):
                    return child
        except OSError:
            pass
        current = current.parent
    return None


def _find_xtest_root() -> Path:
    """Find the xtest root directory by locating pyproject.toml with name = 'xtest'."""
    found = _find_project_root("xtest", Path(__file__))
    if found is not None:
        return found
    # Fallback: assume xtest is a sibling of otdf-local in the same repo
    # __file__ is at otdf-local/src/otdf_local/config/settings.py (4 parents = otdf-local/)
    return Path(__file__).resolve().parent.parent.parent.parent.parent / "xtest"


def _find_platform_dir(xtest_root: Path) -> Path:
    """Find the platform directory by searching for a sibling of an ancestor.

    Searches for a 'platform' directory in:
    1. Ancestor siblings (for local development checkouts)
    2. The otdf-sdk-mgr managed location (xtest/sdk/platform/src/main)
    3. Last resort: attempts to checkout 'main' via otdf-sdk-mgr

    Raises:
        FileNotFoundError: If platform directory is not found with expected shape.
    """
    # 1. Search for sibling 'platform' checkouts
    current = xtest_root
    while current != current.parent:
        # Check siblings at this level
        platform_candidate = current.parent / "platform"
        if platform_candidate.exists() and platform_candidate.is_dir():
            # Verify it has the expected shape
            has_compose = (platform_candidate / "docker-compose.yaml").exists()
            has_config = (platform_candidate / "opentdf-dev.yaml").exists() or (
                platform_candidate / "opentdf.yaml"
            ).exists()
            if has_compose and has_config:
                return platform_candidate
        current = current.parent

    # 2. Search in otdf-sdk-mgr managed location
    managed_main = xtest_root / "sdk" / "platform" / "src" / "main"
    if managed_main.exists() and managed_main.is_dir():
        if (managed_main / "docker-compose.yaml").exists() and (
            (managed_main / "opentdf-dev.yaml").exists()
            or (managed_main / "opentdf.yaml").exists()
        ):
            return managed_main

    # 3. Last resort: checkout 'main' via otdf-sdk-mgr
    sdk_mgr_dir = xtest_root.parent / "otdf-sdk-mgr"
    if sdk_mgr_dir.exists():
        import subprocess

        try:
            # We use plain print to avoid circular imports or dependency on rich here
            print(
                "Platform not found. Attempting to checkout 'main' via otdf-sdk-mgr..."
            )
            subprocess.check_call(
                [
                    "uv",
                    "run",
                    "--project",
                    str(sdk_mgr_dir),
                    "otdf-sdk-mgr",
                    "checkout",
                    "platform",
                    "main",
                ],
                cwd=sdk_mgr_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if managed_main.exists() and managed_main.is_dir():
                if (managed_main / "docker-compose.yaml").exists() and (
                    managed_main / "opentdf-dev.yaml"
                ).exists():
                    return managed_main
        except Exception:
            # Fall through to FileNotFoundError
            pass

    # If we get here, we didn't find it
    raise FileNotFoundError(
        f"Could not find platform directory with expected shape "
        f"(docker-compose.yaml and opentdf.yaml or opentdf-dev.yaml) searching from {xtest_root}"
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
    _platform_dir: Path | None = None

    @property
    def platform_dir(self) -> Path:
        """Platform directory path."""
        if self._platform_dir:
            return self._platform_dir
        return _find_platform_dir(self.xtest_root)

    @platform_dir.setter
    def platform_dir(self, value: Path) -> None:
        self._platform_dir = value

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
        return self.platform_dir / "opentdf.yaml"

    @property
    def platform_template_config(self) -> Path:
        """Platform config template path."""
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
        self.keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
