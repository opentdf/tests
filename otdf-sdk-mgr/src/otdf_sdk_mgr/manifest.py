"""Installation manifest for ordered SDK builds.

Supports ordered artifact requests with mutable ref resolution, installation
tracking, and explicit preparation status. Used by benchmarks to record exactly
what was installed, preserving request order and commit identity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

# Manifest schema version. Bump when changing the JSON structure.
MANIFEST_VERSION = "v1alpha1"


class PreparationStatus(str, Enum):
    """Overall status of the installation preparation."""

    SUCCESS = "success"
    NEUTRAL = "neutral"  # all requests resolved to one commit
    PARTIAL = "partial"  # some installs failed
    FAILED = "failed"  # resolution or installation error


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """Immutable identity of one installed SDK build."""

    requested_alias: str  # e.g., "go@main", "go@v0.29.0"
    repository: str  # git remote URL
    commit_sha: str  # immutable commit
    installed_tag: str  # filesystem-safe tag under dist/
    installed_path: str  # absolute path to dist directory
    installation_method: Literal["release", "source"]
    build_settings: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "requested_alias": self.requested_alias,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "installed_tag": self.installed_tag,
            "installed_path": self.installed_path,
            "installation_method": self.installation_method,
            "build_settings": dict(self.build_settings),
        }

    @staticmethod
    def from_dict(d: dict[str, object]) -> ArtifactIdentity:
        """Deserialize from a dict."""
        return ArtifactIdentity(
            requested_alias=str(d["requested_alias"]),
            repository=str(d["repository"]),
            commit_sha=str(d["commit_sha"]),
            installed_tag=str(d["installed_tag"]),
            installed_path=str(d["installed_path"]),
            installation_method=str(d["installation_method"]),  # type: ignore
            build_settings=dict(d.get("build_settings", {})),  # type: ignore
        )


@dataclass
class InstallationManifest:
    """Complete installation manifest for a benchmark run.

    Records the platform pin, provisioning CLI pin, and ordered SDK arms, along
    with the preparation status and the reason for it.

    `status_message` explains any status, not just the failing ones: NEUTRAL is
    the spec's explicit not-an-error outcome, and the message is where the
    commit everything collapsed onto gets reported.
    """

    schema_version: str = MANIFEST_VERSION
    platform: ArtifactIdentity | None = None
    otdfctl: ArtifactIdentity | None = None
    sdk_arms: list[ArtifactIdentity] = field(default_factory=list)
    status: PreparationStatus = PreparationStatus.SUCCESS
    status_message: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "schema_version": self.schema_version,
            "platform": self.platform.to_dict() if self.platform else None,
            "otdfctl": self.otdfctl.to_dict() if self.otdfctl else None,
            "sdk_arms": [arm.to_dict() for arm in self.sdk_arms],
            "status": self.status.value,
            "status_message": self.status_message,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def from_dict(d: dict[str, object]) -> InstallationManifest:
        """Deserialize from a dict."""
        platform_dict = d.get("platform")
        otdfctl_dict = d.get("otdfctl")
        sdk_arms_list = d.get("sdk_arms", [])

        return InstallationManifest(
            schema_version=str(d.get("schema_version", MANIFEST_VERSION)),
            platform=ArtifactIdentity.from_dict(platform_dict) if platform_dict else None,  # type: ignore
            otdfctl=ArtifactIdentity.from_dict(otdfctl_dict) if otdfctl_dict else None,  # type: ignore
            sdk_arms=[ArtifactIdentity.from_dict(arm) for arm in sdk_arms_list],  # type: ignore
            status=PreparationStatus(d.get("status", "success")),
            status_message=str(d.get("status_message") or ""),
            metadata=dict(d.get("metadata", {})),  # type: ignore
        )

    def write(self, path: Path) -> None:
        """Write manifest to JSON file."""
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @staticmethod
    def read(path: Path) -> InstallationManifest:
        """Read manifest from JSON file."""
        return InstallationManifest.from_dict(json.loads(path.read_text()))

    def is_same_commit(self) -> bool:
        """True if all SDK arms resolved to the same commit."""
        if not self.sdk_arms:
            return False
        commits = {arm.commit_sha for arm in self.sdk_arms}
        return len(commits) == 1


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    """One resolved artifact request: alias → commit + installation intent."""

    requested_alias: str
    repository: str
    commit_sha: str
    tag: str  # filesystem-safe tag
    is_head: bool  # True for branches/PRs (build from source)
    is_release: bool  # True for release tags
    build_settings: dict[str, str] = field(default_factory=dict)

    @property
    def installation_method(self) -> Literal["release", "source"]:
        """Installation method based on whether this is a head or release."""
        return "release" if self.is_release else "source"


def dist_slug_for(artifact: ResolvedArtifact) -> str:
    """The `dist/` directory name this artifact will actually occupy.

    The two installation methods derive their slug from different inputs, and
    they have to, so this is the one place that knows which:

    * A release is named for its resolved tag. The requested alias may be
      mutable (`latest`), and the tag is not.
    * A source build is named for the *expanded requested ref*, because that is
      what `cmd_tip` uses (`installers.py`, `VERSIONS=<slug>`). Resolution does
      not round-trip here: `pr:123` resolves to the tag `pull-123` but builds
      into `refs--pull--123--head`, so slugging a source build from its tag
      points at a directory that never gets created.
    """
    from otdf_sdk_mgr.refs import dist_slug, expand_pr_shorthand

    if artifact.is_release:
        return dist_slug(artifact.tag)
    return dist_slug(expand_pr_shorthand(artifact.requested_alias))


def check_collision(resolved: list[ResolvedArtifact]) -> str | None:
    """Check for colliding installed paths.

    Returns an error message if two artifacts at *different commits* would
    install to the same dist directory (after slug normalization), or None.

    Buckets on the directory each artifact will actually occupy, not the raw
    tag, to catch cases like "otdfctl/v0.24.0" and "v0.24.0" which both slug to
    "v0.24.0" once the namespace prefix is stripped.

    Sharing a directory only matters when the contents would disagree. Two
    aliases at one commit produce the same build, so they pass: for measured
    arms that case is the neutral outcome, and for a provisioning pin naming
    an arm's commit it is the ordinary way to say "provision with the build I
    am already measuring".
    """
    slug_to_commits: dict[str, dict[str, list[str]]] = {}
    for artifact in resolved:
        by_commit = slug_to_commits.setdefault(dist_slug_for(artifact), {})
        by_commit.setdefault(artifact.commit_sha, []).append(artifact.requested_alias)

    messages = [
        f"{slug}: "
        + "; ".join(
            f"{', '.join(aliases)} at {commit[:8]}" for commit, aliases in sorted(by_commit.items())
        )
        for slug, by_commit in sorted(slug_to_commits.items())
        if len(by_commit) > 1
    ]
    if messages:
        return "Colliding installed paths detected:\n  " + "\n  ".join(messages)
    return None


def is_neutral_preparation(resolved: list[ResolvedArtifact]) -> bool:
    """True if all distinct requested aliases resolved to one commit.

    This is not an error — it's an explicit neutral outcome that should be
    produced before builds or service startup.
    """
    if len(resolved) < 2:
        return False
    commits = {artifact.commit_sha for artifact in resolved}
    return len(commits) == 1
