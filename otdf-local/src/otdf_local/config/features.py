"""Platform feature detection based on version."""

import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

FeatureType = Literal[
    "assertions",
    "assertion_verification",
    "autoconfigure",
    "better-messages-2024",
    "bulk_rewrap",
    "connectrpc",
    "ecwrap",
    "hexless",
    "hexaflexible",
    "kasallowlist",
    "key_management",
    "ns_grants",
    "obligations",
    "logger_stderr",  # Support for logger.output: stderr
]

_VERSION_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9a-zA-Z.-]+))?(?:\+([0-9a-zA-Z.-]+))?$"
)


class PlatformFeatures(BaseModel):
    """Platform feature detection based on version."""

    version: str
    semver: tuple[int, int, int]
    features: set[FeatureType]

    @classmethod
    def detect(cls, platform_dir: Path) -> "PlatformFeatures":
        """Detect platform features by querying the version."""
        version = _get_platform_version(platform_dir)
        semver = _parse_semver(version)
        features = _compute_features(semver)
        return cls(version=version, semver=semver, features=features)

    def supports(self, feature: FeatureType) -> bool:
        """Check if a feature is supported."""
        return feature in self.features


def _get_platform_version(platform_dir: Path) -> str:
    """Get the platform version by running 'go run ./service version'."""
    try:
        result = subprocess.run(
            ["go", "run", "./service", "version"],
            cwd=platform_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        pass

    # Default version if detection fails
    return "0.9.0"


def _parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch) tuple."""
    match = _VERSION_RE.match(version)
    if not match:
        # Default to 0.9.0 if parsing fails
        return (0, 9, 0)

    major, minor, patch, _, _ = match.groups()
    return (int(major), int(minor), int(patch))


def _compute_features(semver: tuple[int, int, int]) -> set[FeatureType]:
    """Compute the set of supported features based on semver."""
    features: set[FeatureType] = {
        "assertions",
        "assertion_verification",
        "autoconfigure",
        "better-messages-2024",
    }

    # EC wrapping (announced in 0.4.39 but correct salt in 0.4.40)
    if semver >= (0, 4, 40):
        features.add("ecwrap")

    # Hexless format support
    if semver >= (0, 4, 39):
        features.add("hexless")
        features.add("hexaflexible")

    # Namespace grants
    if semver >= (0, 4, 19):
        features.add("ns_grants")

    # Connect RPC support
    if semver >= (0, 4, 28):
        features.add("connectrpc")

    # Key management
    if semver >= (0, 6, 0):
        features.add("key_management")

    # Obligations support (service v0.11.0)
    if semver >= (0, 11, 0):
        features.add("obligations")

    # Logger stderr output support (added after v0.9.0)
    # v0.9.0 only supports stdout
    if semver >= (0, 10, 0):
        features.add("logger_stderr")

    return features


@lru_cache
def get_platform_features(platform_dir: Path) -> PlatformFeatures:
    """Get cached platform features for a directory."""
    return PlatformFeatures.detect(platform_dir)
