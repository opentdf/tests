"""Installation manifest for ordered SDK builds.

Records what one benchmark preparation installed: the measured SDK arms in
request order, the platform and provisioning-CLI pins, and an explicit
preparation status. Each entry keeps its requested alias next to the full
commit it resolved to, so several aliases for one build stay visible.

The JSON is a contract that other packages read without importing this one.
Renaming a key, or changing whether its value may be null, requires bumping
MANIFEST_VERSION.

The pre-build helpers (`dist_slug_for`, `check_collision`,
`is_neutral_preparation`) work on `ResolvedArtifact`, before anything installs.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal, cast, get_args

# Manifest schema version. Bump when changing the JSON structure.
MANIFEST_VERSION = "v1alpha1"

InstallationMethod = Literal["release", "source"]
_METHODS: tuple[str, ...] = get_args(InstallationMethod)

_FULL_SHA_RE = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")

# `to_dict` always writes every key, so a reader requires exactly these.
_IDENTITY_KEYS = frozenset(
    {
        "requested_alias",
        "repository",
        "commit_sha",
        "installed_tag",
        "installed_path",
        "installation_method",
        "build_settings",
    }
)
_MANIFEST_KEYS = frozenset(
    {"schema_version", "platform", "otdfctl", "sdk_arms", "status", "status_message", "metadata"}
)


class ManifestError(ValueError):
    """A manifest, or an identity meant for one, breaks the schema.

    A ValueError, so that one `except ValueError` covers a file that is not
    JSON (`json.JSONDecodeError`) and one that is JSON but not a manifest.
    """


class PreparationStatus(str, Enum):
    """Overall status of the installation preparation.

    * SUCCESS: every arm and every requested pin installed. `sdk_arms` holds
      at least one arm, each with its `installed_path`; a null pin was not
      requested.
    * NEUTRAL: every arm resolved to one build, so nothing installed, pins
      included. `sdk_arms` holds the two or more resolved arms, each with a
      null `installed_path`, to show which build they collapsed onto.
    * PARTIAL: stopped after some, not all, installs completed. `sdk_arms` and
      the pins hold only those that completed.
    * FAILED: failed or aborted before any install completed.

    FAILED and PARTIAL split on whether the manifest records any completed
    install. Neither promises the dist/ tree is untouched: a failed install
    may have removed a stale directory, or left a half-built one.
    """

    SUCCESS = "success"
    NEUTRAL = "neutral"
    PARTIAL = "partial"
    FAILED = "failed"


_STATUSES = tuple(s.value for s in PreparationStatus)


def short_commit(commit_sha: str | None) -> str:
    """A commit as a message names it."""
    return commit_sha[:8] if commit_sha else "an unknown commit"


def is_full_commit_sha(value: str) -> bool:
    """True for a full lowercase hex commit: 40 characters (SHA-1) or 64 (SHA-256)."""
    return _FULL_SHA_RE.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """Identity of one build the run recorded: a measured arm or a pin."""

    requested_alias: str  # as typed, e.g. "main", "v0.29.0", "pr:123"
    repository: str  # git remote URL
    # The full commit, or None when it is unknown: a js release found on npm
    # but not in git.
    commit_sha: str | None
    installed_tag: str  # the directory name under dist/
    # Absolute path to that directory, whether this run built it or reused
    # one; None only for the arms of a NEUTRAL run.
    installed_path: str | None
    installation_method: InstallationMethod
    build_settings: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Refuse to build what `from_dict` would refuse to read back."""
        _check_identity(self.commit_sha, self.installed_tag, self.installation_method, "")

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
    def from_dict(d: object, where: str = "") -> ArtifactIdentity:
        """Deserialize from a dict.

        `where` is the identity's JSON path, e.g. `sdk_arms[2]`; errors name
        each field under it.

        Raises:
            ManifestError: if `d` is not an object, lacks a key or has an extra
                one, or a value has the wrong type or breaks an invariant.
        """
        fields = _object(d, where or "identity", _IDENTITY_KEYS)
        requested_alias = _str(fields, "requested_alias", where)
        repository = _str(fields, "repository", where)
        commit_sha = _nullable_str(fields, "commit_sha", where)
        installed_tag = _str(fields, "installed_tag", where)
        installed_path = _nullable_str(fields, "installed_path", where)
        method = _str(fields, "installation_method", where)
        build_settings = _str_dict(fields, "build_settings", where)
        # `__post_init__` checks these too, but cannot name the JSON path.
        _check_identity(commit_sha, installed_tag, method, where)
        return ArtifactIdentity(
            requested_alias=requested_alias,
            repository=repository,
            commit_sha=commit_sha,
            installed_tag=installed_tag,
            installed_path=installed_path,
            installation_method=cast(InstallationMethod, method),
            build_settings=build_settings,
        )


@dataclass(kw_only=True)
class InstallationManifest:
    """Complete installation manifest for a benchmark run.

    Records the platform pin, provisioning CLI pin, and ordered SDK arms, along
    with the preparation status and the reason for it. A null pin means no pin.

    Writers must set `metadata["sdk"]` to the SDK the arms belong to. An arm
    doesn't record its SDK, and its repository can't stand in: a go arm's
    repository is the platform's.

    `status` has no default: a manifest nobody explicitly marked as a success
    must not read as one. `PreparationStatus` says what each status implies
    for `sdk_arms` and the pins.

    Writers must set `status_message` for every status but SUCCESS: what
    failed, or, for NEUTRAL, the build every arm collapsed onto. A SUCCESS
    sets it only to warn, e.g. naming arms that repeat a build.

    `from_dict` checks that the status agrees with the arms and the message.
    Construction and `write()` do not, so a writer can always record an abort.
    """

    platform: ArtifactIdentity | None = None
    otdfctl: ArtifactIdentity | None = None
    sdk_arms: list[ArtifactIdentity] = field(default_factory=list)
    status: PreparationStatus
    status_message: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-compatible dict."""
        return {
            "schema_version": MANIFEST_VERSION,
            "platform": self.platform.to_dict() if self.platform else None,
            "otdfctl": self.otdfctl.to_dict() if self.otdfctl else None,
            "sdk_arms": [arm.to_dict() for arm in self.sdk_arms],
            "status": self.status.value,
            "status_message": self.status_message,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def from_dict(d: object) -> InstallationManifest:
        """Deserialize from a dict.

        Raises:
            ManifestError: if `d` is not an object, its schema version is not
                this one, it lacks a key or has an extra one, a value has the
                wrong type, `metadata["sdk"]` is missing or empty, or the
                status disagrees with the arms or the message. None of them
                has a safe default.
        """
        if not isinstance(d, dict):
            raise ManifestError(f"manifest must be a JSON object, not {type(d).__name__}")
        if "schema_version" in d and d["schema_version"] != MANIFEST_VERSION:
            # Before the key check: another version may have other keys.
            raise ManifestError(
                f"unsupported manifest schema_version {d['schema_version']!r}; "
                f"expected {MANIFEST_VERSION!r}"
            )
        fields = _object(d, "manifest", _MANIFEST_KEYS)
        arms = fields["sdk_arms"]
        if not isinstance(arms, list):
            raise ManifestError(f"sdk_arms must be a list, not {arms!r}")
        metadata = _str_dict(fields, "metadata", "")
        if not metadata.get("sdk"):
            raise ManifestError(
                "metadata.sdk " + ("must not be empty" if "sdk" in metadata else "is missing")
            )

        manifest = InstallationManifest(
            platform=_optional_identity(fields["platform"], "platform"),
            otdfctl=_optional_identity(fields["otdfctl"], "otdfctl"),
            sdk_arms=[
                ArtifactIdentity.from_dict(arm, f"sdk_arms[{i}]") for i, arm in enumerate(arms)
            ],
            status=PreparationStatus(_one_of(fields["status"], _STATUSES, "status")),
            status_message=_str(fields, "status_message", ""),
            metadata=metadata,
        )
        _check_status_agrees(manifest)
        return manifest

    def write(self, path: Path) -> None:
        """Write manifest to JSON file, creating its directory.

        The write goes through a temporary file and a rename, so a write cut
        short (a full disk, Ctrl-C) leaves the previous file intact rather than
        truncated JSON, and leaves no temporary file behind.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        try:
            tmp.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
            tmp.replace(path)
        except BaseException:
            # Suppressed so that a failed cleanup cannot replace the real error.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def read(path: Path) -> InstallationManifest:
        """Read manifest from JSON file.

        Raises:
            ManifestError: if the file is not JSON or not a valid manifest. The
                message starts with the path.
            OSError: if the file cannot be read.
        """
        try:
            return InstallationManifest.from_dict(json.loads(path.read_text()))
        except (ManifestError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ManifestError(f"{path}: {e}") from e


def _at(where: str, key: str) -> str:
    """The JSON path of `key` in the object at `where`."""
    return f"{where}.{key}" if where else key


def _object(value: object, where: str, keys: frozenset[str]) -> dict[str, object]:
    """`value` as an object with exactly `keys`; reports missing and unknown keys together."""
    if not isinstance(value, dict):
        raise ManifestError(f"{where} must be an object, not {value!r}")
    d = cast(dict[str, object], value)
    problems = []
    if missing := sorted(keys - d.keys()):
        problems.append(f"is missing {', '.join(missing)}")
    if unknown := sorted(str(k) for k in d.keys() - keys):
        problems.append(f"has unknown keys {', '.join(unknown)}")
    if problems:
        raise ManifestError(f"{where} {' and '.join(problems)}")
    return d


def _one_of(value: object, allowed: tuple[str, ...], where: str) -> str:
    if value not in allowed:
        raise ManifestError(f"{where} must be one of {', '.join(allowed)}, not {value!r}")
    return cast(str, value)


def _str(d: dict[str, object], key: str, where: str) -> str:
    value = d[key]
    if not isinstance(value, str):
        raise ManifestError(f"{_at(where, key)} must be a string, not {value!r}")
    return value


def _nullable_str(d: dict[str, object], key: str, where: str) -> str | None:
    """A value that may be null. Not `str(d[key])`: that reads null as "None"."""
    value = d[key]
    if value is not None and not isinstance(value, str):
        raise ManifestError(f"{_at(where, key)} must be a string or null, not {value!r}")
    return value


def _str_dict(d: dict[str, object], key: str, where: str) -> dict[str, str]:
    value = d[key]
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ManifestError(f"{_at(where, key)} must map strings to strings, not {value!r}")
    return cast(dict[str, str], dict(value))


def _optional_identity(value: object, where: str) -> ArtifactIdentity | None:
    return None if value is None else ArtifactIdentity.from_dict(value, where)


def _check_commit(commit_sha: str | None, where: str) -> None:
    # Never an abbreviation: `abc1234` and the commit it abbreviates must
    # compare as one build.
    if commit_sha is not None and not is_full_commit_sha(commit_sha):
        raise ManifestError(
            f"{_at(where, 'commit_sha')} must be a full lowercase hex commit SHA "
            f"(40 or 64 characters) or null, not {commit_sha!r}"
        )


def _check_identity(commit_sha: str | None, installed_tag: str, method: str, where: str) -> None:
    """The invariants an identity holds however it was made."""
    _check_commit(commit_sha, where)
    if not installed_tag:
        raise ManifestError(f"{_at(where, 'installed_tag')} must not be empty")
    _one_of(method, _METHODS, _at(where, "installation_method"))


def _check_status_agrees(manifest: InstallationManifest) -> None:
    """The status must describe the arms and the message recorded with it."""
    status = manifest.status
    paths = [arm.installed_path for arm in manifest.sdk_arms]
    if status is PreparationStatus.NEUTRAL and (
        len(paths) < 2 or any(p is not None for p in paths)
    ):
        raise ManifestError(
            "status neutral needs at least two sdk_arms, each with a null installed_path"
        )
    if status is PreparationStatus.SUCCESS and (not paths or None in paths):
        raise ManifestError(
            "status success needs at least one sdk_arm, each with an installed_path"
        )
    if status is not PreparationStatus.SUCCESS and not manifest.status_message:
        raise ManifestError(f"status {status.value} needs a status_message saying why")


@dataclass(frozen=True, slots=True)
class ResolvedArtifact:
    """One resolved artifact request: alias → commit + installation intent."""

    requested_alias: str
    repository: str
    # The full commit, or None for a js release found on npm but not in git.
    commit_sha: str | None
    # The resolver's tag (`pull-123`, a bare npm `0.4.0`), not the dist
    # directory name; that is `dist_slug_for`.
    tag: str
    is_head: bool  # resolved to a branch or PR head
    is_release: bool  # a release tag; anything else, a bare SHA too, builds from source
    build_settings: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Only full commits compare: an abbreviation would hide a same-commit request."""
        _check_commit(self.commit_sha, "")

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

    Raises:
        ValueError: if the ref names no directory (see `refs.dist_slug`).
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
    together under one missing commit. The directory is casefolded for the
    reason `check_collision` gives.
    """
    return commit_sha or f"dist/{dist_name.casefold()}"


def check_collision(resolved: list[ResolvedArtifact]) -> str | None:
    """Check for colliding installed paths.

    Returns an error message if two artifacts at *different commits* would
    install to the same dist directory (after slug normalization), or None.

    Buckets on the directory each artifact will actually occupy, not the raw
    tag, to catch cases like the js branches `sdk/feature` and `feature`,
    which both build into `dist/feature`. The bucket is casefolded: `Feature`
    and `feature` are one directory on a case-insensitive disk, as macOS's
    are by default. The message keeps the spellings as given.

    Sharing a directory only matters when the contents would disagree. Two
    aliases at one commit produce the same build, so they pass: for measured
    arms that case is the neutral outcome, and for a provisioning pin naming
    an arm's commit it is the ordinary way to say "provision with the build I
    am already measuring".
    """
    spellings: dict[str, list[str]] = {}
    by_dir: dict[str, dict[str | None, list[str]]] = {}
    for artifact in resolved:
        slug = dist_slug_for(artifact)
        names = spellings.setdefault(slug.casefold(), [])
        if slug not in names:
            names.append(slug)
        by_commit = by_dir.setdefault(slug.casefold(), {})
        by_commit.setdefault(artifact.commit_sha, []).append(artifact.requested_alias)

    messages = [
        f"{' / '.join(spellings[key])}: "
        + "; ".join(
            f"{', '.join(aliases)} at {short_commit(commit)}"
            for commit, aliases in sorted(by_commit.items(), key=lambda item: item[0] or "")
        )
        for key, by_commit in sorted(by_dir.items())
        if len(by_commit) > 1
    ]
    if messages:
        return "Colliding installed paths detected:\n  " + "\n  ".join(messages)
    return None


def is_neutral_preparation(resolved: list[ResolvedArtifact]) -> bool:
    """True if two or more arms all resolved to one build.

    Repeats count: `main main` is neutral. Callers check this before building:
    a neutral run has nothing to compare, which is an outcome, not an error.
    """
    if len(resolved) < 2:
        return False
    return len({_build_key(a.commit_sha, dist_slug_for(a)) for a in resolved}) == 1


def repeated_builds(arms: Iterable[ArtifactIdentity]) -> list[list[str]]:
    """The aliases of arms that are one build, grouped, for each build named more than once.

    Comparing two arms in a group measures only noise. Callers check
    `is_neutral_preparation` before building, which covers a run where
    *every* arm is one build; this finds the rest: `v0.38.0 main pr:123` the
    day `main` is the release commit.
    """
    groups: dict[str, list[str]] = {}
    for arm in arms:
        key = _build_key(arm.commit_sha, arm.installed_tag)
        groups.setdefault(key, []).append(arm.requested_alias)
    return [aliases for aliases in groups.values() if len(aliases) > 1]
