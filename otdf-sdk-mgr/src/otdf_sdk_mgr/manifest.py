"""Installation manifest for ordered SDK builds.

Supports ordered artifact requests with mutable ref resolution, installation
tracking, and explicit preparation status. Used by benchmarks to record exactly
what was installed, preserving request order and commit identity.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal, cast

# Manifest schema version. Bump when changing the JSON structure.
MANIFEST_VERSION = "v1alpha1"

InstallationMethod = Literal["release", "source"]
_INSTALLATION_METHODS: tuple[InstallationMethod, ...] = ("release", "source")


class PreparationStatus(str, Enum):
    """Overall status of the installation preparation.

    FAILED and PARTIAL split on whether the manifest records any completed
    install. Neither promises the dist/ tree is untouched: a failed install
    may have removed a stale directory, or left a half-built one.
    """

    SUCCESS = "success"
    NEUTRAL = "neutral"  # every arm resolved to one build; nothing installed
    PARTIAL = "partial"  # stopped after some, not all, installs completed
    FAILED = "failed"  # failed or aborted before any install completed


def short_commit(commit_sha: str | None) -> str:
    """A commit as a message names it."""
    return commit_sha[:8] if commit_sha else "an unknown commit"


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """Identity of one build the run recorded: a measured arm or a pin."""

    requested_alias: str  # as typed, e.g. "main", "v0.29.0", "pr:123"
    repository: str  # git remote URL
    # The full commit, or None when it is unknown: a js release found on npm
    # but not in git.
    commit_sha: str | None
    installed_tag: str  # the directory name under dist/
    # Absolute path to that directory, or None when this run installed
    # nothing there (the arms of a NEUTRAL run).
    installed_path: str | None
    installation_method: InstallationMethod
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
        """Deserialize from a dict.

        Raises:
            ValueError: if a field is missing or has the wrong type.
        """
        method = _str(d, "installation_method")
        if method not in _INSTALLATION_METHODS:
            raise ValueError(f"unknown installation_method {method!r}")
        return ArtifactIdentity(
            requested_alias=_str(d, "requested_alias"),
            repository=_str(d, "repository"),
            commit_sha=_nullable_str(d, "commit_sha"),
            installed_tag=_str(d, "installed_tag"),
            installed_path=_nullable_str(d, "installed_path"),
            installation_method=cast(InstallationMethod, method),
            build_settings=_str_dict(d, "build_settings"),
        )


@dataclass(kw_only=True)
class InstallationManifest:
    """Complete installation manifest for a benchmark run.

    Records the platform pin, provisioning CLI pin, and ordered SDK arms, along
    with the preparation status and the reason for it. `metadata["sdk"]` names
    the SDK the arms belong to: an arm records only its ref, and a go arm's
    repository is the platform's.

    `status` has no default: a manifest nobody explicitly marked as a success
    must not read as one.

    `status_message` says why for every status but a clean SUCCESS: what
    failed, or, for NEUTRAL, the build every arm collapsed onto. A SUCCESS
    whose arms repeat a build carries a warning naming them.
    """

    schema_version: str = MANIFEST_VERSION
    platform: ArtifactIdentity | None = None
    otdfctl: ArtifactIdentity | None = None
    sdk_arms: list[ArtifactIdentity] = field(default_factory=list)
    status: PreparationStatus
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
        """Deserialize from a dict.

        Raises:
            ValueError: if the schema version is not this one, the status is
                missing or unknown, or any field is missing or mistyped. None
                of them has a safe default.
        """
        schema_version = d.get("schema_version")
        if schema_version != MANIFEST_VERSION:
            raise ValueError(
                f"unsupported manifest schema_version {schema_version!r}; "
                f"expected {MANIFEST_VERSION!r}"
            )
        if "status" not in d:
            raise ValueError("manifest has no status")
        arms = d.get("sdk_arms", [])
        if not isinstance(arms, list):
            raise ValueError(f"manifest field 'sdk_arms' must be a list, not {arms!r}")

        return InstallationManifest(
            schema_version=MANIFEST_VERSION,
            platform=_optional_identity(d.get("platform"), "platform"),
            otdfctl=_optional_identity(d.get("otdfctl"), "otdfctl"),
            sdk_arms=[_identity(arm, f"sdk_arms[{i}]") for i, arm in enumerate(arms)],
            status=PreparationStatus(d["status"]),
            status_message=_str(d, "status_message"),
            metadata=_str_dict(d, "metadata"),
        )

    def write(self, path: Path) -> None:
        """Write manifest to JSON file, creating its directory.

        The write goes through a temporary file and a rename, so a write cut
        short (a full disk, Ctrl-C) leaves the previous file intact rather than
        truncated JSON.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        tmp.replace(path)

    @staticmethod
    def read(path: Path) -> InstallationManifest:
        """Read manifest from JSON file."""
        return InstallationManifest.from_dict(json.loads(path.read_text()))


def _str(d: dict[str, object], key: str) -> str:
    value = d.get(key)
    if not isinstance(value, str):
        raise ValueError(f"manifest field {key!r} must be a string, not {value!r}")
    return value


def _nullable_str(d: dict[str, object], key: str) -> str | None:
    """A field that must be present, but may be null.

    Not `str(d[key])`: that reads a JSON null back as the string "None".
    """
    if key not in d:
        raise ValueError(f"manifest field {key!r} is missing")
    value = d[key]
    if value is not None and not isinstance(value, str):
        raise ValueError(f"manifest field {key!r} must be a string or null, not {value!r}")
    return value


def _str_dict(d: dict[str, object], key: str) -> dict[str, str]:
    value = d.get(key) or {}
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ValueError(f"manifest field {key!r} must map strings to strings, not {value!r}")
    return cast(dict[str, str], dict(value))


def _identity(value: object, where: str) -> ArtifactIdentity:
    if not isinstance(value, dict):
        raise ValueError(f"manifest field {where!r} must be an object, not {value!r}")
    return ArtifactIdentity.from_dict(cast(dict[str, object], value))


def _optional_identity(value: object, where: str) -> ArtifactIdentity | None:
    return None if value is None else _identity(value, where)


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    """One resolved artifact request: alias → commit + installation intent."""

    requested_alias: str
    repository: str
    commit_sha: str | None  # None for a js release found on npm but not in git
    # The resolver's tag (`pull-123`, a bare npm `0.4.0`), not the dist
    # directory name; that is `dist_slug_for`.
    tag: str
    is_head: bool  # resolved to a branch or PR head
    is_release: bool  # a release tag; anything else, a bare SHA too, builds from source
    build_settings: dict[str, str] = field(default_factory=dict)

    @property
    def installation_method(self) -> InstallationMethod:
        """How this artifact installs: from its release, or from source."""
        return "release" if self.is_release else "source"


def dist_slug_for(artifact: ResolvedArtifact) -> str:
    """The `dist/` directory name this artifact will actually occupy.

    The two installation methods derive their slug from different inputs, and
    they have to, so this is the one place that knows which:

    * A release is named for its resolved tag. The requested alias may be
      mutable (`latest`), and the tag is not. It is `v`-prefixed the way
      `install_release` names its default directory: npm resolution reports
      js tags bare (`0.4.0`), and `dist/0.4.0` beside `dist/v0.4.0` is one
      release that xtest would test twice.
    * A source build is named for the *expanded requested ref*, because that is
      what `cmd_tip` uses (`installers.py`, `VERSIONS=<slug>`). Resolution does
      not round-trip here: `pr:123` resolves to the tag `pull-123` but builds
      into `refs--pull--123--head`, so slugging a source build from its tag
      points at a directory that never gets created.
    """
    from otdf_sdk_mgr.refs import dist_slug, expand_pr_shorthand
    from otdf_sdk_mgr.semver import normalize_version

    if artifact.is_release:
        return normalize_version(dist_slug(artifact.tag))
    return dist_slug(expand_pr_shorthand(artifact.requested_alias))


def _build_key(commit_sha: str | None, dist_name: str) -> str:
    """What makes two artifacts one build: their commit, or failing that, their directory.

    A release whose commit is unknown is still one release per directory, so
    two such releases are told apart by where they install, not lumped
    together under one missing commit.
    """
    return commit_sha or f"dist/{dist_name}"


def check_collision(resolved: list[ResolvedArtifact]) -> str | None:
    """Check for colliding installed paths.

    Returns an error message if two artifacts at *different commits* would
    install to the same dist directory (after slug normalization), or None.

    Buckets on the directory each artifact will actually occupy, not the raw
    tag, to catch cases like the js branches `sdk/feature` and `feature`,
    which both build into `dist/feature`.

    Sharing a directory only matters when the contents would disagree. Two
    aliases at one commit produce the same build, so they pass: for measured
    arms that case is the neutral outcome, and for a provisioning pin naming
    an arm's commit it is the ordinary way to say "provision with the build I
    am already measuring".
    """
    slug_to_commits: dict[str, dict[str | None, list[str]]] = {}
    for artifact in resolved:
        by_commit = slug_to_commits.setdefault(dist_slug_for(artifact), {})
        by_commit.setdefault(artifact.commit_sha, []).append(artifact.requested_alias)

    messages = [
        f"{slug}: "
        + "; ".join(
            f"{', '.join(aliases)} at {short_commit(commit)}"
            for commit, aliases in sorted(by_commit.items(), key=lambda item: item[0] or "")
        )
        for slug, by_commit in sorted(slug_to_commits.items())
        if len(by_commit) > 1
    ]
    if messages:
        return "Colliding installed paths detected:\n  " + "\n  ".join(messages)
    return None


def is_neutral_preparation(resolved: list[ResolvedArtifact]) -> bool:
    """True if two or more arms all resolved to one build.

    Repeats count: `main main` is neutral. This is not an error — it's an
    explicit neutral outcome, reported before anything is built.
    """
    if len(resolved) < 2:
        return False
    return len({_build_key(a.commit_sha, dist_slug_for(a)) for a in resolved}) == 1


def repeated_builds(arms: Iterable[ArtifactIdentity]) -> list[list[str]]:
    """The aliases of arms that are one build, grouped, for each build named twice.

    Comparing two arms in a group measures only noise. A run where *every*
    arm is one build is NEUTRAL and never installs, so this is about the
    rest: `v0.38.0 main pr:123` the day `main` is the release commit.
    """
    groups: dict[str, list[str]] = {}
    for arm in arms:
        key = _build_key(arm.commit_sha, arm.installed_tag)
        groups.setdefault(key, []).append(arm.requested_alias)
    return [aliases for aliases in groups.values() if len(aliases) > 1]
