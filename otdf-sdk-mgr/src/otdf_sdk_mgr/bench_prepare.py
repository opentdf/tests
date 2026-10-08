"""Benchmark preparation: ordered resolution and installation with manifest emission.

This module handles the specific workflow needed for benchmark runs: resolve an
ordered list of SDK build requests, install them without collisions, and emit a
versioned installation manifest recording exactly what was installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from otdf_sdk_mgr.config import SDK_GIT_URLS, get_sdk_dir, get_sdk_dirs
from otdf_sdk_mgr.installers import cmd_tip, install_release
from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    PreparationStatus,
    ResolvedArtifact,
    check_collision,
    dist_slug_for,
    is_neutral_preparation,
)
from otdf_sdk_mgr.platform_installer import (
    install_platform_release,
    install_platform_source,
)
from otdf_sdk_mgr.refs import expand_pr_shorthand
from otdf_sdk_mgr.resolve import is_resolve_success, resolve


# otdfctl is the Go CLI regardless of which SDK is being measured, so it
# resolves and installs against "go" and lives in the go dist/ tree.
OTDFCTL_SDK = "go"


class BenchPrepareError(Exception):
    """Benchmark preparation failed."""


def default_manifest_path() -> Path:
    """Conventional path for benchmark installation manifests."""
    sdk_dir = get_sdk_dir()
    return sdk_dir / "benchmark.installed.json"


def resolve_ordered(
    sdk: str, requested_aliases: list[str]
) -> tuple[list[ResolvedArtifact], str | None]:
    """Resolve an ordered list of SDK build requests.

    Each alias is resolved once to an immutable commit SHA. Mutable refs (branches,
    PR heads) are resolved exactly once; the returned SHA is what will be installed.

    Args:
        sdk: SDK name ("go", "java", "js")
        requested_aliases: Ordered list of version specs (e.g., ["v0.29.0", "main", "pr:123"])

    Returns:
        (resolved_artifacts, error_message)
        - resolved_artifacts: List of ResolvedArtifact in request order
        - error_message: None on success, error string on failure

    The alias→commit mapping may be many-to-one (same commit via different paths).
    Request order is preserved; duplicates are NOT removed.
    """
    if sdk not in SDK_GIT_URLS:
        return ([], f"Unknown SDK: {sdk}")

    repo_url = SDK_GIT_URLS.get(sdk, "")
    if sdk == "go":
        # Go uses platform monorepo
        repo_url = SDK_GIT_URLS["platform"]

    resolved: list[ResolvedArtifact] = []
    for alias in requested_aliases:
        # Expand pr:N shorthand
        expanded = expand_pr_shorthand(alias)

        # Resolve to commit
        result = resolve(sdk, expanded, infix="sdk" if sdk != "go" else "otdfctl")

        if not is_resolve_success(result):
            err = result.get("err", "unknown error")
            return ([], f"Failed to resolve {sdk}@{alias}: {err}")

        # Extract resolution data
        commit_sha = result["sha"]
        tag = result["tag"]
        is_head = result.get("head", False)
        is_release = "release" in result

        # Build settings (e.g., PLATFORM_BRANCH for java)
        build_settings: dict[str, str] = {}
        # Could add lookup_additional_options(sdk, expanded) here if needed

        artifact = ResolvedArtifact(
            requested_alias=alias,
            repository=repo_url,
            commit_sha=commit_sha,
            tag=tag,
            is_head=is_head,
            is_release=is_release,
            build_settings=build_settings,
        )
        resolved.append(artifact)

    return (resolved, None)


def read_dist_commit(dist_dir: Path) -> str | None:
    """The commit SHA recorded next to a build, or None if unrecorded.

    Reads the `key=value` `.version` format written by
    `platform_installer._record_version`, so both installers speak one dialect.
    """
    version_file = dist_dir / ".version"
    if not version_file.exists():
        return None
    try:
        for line in version_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "sha":
                return value.strip()
    except OSError:
        return None
    return None


def _verify_dist_commit(dist_dir: Path, expected_sha: str) -> bool:
    """Whether an existing dist is known to have been built from `expected_sha`.

    An unrecorded provenance answers False: rebuilding costs minutes, whereas
    adopting a stale directory silently mislabels it in the manifest and
    every downstream measurement attributes the wrong commit.
    """
    return read_dist_commit(dist_dir) == expected_sha


def _record_dist_commit(dist_dir: Path, ref: str, commit_sha: str) -> None:
    """Record the ref and commit a dist was built from."""
    (dist_dir / ".version").write_text(f"ref={ref}\nsha={commit_sha}\n")


def install_artifact(sdk: str, artifact: ResolvedArtifact) -> ArtifactIdentity:
    """Install one resolved artifact and return its identity.

    Dispatches to install_release for released artifacts or cmd_tip for source builds.

    Args:
        sdk: SDK name
        artifact: The resolved artifact to install

    Returns:
        ArtifactIdentity with installed path and metadata

    Raises:
        BenchPrepareError: If installation fails
    """
    sdk_dirs = get_sdk_dirs()
    sdk_dir = sdk_dirs[sdk]

    # One slug function, shared with check_collision, so the directory we
    # reason about is the directory that ends up on disk.
    slug = dist_slug_for(artifact)
    dist_dir = sdk_dir / "dist" / slug

    if artifact.is_release:
        try:
            dist_dir = install_release(sdk, artifact.tag, dist_name=slug)
        except Exception as e:
            raise BenchPrepareError(f"Failed to install {sdk} release {artifact.tag}: {e}") from e
    else:
        # A dist left by an earlier run is only reusable if it is recorded as
        # this commit's build; anything else is discarded rather than adopted.
        if dist_dir.exists() and not _verify_dist_commit(dist_dir, artifact.commit_sha):
            shutil.rmtree(dist_dir)

        if not dist_dir.exists():
            try:
                # cmd_tip owns checkout, slug and make; do not re-implement it.
                cmd_tip([sdk], ref=artifact.requested_alias)
                if not dist_dir.exists():
                    raise BenchPrepareError(
                        f"cmd_tip built {sdk}@{artifact.requested_alias} but {dist_dir} "
                        "is missing; the slug rules have diverged"
                    )
                _record_dist_commit(dist_dir, artifact.requested_alias, artifact.commit_sha)
            except Exception as e:
                raise BenchPrepareError(
                    f"Failed to build {sdk} from source ({artifact.tag}): {e}"
                ) from e

    return ArtifactIdentity(
        requested_alias=artifact.requested_alias,
        repository=artifact.repository,
        commit_sha=artifact.commit_sha,
        installed_tag=slug,
        installed_path=str(dist_dir.resolve()),
        installation_method=artifact.installation_method,
        build_settings=dict(artifact.build_settings),
    )


def prepare_benchmark(
    sdk: str,
    requested_aliases: list[str],
    platform_ref: str | None = None,
    otdfctl_ref: str | None = None,
    manifest_path: Path | None = None,
) -> InstallationManifest:
    """Prepare a benchmark run: resolve, install, and manifest.

    This is the main entry point for benchmark preparation. It:
    1. Resolves all requested aliases to immutable commits
    2. Detects same-commit scenarios (neutral preparation)
    3. Checks for collisions in installed paths
    4. Installs all artifacts
    5. Installs platform and otdfctl if specified
    6. Writes a versioned installation manifest

    Args:
        sdk: SDK name to benchmark
        requested_aliases: Ordered list of version specs (first is reference)
        platform_ref: Optional platform version to install
        otdfctl_ref: Optional provisioning CLI version (independent of measured arms)
        manifest_path: Where to write the manifest (default: sdk/benchmark.installed.json)

    Returns:
        InstallationManifest with status and all installed artifacts

    The function produces an explicit neutral status when distinct aliases resolve
    to the same commit, before installation begins.
    """
    if manifest_path is None:
        manifest_path = default_manifest_path()

    manifest = InstallationManifest()

    # Resolve SDK arms
    resolved, error = resolve_ordered(sdk, requested_aliases)
    if error:
        manifest.status = PreparationStatus.FAILED
        manifest.status_message = error
        manifest.write(manifest_path)
        return manifest

    # Resolve the provisioning pin here, with the arms, rather than after the
    # builds: an unresolvable pin should cost a lookup, not minutes of
    # compilation first. otdfctl is always the Go CLI, so it is resolved and
    # installed against "go" whatever SDK is under measurement.
    otdfctl_resolved: ResolvedArtifact | None = None
    if otdfctl_ref:
        candidates, otdfctl_error = resolve_ordered(OTDFCTL_SDK, [otdfctl_ref])
        if otdfctl_error:
            manifest.status = PreparationStatus.FAILED
            manifest.status_message = f"Failed to resolve otdfctl: {otdfctl_error}"
            manifest.write(manifest_path)
            return manifest
        otdfctl_resolved = candidates[0]

    # Check for same-commit (neutral) outcome BEFORE collision
    # Two aliases that resolve to one commit AND one slug must be neutral, not FAILED
    if is_neutral_preparation(resolved):
        manifest.status = PreparationStatus.NEUTRAL
        manifest.status_message = (
            f"All {len(resolved)} requested aliases resolved to the same commit: "
            f"{resolved[0].commit_sha[:8]}"
        )
        # Record the resolved artifacts so downstream knows *which* commit
        # everything collapsed onto, not merely that it collapsed.
        #
        # `installed_path` stays empty: this run installed nothing. A leftover
        # directory from an earlier run may well sit at the slug, but naming
        # it here would claim a provenance this preparation never checked --
        # and `installed_path` is exactly what a reader trusts to answer "what
        # is in that directory".
        for artifact in resolved:
            manifest.sdk_arms.append(
                ArtifactIdentity(
                    requested_alias=artifact.requested_alias,
                    repository=artifact.repository,
                    commit_sha=artifact.commit_sha,
                    installed_tag=dist_slug_for(artifact),
                    installed_path="",
                    installation_method=artifact.installation_method,
                    build_settings=dict(artifact.build_settings),
                )
            )
        manifest.write(manifest_path)
        return manifest

    # Check for collisions in installed paths (not raw tags). The provisioning
    # pin joins the check only when it shares the arms' dist/ tree -- measuring
    # java against a Go otdfctl cannot collide.
    to_check = list(resolved)
    if otdfctl_resolved is not None and sdk == OTDFCTL_SDK:
        to_check.append(otdfctl_resolved)
    collision_error = check_collision(to_check)
    if collision_error:
        manifest.status = PreparationStatus.FAILED
        manifest.status_message = collision_error
        manifest.write(manifest_path)
        return manifest

    # Install each artifact
    try:
        for artifact in resolved:
            identity = install_artifact(sdk, artifact)
            manifest.sdk_arms.append(identity)
    except BenchPrepareError as e:
        manifest.status = PreparationStatus.PARTIAL
        manifest.status_message = str(e)
        manifest.write(manifest_path)
        return manifest

    # Install platform if specified
    if platform_ref:
        try:
            expanded = expand_pr_shorthand(platform_ref)
            # Determine if it's a release or source ref
            # Simple heuristic: if it looks like a version tag, use release; otherwise source
            if expanded.startswith("v") or expanded.startswith("service/v"):
                dist_dir = install_platform_release(expanded)
                method = "release"
            else:
                dist_dir = install_platform_source(expanded)
                method = "source"

            # `platform_installer._record_version` already persists the commit
            # next to the build; read it back rather than recording a pin with
            # no commit in it, which is indistinguishable from no pin at all.
            platform_sha = read_dist_commit(dist_dir)
            if platform_sha is None:
                raise BenchPrepareError(
                    f"platform {expanded} installed to {dist_dir} without a recorded "
                    "commit; refusing to record an unpinnable platform"
                )
            manifest.platform = ArtifactIdentity(
                requested_alias=platform_ref,
                repository=SDK_GIT_URLS["platform"],
                commit_sha=platform_sha,
                installed_tag=expanded,
                installed_path=str(dist_dir.resolve()),
                installation_method=method,  # type: ignore
            )
        except Exception as e:
            manifest.status = PreparationStatus.PARTIAL
            manifest.status_message = f"Failed to install platform: {e}"
            manifest.write(manifest_path)
            return manifest

    # Install otdfctl (resolved above, with the arms) separately from the
    # measured arms, so the build under measurement never provisions the
    # fixtures it is measured against.
    if otdfctl_resolved is not None:
        try:
            manifest.otdfctl = install_artifact(OTDFCTL_SDK, otdfctl_resolved)
        except Exception as e:
            manifest.status = PreparationStatus.PARTIAL
            manifest.status_message = f"Failed to install otdfctl: {e}"
            manifest.write(manifest_path)
            return manifest

    manifest.status = PreparationStatus.SUCCESS
    manifest.write(manifest_path)
    return manifest
