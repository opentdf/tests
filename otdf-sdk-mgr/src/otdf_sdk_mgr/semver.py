"""Semantic version parsing and utilities."""

from __future__ import annotations

import re

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([^+]+))?(?:\+(.+))?$")


def parse_semver(version: str) -> tuple[int, int, int, str | None] | None:
    """Parse a semver string into (major, minor, patch, pre) or None."""
    m = SEMVER_RE.match(version)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)


def is_stable(version: str) -> bool:
    """Return True if version has no pre-release suffix."""
    parsed = parse_semver(version)
    if parsed is None:
        return False
    return parsed[3] is None


def semver_sort_key(version: str) -> tuple[int, int, int, int, str]:
    """Sort key for semver strings. Stable versions sort after pre-release."""
    parsed = parse_semver(version)
    if parsed is None:
        return (0, 0, 0, 0, version)
    major, minor, patch, pre = parsed
    return (major, minor, patch, 0 if pre else 1, pre or "")


def normalize_version(version: str) -> str:
    """Normalize version string to v-prefixed form."""
    v = version.strip().lstrip("v")
    return f"v{v}"
