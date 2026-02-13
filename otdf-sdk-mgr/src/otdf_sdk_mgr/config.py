"""Constants and path discovery for SDK management."""

from __future__ import annotations

from pathlib import Path

# Discover the tests/ directory by walking up from this package
# In CI, the checkout may be named otdftests/ instead of tests/
# Look for the xtest/sdk structure to identify the root
_PACKAGE_DIR = Path(__file__).resolve().parent
_TESTS_DIR = _PACKAGE_DIR
while _TESTS_DIR != _TESTS_DIR.parent:
    if (_TESTS_DIR / "xtest" / "sdk").exists():
        break
    _TESTS_DIR = _TESTS_DIR.parent

SDK_DIR = _TESTS_DIR / "xtest" / "sdk"
if not SDK_DIR.exists():
    raise RuntimeError(
        f"Could not locate xtest/sdk directory. "
        f"Started from {_PACKAGE_DIR}, walked up to {_TESTS_DIR}. "
        f"Expected to find xtest/sdk structure in repository root."
    )
GO_DIR = SDK_DIR / "go"
JS_DIR = SDK_DIR / "js"
JAVA_DIR = SDK_DIR / "java"
SCRIPTS_DIR = SDK_DIR / "scripts"

SDK_DIRS: dict[str, Path] = {
    "go": GO_DIR,
    "js": JS_DIR,
    "java": JAVA_DIR,
}

# Git repository URLs (unified from resolve-version.py sdk_urls + list-versions.py sdk_git_urls)
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

GO_INSTALL_PREFIX = "go run github.com/opentdf/otdfctl"

LTS_VERSIONS: dict[str, str] = {
    "go": "0.24.0",
    "java": "0.9.0",
    "js": "0.4.0",
    "platform": "0.9.0",
}

# Java SDK version -> compatible platform protocol branch
# Must stay in sync with resolve-version.py lookup_additional_options
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

ALL_SDKS = ["go", "js", "java"]
