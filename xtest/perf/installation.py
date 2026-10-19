"""Reading the installation manifest that `otdf-sdk-mgr install benchmark` writes.

The manifest is the contract between preparation and measurement: it records,
in request order, which build each requested alias resolved to and where it was
installed, plus the preparation's own status. Reading it here means a local run
and a CI run take their arms and their provenance from the same record, rather
than from environment variables somebody had to assemble by hand.

`otdf-sdk-mgr` and xtest do not depend on each other, so the JSON shape is a
written convention (see ``otdf_sdk_mgr.manifest``) rather than a shared import.
Only the fields measurement needs are read, and the schema version is checked
so that a reshaped manifest fails loudly instead of being half-understood.

Imports no pytest, for the same reason as :mod:`perf.config`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

#: Environment variable `otdf-local env` exports when a manifest exists.
MANIFEST_ENV = "BENCH_INSTALLATION_MANIFEST"

#: Manifest schema versions this reader understands.
SUPPORTED_SCHEMAS = ("v1alpha1",)

#: Preparation finished and every arm is installed.
SUCCESS = "success"
#: Every distinct requested alias resolved to one commit: nothing to compare.
#: Not an error -- the run reports it and does not fail.
NEUTRAL = "neutral"


class ManifestError(ValueError):
    """The manifest exists but cannot be used."""


@dataclass(frozen=True, slots=True)
class InstalledArm:
    """One measured build, as preparation recorded it."""

    requested_alias: str
    repository: str
    commit_sha: str
    #: The ``dist/`` directory name, which is what arm selection resolves.
    installed_tag: str
    installation_method: str

    def to_dict(self) -> dict[str, str]:
        return {
            "requested_alias": self.requested_alias,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "installed_tag": self.installed_tag,
            "installation_method": self.installation_method,
        }


@dataclass(frozen=True, slots=True)
class Installation:
    """What one preparation installed, in request order."""

    path: Path
    sdk: str
    status: str
    status_message: str
    arms: tuple[InstalledArm, ...]
    otdfctl: InstalledArm | None = None
    platform: InstalledArm | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def neutral(self) -> bool:
        return self.status == NEUTRAL

    @property
    def usable(self) -> bool:
        """True if the recorded arms can be measured."""
        return self.status == SUCCESS and len(self.arms) >= 2

    def arm_specs(self) -> tuple[str, ...]:
        """The arms as ``sdk@tag`` specs, reference first."""
        return tuple(f"{self.sdk}@{a.installed_tag}" for a in self.arms)

    def arm_for_tag(self, tag: str) -> InstalledArm | None:
        return next((a for a in self.arms if a.installed_tag == tag), None)

    def to_dict(self) -> dict[str, object]:
        """The provenance worth carrying into a result artifact.

        Installed paths are left out: they differ between machines, and the
        identity of an artifact must not.
        """
        return {
            "sdk": self.sdk,
            "status": self.status,
            "status_message": self.status_message,
            "arms": [a.to_dict() for a in self.arms],
            "otdfctl": self.otdfctl.to_dict() if self.otdfctl else None,
            "platform": self.platform.to_dict() if self.platform else None,
        }


def _arm(raw: object, where: str) -> InstalledArm:
    if not isinstance(raw, dict):
        raise ManifestError(f"{where} is not an object")
    try:
        return InstalledArm(
            requested_alias=str(raw["requested_alias"]),
            repository=str(raw.get("repository", "")),
            commit_sha=str(raw["commit_sha"]),
            installed_tag=str(raw["installed_tag"]),
            installation_method=str(raw.get("installation_method", "")),
        )
    except KeyError as e:
        raise ManifestError(f"{where} is missing {e}") from e


def parse(raw: object, path: Path) -> Installation:
    """Validate a decoded manifest."""
    if not isinstance(raw, dict):
        raise ManifestError(f"{path}: manifest is not a JSON object")
    schema = raw.get("schema_version")
    if schema not in SUPPORTED_SCHEMAS:
        raise ManifestError(
            f"{path}: manifest schema {schema!r} is not one of {SUPPORTED_SCHEMAS}"
        )
    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ManifestError(f"{path}: metadata is not an object")
    sdk = str(metadata.get("sdk", ""))
    if not sdk:
        raise ManifestError(
            f"{path}: metadata.sdk is missing; re-run `otdf-sdk-mgr install "
            "benchmark` to record which SDK the arms belong to"
        )
    arms_raw = raw.get("sdk_arms") or []
    if not isinstance(arms_raw, list):
        raise ManifestError(f"{path}: sdk_arms is not a list")
    arms = tuple(_arm(a, f"{path}: sdk_arms[{i}]") for i, a in enumerate(arms_raw))
    otdfctl = raw.get("otdfctl")
    platform = raw.get("platform")
    return Installation(
        path=path,
        sdk=sdk,
        status=str(raw.get("status", "")),
        status_message=str(raw.get("status_message") or ""),
        arms=arms,
        otdfctl=_arm(otdfctl, f"{path}: otdfctl") if otdfctl else None,
        platform=_arm(platform, f"{path}: platform") if platform else None,
        metadata={str(k): str(v) for k, v in metadata.items()},
    )


def read(path: Path) -> Installation:
    """Read and validate the manifest at ``path``."""
    try:
        raw = json.loads(path.read_text())
    except OSError as e:
        raise ManifestError(f"cannot read installation manifest {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise ManifestError(f"{path} is not valid JSON: {e}") from e
    return parse(raw, path)


def from_env(environ: dict[str, str] | None = None) -> Installation | None:
    """The manifest named by :data:`MANIFEST_ENV`, or None when unset.

    Set but unreadable is an error, not a fallback: the variable is an explicit
    statement that this run was prepared, and measuring whatever happens to be
    in ``dist/`` instead would attach no provenance to the result without
    saying so.
    """
    value = (os.environ if environ is None else environ).get(MANIFEST_ENV, "")
    if not value:
        return None
    return read(Path(value))
