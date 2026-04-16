"""Constants and path discovery for SDK management."""

from __future__ import annotations

import os
from pathlib import Path


def _find_sdk_dir() -> Path | None:
    """Walk up from this package directory to find xtest/sdk."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "xtest" / "sdk").exists():
            return current / "xtest" / "sdk"
        current = current.parent
    return None


def get_sdk_dir() -> Path:
    """Return the SDK directory.

    Checks OTDF_SDK_DIR env var first, then walks up the directory tree
    to find xtest/sdk.  Raises RuntimeError if not found.
    """
    env_dir = os.environ.get("OTDF_SDK_DIR")
    if env_dir:
        return Path(env_dir)
    found = _find_sdk_dir()
    if found is None:
        pkg_dir = Path(__file__).resolve().parent
        raise RuntimeError(
            f"Could not locate xtest/sdk directory. "
            f"Started from {pkg_dir}, walked up to filesystem root. "
            f"Set OTDF_SDK_DIR env var to override."
        )
    return found


def get_sdk_dirs() -> dict[str, Path]:
    """Return per-SDK directories keyed by SDK name."""
    sdk_dir = get_sdk_dir()
    return {
        "go": sdk_dir / "go",
        "js": sdk_dir / "js",
        "java": sdk_dir / "java",
    }


# Git repository URLs
SDK_GIT_URLS: dict[str, str] = {
    "go": "https://github.com/opentdf/otdfctl.git",
    "java": "https://github.com/opentdf/java-sdk.git",
    "js": "https://github.com/opentdf/web-sdk.git",
    "platform": "https://github.com/opentdf/platform.git",
}

SDK_NPM_PACKAGES: dict[str, str] = {
    "js": "@opentdf/ctl",
}

SDK_MAVEN_COORDS: dict[str, dict[str, str]] = {
    "java": {
        "group": "io.opentdf.platform",
        "artifact": "sdk",
        "base_url": "https://repo1.maven.org/maven2/io/opentdf/platform/sdk",
    },
}

SDK_GITHUB_REPOS: dict[str, str] = {
    "java": "opentdf/java-sdk",
}

GO_INSTALL_PREFIX_STANDALONE = "go run github.com/opentdf/otdfctl"
GO_INSTALL_PREFIX_PLATFORM = "go run github.com/opentdf/platform/otdfctl"

GO_MODULE_PATH = "github.com/opentdf/otdfctl"
GO_MODULE_PATH_PLATFORM = "github.com/opentdf/platform/otdfctl"

LTS_VERSIONS: dict[str, str] = {
    "go": "0.24.0",
    "java": "0.9.0",
    "js": "0.4.0",
    "platform": "0.9.0",
}

# Java SDK version -> compatible platform protocol branch
# Must stay in sync with otdf-sdk-mgr versions resolve's lookup_additional_options
JAVA_PLATFORM_BRANCH_MAP: dict[str, str] = {
    "0.7.8": "protocol/go/v0.2.29",
    "0.7.7": "protocol/go/v0.2.29",
    "0.7.6": "protocol/go/v0.2.25",
    "0.7.5": "protocol/go/v0.2.18",
    "0.7.4": "protocol/go/v0.2.18",
    "0.7.3": "protocol/go/v0.2.17",
    "0.7.2": "protocol/go/v0.2.17",
    "0.6.1": "protocol/go/v0.2.14",
    "0.6.0": "protocol/go/v0.2.14",
    "0.5.0": "protocol/go/v0.2.13",
    "0.4.0": "protocol/go/v0.2.10",
    "0.3.0": "protocol/go/v0.2.10",
    "0.2.0": "protocol/go/v0.2.10",
    "0.1.0": "protocol/go/v0.2.3",
}

# Bare repo names per SDK (used by checkout)
SDK_BARE_REPOS: dict[str, str] = {
    "go": "otdfctl.git",
    "java": "java-sdk.git",
    "js": "web-sdk.git",
}

# Tag infixes for monorepo tag resolution
SDK_TAG_INFIXES: dict[str, str] = {
    "js": "sdk",
    "platform": "service",
}

# When resolving go versions from the platform repo, use "otdfctl" infix
# (tags are otdfctl/v0.X.Y in the platform monorepo)
SDK_TAG_INFIXES_PLATFORM_GO = "otdfctl"


def go_git_url(source: str | None = None) -> str:
    """Return the git URL for Go SDK resolution based on source.

    Args:
        source: "platform" to use the platform monorepo, None/"standalone" for the
                standalone otdfctl repo.
    """
    if source == "platform":
        return SDK_GIT_URLS["platform"]
    return SDK_GIT_URLS["go"]


def go_tag_infix(source: str | None = None) -> str | None:
    """Return the tag infix for Go SDK resolution based on source."""
    if source == "platform":
        return SDK_TAG_INFIXES_PLATFORM_GO
    return None


def go_install_prefix(source: str | None = None) -> str:
    """Return the go install/run prefix based on source."""
    if source == "platform":
        return GO_INSTALL_PREFIX_PLATFORM
    return GO_INSTALL_PREFIX_STANDALONE


_VALID_GO_SOURCES = {None, "platform"}


def go_module_path(source: str | None = None) -> str:
    """Return the Go module path based on source."""
    if source not in _VALID_GO_SOURCES:
        raise ValueError(f"Invalid Go source {source!r}; expected one of {_VALID_GO_SOURCES}")
    if source == "platform":
        return GO_MODULE_PATH_PLATFORM
    return GO_MODULE_PATH


ALL_SDKS = ["go", "js", "java"]
