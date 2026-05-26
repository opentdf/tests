"""Pydantic settings for otdf_local configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from otdf_local.config.ports import Ports

DEFAULT_INSTANCE_NAME = "default"


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


def _find_platform_dir_optional(xtest_root: Path) -> Path | None:
    """Same as `_find_platform_dir` but returns None instead of raising.

    Multi-instance mode looks up platform binaries via `otdf-sdk-mgr` instead of
    a sibling repo, so a missing sibling `platform/` is no longer fatal — only
    the legacy single-instance path needs it.
    """
    try:
        return _find_platform_dir(xtest_root)
    except FileNotFoundError:
        return None


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="OTDF_LOCAL_",
        env_file=".env",
        extra="ignore",
    )

    # Directory paths - computed from xtest_root
    xtest_root: Path = Field(default_factory=_find_xtest_root)
    platform_dir: Path | None = Field(
        default_factory=lambda: _find_platform_dir_optional(_find_xtest_root())
    )

    # Multi-instance: which named instance under `tests/instances/<name>/` to use.
    instance_name: str = DEFAULT_INSTANCE_NAME

    @property
    def tests_root(self) -> Path:
        """Repo root that holds `xtest/`, `instances/`, `otdf-local/`, etc."""
        return self.xtest_root.parent

    @property
    def instances_root(self) -> Path:
        """Top-level `tests/instances/` directory (created on demand)."""
        return self.tests_root / "instances"

    @property
    def instance_dir(self) -> Path:
        """Per-instance directory: `tests/instances/<instance_name>/`."""
        return self.instances_root / self.instance_name

    @property
    def instance_yaml(self) -> Path:
        """Path to the per-instance manifest."""
        return self.instance_dir / "instance.yaml"

    def has_instance(self) -> bool:
        """Return True if `instance.yaml` exists for the selected instance."""
        return self.instance_yaml.is_file()

    def platform_binary_for(self, dist: str) -> Path:
        """Resolve a platform dist version to its built `service` binary path.

        Looks under `xtest/platform/dist/<dist>/service` (managed by
        `otdf-sdk-mgr install platform:<version>`). The binary is not required
        to exist at the time of the call — callers should check existence and
        surface a clear error suggesting `otdf-sdk-mgr install` when missing.
        """
        from otdf_sdk_mgr.platform_installer import get_platform_dir

        return get_platform_dir() / "dist" / dist / "service"

    @property
    def logs_dir(self) -> Path:
        """Logs directory. Per-instance when an instance is selected, falls back to legacy."""
        if self.has_instance():
            return self.instance_dir / "logs"
        return self.xtest_root / "tmp" / "logs"

    @property
    def keys_dir(self) -> Path:
        """Keys directory. Per-instance when an instance is selected, falls back to legacy."""
        if self.has_instance():
            return self.instance_dir / "keys"
        return self.xtest_root / "tmp" / "keys"

    @property
    def config_dir(self) -> Path:
        """Generated config files directory. Per-instance when present."""
        if self.has_instance():
            return self.instance_dir
        return self.xtest_root / "tmp" / "config"

    def _require_platform_dir(self) -> Path:
        if self.platform_dir is None:
            raise FileNotFoundError(
                "No sibling platform/ directory found. Either check out opentdf/platform as "
                "a sibling of tests/, or run `otdf-sdk-mgr install platform:<version>` and "
                "select an instance with `otdf-local --instance <name>`."
            )
        return self.platform_dir

    @property
    def platform_config(self) -> Path:
        """Platform config file. Per-instance when present, else legacy template."""
        if self.has_instance():
            return self.instance_dir / "opentdf.yaml"
        return self._require_platform_dir() / "opentdf-dev.yaml"

    @property
    def platform_template_config(self) -> Path:
        """Platform config template path (legacy mode)."""
        return self._require_platform_dir() / "opentdf.yaml"

    @property
    def kas_template_config(self) -> Path:
        """KAS config template path (legacy mode)."""
        return self._require_platform_dir() / "opentdf-kas-mode.yaml"

    @property
    def platform_source_dir(self) -> Path | None:
        """Return the platform source directory for go run / provisioning.

        Legacy mode: the sibling platform/ checkout.
        Instance + source build: the platform src worktree (xtest/platform/src/<ref>/).
        """
        if self.platform_dir is not None:
            return self.platform_dir
        instance = self.load_instance()
        if instance is not None and instance.platform.source is not None:
            from otdf_sdk_mgr.platform_installer import get_platform_dir

            safe_ref = instance.platform.source.ref.replace("/", "--")
            src_worktree = get_platform_dir() / "src" / safe_ref
            if src_worktree.exists():
                return src_worktree
        return None

    @property
    def docker_compose_file(self) -> Path:
        """Docker compose file path."""
        src = self.platform_source_dir
        if src is not None:
            compose = src / "docker-compose.yaml"
            if compose.exists():
                return compose
        return self._require_platform_dir() / "docker-compose.yaml"

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
        """Get port for a KAS instance.

        When an `instance.yaml` exists with a `ports.base`, computes ports
        relative to it so multiple instances on different bases don't clash.
        """
        instance = self.load_instance()
        if instance is not None:
            return Ports.get_kas_port(name, base=instance.ports.base)
        return Ports.get_kas_port(name)

    def load_instance(self):
        """Load the per-instance manifest, or return None when not present."""
        if not self.has_instance():
            return None
        from otdf_sdk_mgr.schema import load_instance as _load

        return _load(self.instance_yaml)

    def get_kas_config_path(self, name: str) -> Path:
        """Get config file path for a KAS instance."""
        if self.has_instance():
            return self.instance_dir / "kas" / name / "opentdf.yaml"
        return self.config_dir / f"kas-{name}.yaml"

    def get_kas_log_path(self, name: str) -> Path:
        """Get log file path for a KAS instance."""
        return self.logs_dir / f"kas-{name}.log"

    def ensure_directories(self) -> None:
        """Create all required directories."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.keys_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.has_instance():
            (self.instance_dir / "kas").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
