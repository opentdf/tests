"""Benchmark preparation: ordered resolution and installation with manifest emission.

This module handles the specific workflow needed for benchmark runs: resolve an
ordered list of SDK build requests, install them without collisions, and emit a
versioned installation manifest recording exactly what was installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from otdf_sdk_mgr.config import (
    ALL_SDKS,
    SDK_GIT_URLS,
    SDK_TAG_INFIXES,
    get_sdk_dir,
    get_sdk_dirs,
)
from otdf_sdk_mgr.installers import cmd_tip, install_release
from otdf_sdk_mgr.manifest import (
    ArtifactIdentity,
    InstallationManifest,
    InstallationMethod,
    PreparationStatus,
    ResolvedArtifact,
    check_collision,
    dist_slug_for,
    is_full_commit_sha,
    is_neutral_preparation,
    repeated_builds,
    short_commit,
)
from otdf_sdk_mgr.platform_installer import (
    PlatformInstallError,
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

    Each alias is resolved once, in order, before anything is built.

    The SHA is a resolve-time snapshot. `cmd_tip` builds a source arm from the
    alias itself, so `install_artifact` reads the commit back from the
    checkout and fails the arm if the ref moved in between. A js release
    found on npm but not in git has no commit (None). A SHA alias that is no
    ref's tip comes back as typed, and fails here unless it is a full commit:
    an abbreviation would hide that it names the same commit as another arm.
    A full SHA is not checked to exist, so a typo in one fails only at
    checkout, after the arms before it have built.

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
    # Not SDK_GIT_URLS: that also lists "platform", which resolves but is no
    # SDK -- it has no sdk/<name>/dist tree, and installs through --platform.
    if sdk not in ALL_SDKS:
        return ([], f"Unknown SDK: {sdk} (expected one of: {', '.join(ALL_SDKS)})")
    if not requested_aliases:
        return ([], "No refs requested")

    repo_url = SDK_GIT_URLS[sdk]
    if sdk == "go":
        # otdfctl lives in the platform monorepo, whose `otdfctl/` tags reach
        # back to v0.10.0 at the archived repo's commits -- except v0.30.x.
        # `resolve` falls back to the archived otdfctl repo for those, and for
        # any monorepo lookup that fails, without saying which repo answered;
        # such an arm is recorded here with a commit the monorepo lacks.
        repo_url = SDK_GIT_URLS["platform"]

    resolved: list[ResolvedArtifact] = []
    for alias in requested_aliases:
        expanded = expand_pr_shorthand(alias)

        # Resolve to commit. Tag namespaces differ per repo: js tags carry the
        # `sdk` infix (`sdk-vX.Y.Z`; `sdk/vX.Y.Z` through 0.4.0), java tags are
        # bare, and `resolve` supplies go's itself.
        result = resolve(sdk, expanded, infix=SDK_TAG_INFIXES.get(sdk))

        if not is_resolve_success(result):
            err = result.get("err", "unknown error")
            return ([], f"Failed to resolve {sdk}@{alias}: {err}")

        # An npm-only js release resolves with sha "": record no commit
        # rather than an empty one that every such release would share.
        commit_sha = result["sha"] or None
        if commit_sha is not None and not is_full_commit_sha(commit_sha):
            error = f"{sdk}@{alias} resolved to {commit_sha!r}, which is not a full commit SHA"
            return ([], f"{error}; give the full commit SHA for {alias}")
        tag = result["tag"]
        is_head = result.get("head", False)
        is_release = "release" in result

        # build_settings stays empty: cmd_tip passes no per-ref build options.
        # (The java Makefile does source `java/<slug>.env` if one exists; that
        # goes unrecorded.)
        artifact = ResolvedArtifact(
            requested_alias=alias,
            repository=repo_url,
            commit_sha=commit_sha,
            tag=tag,
            is_head=is_head,
            is_release=is_release,
        )
        resolved.append(artifact)

    return (resolved, None)


def read_dist_commit(dist_dir: Path) -> str | None:
    """The commit SHA recorded next to a build, or None if unrecorded.

    Reads the `key=value` `.version` format that `_record_dist_commit` and
    `platform_installer._record_version` both write. A go *release* dist's
    `.version` is a bare `module@tag` with no `sha=` line, so it reads as
    unrecorded.
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


def _recorded_build(dist_dir: Path, expected_sha: str | None) -> str | None:
    """The full commit `dist_dir` is recorded as built from, if it is `expected_sha`.

    An unrecorded provenance answers None: rebuilding costs minutes, whereas
    adopting a stale directory silently mislabels it in the manifest and
    every downstream measurement attributes the wrong commit.
    """
    recorded = read_dist_commit(dist_dir)
    if recorded is not None and recorded == expected_sha:
        return recorded
    return None


def _record_dist_commit(dist_dir: Path, ref: str, commit_sha: str) -> None:
    """Record the ref and commit a dist was built from."""
    (dist_dir / ".version").write_text(f"ref={ref}\nsha={commit_sha}\n")


def _built_commit(sdk_dir: Path, slug: str) -> str:
    """The commit checked out in `src/<slug>`, which make built into `dist/<slug>`."""
    checkout = sdk_dir / "src" / slug
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BenchPrepareError(
            f"cannot read the commit built from {checkout}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _describe(e: BaseException) -> str:
    """`str(e)`, plus the stderr a CalledProcessError carries but leaves out of it.

    `checkout.py` captures git's stderr, so without this a failed fetch
    reads only "returned non-zero exit status 1".
    """
    if isinstance(e, subprocess.CalledProcessError) and e.stderr:
        stderr = e.stderr if isinstance(e.stderr, str) else e.stderr.decode(errors="replace")
        return f"{e}\n{stderr.strip()}"
    return str(e)


def install_artifact(sdk: str, artifact: ResolvedArtifact) -> ArtifactIdentity:
    """Install one resolved artifact and return its identity.

    Dispatches to install_release for released artifacts or cmd_tip for source builds.

    Args:
        sdk: SDK name
        artifact: The resolved artifact to install

    Returns:
        ArtifactIdentity with the installed path and, for a source build, the
        commit read back from its checkout

    Raises:
        BenchPrepareError: If installation fails, or a source build is not of
            the commit the alias resolved to
        OSError: If a stale dist cannot be removed
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
            raise BenchPrepareError(
                f"Failed to install {sdk} release {artifact.tag}: {_describe(e)}"
            ) from e
        commit_sha = artifact.commit_sha
    else:
        commit_sha = _build_from_source(sdk, sdk_dir, dist_dir, artifact)

    return ArtifactIdentity(
        requested_alias=artifact.requested_alias,
        repository=artifact.repository,
        commit_sha=commit_sha,
        installed_tag=slug,
        installed_path=str(dist_dir.resolve()),
        installation_method=artifact.installation_method,
        build_settings=dict(artifact.build_settings),
    )


def _build_from_source(sdk: str, sdk_dir: Path, dist_dir: Path, artifact: ResolvedArtifact) -> str:
    """Build a source arm into `dist_dir`, or reuse it; return the commit in it."""
    # A dist left by an earlier run is only reusable if it is recorded as this
    # commit's build; anything else is discarded rather than adopted.
    if dist_dir.exists():
        recorded = _recorded_build(dist_dir, artifact.commit_sha)
        if recorded is not None:
            return recorded
        shutil.rmtree(dist_dir)

    try:
        # cmd_tip owns checkout and make. It names the directory with
        # refs.dist_slug, as dist_slug_for does, and the check below catches
        # the two drifting apart.
        cmd_tip([sdk], ref=artifact.requested_alias)
    except Exception as e:
        raise BenchPrepareError(
            f"Failed to build {sdk} from source ({artifact.requested_alias}): {_describe(e)}"
        ) from e
    if not dist_dir.exists():
        raise BenchPrepareError(
            f"cmd_tip built {sdk}@{artifact.requested_alias} but {dist_dir} "
            "is missing; the slug rules have diverged"
        )

    # Record what was built, not what was resolved. cmd_tip checks out the
    # alias, not the SHA, so the two differ when the ref moves in between,
    # and a rerun can reuse this build only if the record is true.
    built = _built_commit(sdk_dir, dist_dir.name)
    _record_dist_commit(dist_dir, artifact.requested_alias, built)
    if built != artifact.commit_sha:
        raise BenchPrepareError(
            f"{sdk}@{artifact.requested_alias} resolved to {short_commit(artifact.commit_sha)} but "
            f"built {built[:8]}: the ref moved during preparation. Re-run to compare "
            "the current commits."
        )
    return built


def prepare_benchmark(
    sdk: str,
    requested_aliases: list[str],
    platform_ref: str | None = None,
    otdfctl_ref: str | None = None,
    manifest_path: Path | None = None,
) -> InstallationManifest:
    """Prepare a benchmark run: resolve, install, and manifest.

    This is the main entry point for benchmark preparation. It:
    1. Resolves the SDK arms and the otdfctl pin, before any build
    2. Stops with NEUTRAL if every arm resolved to one build
    3. Checks for collisions in installed paths
    4. Installs the arms, stopping at the first failure
    5. Installs the platform and otdfctl, if requested

    The manifest is written first, before anything is resolved, and again
    on every exit path, an exception or Ctrl-C included. Once that first
    write succeeds, the file at `manifest_path` describes this run.

    Args:
        sdk: SDK name to benchmark
        requested_aliases: Ordered list of version specs (first is reference)
        platform_ref: Optional platform version to install
        otdfctl_ref: Optional provisioning CLI version (independent of measured arms)
        manifest_path: Where to write the manifest (default: `default_manifest_path()`)

    Returns:
        InstallationManifest with status and all installed artifacts

    Raises:
        BenchPrepareError: If that first write fails. Nothing has been
            resolved, and whatever is at `manifest_path` is an earlier run's.
        OSError: If the final write fails; the file then still says this run
            did not finish.
    """
    if manifest_path is None:
        manifest_path = default_manifest_path()

    # Written before anything else, so an unwritable path fails before any
    # build, and a run killed outright -- where no handler runs -- leaves
    # this record behind rather than the previous run's manifest.
    manifest = InstallationManifest(
        status=PreparationStatus.FAILED,
        status_message="Preparation started but did not finish",
        # The arms record bare refs, so readers need the SDK to turn each
        # installed tag back into an `sdk@tag` arm.
        metadata={"sdk": sdk},
    )
    try:
        manifest.write(manifest_path)
    except OSError as e:
        raise BenchPrepareError(f"cannot write the manifest {manifest_path}: {e}") from e
    try:
        manifest.status, manifest.status_message = _prepare(
            manifest, sdk, requested_aliases, platform_ref, otdfctl_ref
        )
    except BaseException as e:
        # Ctrl-C, or an error nothing below anticipated. Record it and let it
        # propagate: an unexpected error still deserves its traceback.
        installed = manifest.sdk_arms or manifest.platform or manifest.otdfctl
        manifest.status = PreparationStatus.PARTIAL if installed else PreparationStatus.FAILED
        manifest.status_message = f"Preparation aborted: {e!r}"
        _write_abort(manifest, manifest_path)
        raise
    manifest.write(manifest_path)
    return manifest


def _write_abort(manifest: InstallationManifest, path: Path) -> None:
    """Record an abort without replacing the exception that caused it.

    If this write fails too, the "did not finish" record from the start of
    the run stays on disk, which is still true.
    """
    try:
        manifest.write(path)
    except OSError as e:
        print(f"warning: could not record the abort in {path}: {e}", file=sys.stderr)


def _prepare(
    manifest: InstallationManifest,
    sdk: str,
    requested_aliases: list[str],
    platform_ref: str | None,
    otdfctl_ref: str | None,
) -> tuple[PreparationStatus, str]:
    """Resolve and install into `manifest`; return the status to record."""
    resolved, error = resolve_ordered(sdk, requested_aliases)
    if error:
        return PreparationStatus.FAILED, error

    # Resolve the provisioning pin here, with the arms, rather than after the
    # builds: an unresolvable pin should cost a lookup, not minutes of
    # compilation first. (--platform is not resolved up front yet; a bad
    # platform ref still fails only after the arms are built.)
    otdfctl_resolved: ResolvedArtifact | None = None
    if otdfctl_ref:
        candidates, otdfctl_error = resolve_ordered(OTDFCTL_SDK, [otdfctl_ref])
        if otdfctl_error:
            return PreparationStatus.FAILED, f"Failed to resolve otdfctl: {otdfctl_error}"
        otdfctl_resolved = candidates[0]

    # Every arm one build: there is nothing to compare, so stop before any
    # build. (Arms at one commit never collide, so this needs no ordering
    # against the collision check below.)
    if is_neutral_preparation(resolved):
        # Record the resolved artifacts so downstream knows *which* commit
        # everything collapsed onto, not merely that it collapsed.
        #
        # `installed_path` stays None: this run installed nothing. A leftover
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
                    installed_path=None,
                    installation_method=artifact.installation_method,
                    build_settings=dict(artifact.build_settings),
                )
            )
        first = resolved[0]
        build = (
            f"commit: {short_commit(first.commit_sha)}"
            if first.commit_sha
            else f"release, {dist_slug_for(first)}, whose commit is unknown"
        )
        return PreparationStatus.NEUTRAL, (
            f"All {len(resolved)} requested aliases resolved to the same {build}"
        )

    # Check for collisions in installed paths (not raw tags). The provisioning
    # pin joins the check only when it shares the arms' dist/ tree -- measuring
    # java against a Go otdfctl cannot collide.
    to_check = list(resolved)
    if otdfctl_resolved is not None and sdk == OTDFCTL_SDK:
        to_check.append(otdfctl_resolved)
    collision_error = check_collision(to_check)
    if collision_error:
        return PreparationStatus.FAILED, collision_error

    try:
        for artifact in resolved:
            manifest.sdk_arms.append(install_artifact(sdk, artifact))
    except (BenchPrepareError, OSError) as e:
        status = PreparationStatus.PARTIAL if manifest.sdk_arms else PreparationStatus.FAILED
        return status, _describe(e)

    if platform_ref:
        try:
            manifest.platform = _install_platform(platform_ref)
        except (PlatformInstallError, BenchPrepareError, OSError) as e:
            return PreparationStatus.PARTIAL, f"Failed to install platform: {_describe(e)}"

    # Install otdfctl (resolved above, with the arms) separately from the
    # measured arms, so which build provisions the fixtures is always the
    # caller's explicit choice, even when it is one of the arms.
    if otdfctl_resolved is not None:
        try:
            manifest.otdfctl = install_artifact(OTDFCTL_SDK, otdfctl_resolved)
        except (BenchPrepareError, OSError) as e:
            return PreparationStatus.PARTIAL, f"Failed to install otdfctl: {_describe(e)}"

    # Not neutral, but two arms may still be one build -- `v0.38.0 main pr:123`
    # the day `main` is the release commit. Measuring them against each other
    # is legitimate noise data, so warn rather than fail.
    repeated = repeated_builds(manifest.sdk_arms)
    if repeated:
        return PreparationStatus.SUCCESS, (
            "Some arms are the same build, so comparing them measures only noise: "
            + "; ".join(" = ".join(aliases) for aliases in repeated)
        )
    return PreparationStatus.SUCCESS, ""


def _install_platform(platform_ref: str) -> ArtifactIdentity:
    """Install the platform service and return its pinned identity."""
    expanded = expand_pr_shorthand(platform_ref)
    # Both installers build from source; this only picks the installation_method
    # label recorded for the pin, by a heuristic that calls a `v2-fix` branch a
    # release and a bare `0.9.0` source.
    method: InstallationMethod
    if expanded.startswith(("v", "service/v")):
        dist_dir = install_platform_release(expanded)
        method = "release"
    else:
        dist_dir = install_platform_source(expanded)
        method = "source"

    # `platform_installer._record_version` already persists the commit
    # next to the build; read it back rather than recording a pin with
    # no commit in it, which pins nothing a reader can check out.
    platform_sha = read_dist_commit(dist_dir)
    if platform_sha is None or not is_full_commit_sha(platform_sha):
        raise BenchPrepareError(
            f"platform {expanded} installed to {dist_dir} without a recorded "
            "commit; refusing to record an unpinnable platform"
        )
    return ArtifactIdentity(
        requested_alias=platform_ref,
        repository=SDK_GIT_URLS["platform"],
        commit_sha=platform_sha,
        # The directory the installer chose, not the ref: `pr:42` and
        # `service/v0.9.0` land in `refs--pull--42--head` and `v0.9.0`.
        installed_tag=dist_dir.name,
        installed_path=str(dist_dir.resolve()),
        installation_method=method,
    )
