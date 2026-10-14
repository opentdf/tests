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


def _has_platform_shape(candidate: Path) -> bool:
    """True if `candidate` has `docker-compose.yaml` (docker deps) and
    `opentdf-dev.yaml` (committed config, which seeds the template)."""
    return (
        candidate.is_dir()
        and (candidate / "docker-compose.yaml").is_file()
        and (candidate / "opentdf-dev.yaml").is_file()
    )


# `otdf-sdk-mgr install scripts` checks out platform `main` here too, as
# `scripts--<branch>`; it has platform shape but is not an installed platform.
_HELPER_SCRIPTS_PREFIX = "scripts--"


def _installed_platform_worktrees(xtest_root: Path) -> list[Path]:
    """Platform worktrees `otdf-sdk-mgr` installed under `xtest/platform/src/`.

    One per ref, named by `ref_slug` (e.g. `main`, `service--v0.9.0`), beside
    a bare `platform.git` that the shape check skips.
    """
    src_root = xtest_root / "platform" / "src"
    if not src_root.is_dir():
        return []
    return sorted(
        (
            c
            for c in src_root.iterdir()
            if not c.name.startswith(_HELPER_SCRIPTS_PREFIX) and _has_platform_shape(c)
        ),
        key=lambda p: p.name,
    )


def _find_platform_dir(xtest_root: Path) -> Path:
    """Find a startable platform source tree, in order of preference:

    1. `platform/` beside `xtest/` (a hand-cloned checkout).
    2. The single worktree under `xtest/platform/src/`, as installed by
       `otdf-sdk-mgr install tip|release platform`.
    3. `platform/` beside a further ancestor (e.g. a multi-repo workspace).

    `OTDF_LOCAL_PLATFORM_DIR` overrides all of these.

    Raises:
        FileNotFoundError: if nothing startable is found, or if several
            worktrees are installed and none is preferred.
    """
    sibling = xtest_root.parent / "platform"
    if _has_platform_shape(sibling):
        return sibling

    installed = _installed_platform_worktrees(xtest_root)
    if len(installed) == 1:
        return installed[0]
    if installed:
        names = ", ".join(p.name for p in installed)
        raise FileNotFoundError(
            f"Multiple platform refs installed under {xtest_root / 'platform' / 'src'}: "
            f"{names}. Set OTDF_LOCAL_PLATFORM_DIR to the one to run."
        )

    current = xtest_root.parent
    while current != current.parent:
        candidate = current.parent / "platform"
        if _has_platform_shape(candidate):
            return candidate
        current = current.parent

    raise FileNotFoundError(
        f"Could not find platform directory with expected shape "
        f"(docker-compose.yaml and opentdf-dev.yaml) searching from {xtest_root}. "
        f"Install one with `otdf-sdk-mgr install tip platform`, or set "
        f"OTDF_LOCAL_PLATFORM_DIR."
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
        default_factory=lambda data: _find_platform_dir(data["xtest_root"])
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
        self.keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
