"""Installer for the OpenTDF platform service.

Produces a built `service` binary at `xtest/platform/dist/<version>/service`
from source — container images and release tarballs are not published by
`opentdf/platform` today.

Tag namespacing: the platform monorepo tags releases as `service/vX.Y.Z`.
Users pass plain versions (e.g. `v0.9.0`); the installer prefixes `service/`
when resolving against git.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from otdf_sdk_mgr.config import SDK_GIT_URLS, SDK_TAG_INFIXES
from otdf_sdk_mgr.refs import expand_pr_shorthand, is_mutable_ref, ref_slug
from otdf_sdk_mgr.semver import normalize_version

PLATFORM_BARE_REPO = "platform.git"
HELPER_SCRIPTS_BRANCH = "main"


class PlatformInstallError(Exception):
    """Raised when platform installation fails."""


def get_platform_dir() -> Path:
    """Return `xtest/platform/`, creating an env-var override hook.

    Search precedence:
      1. `OTDF_PLATFORM_DIR` env var.
      2. Walk up from this package until an `xtest/` sibling is found.
    """
    env = os.environ.get("OTDF_PLATFORM_DIR")
    if env:
        return Path(env)
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "xtest").exists():
            return current / "xtest" / "platform"
        current = current.parent
    raise PlatformInstallError("Could not locate xtest/ root. Set OTDF_PLATFORM_DIR to override.")


def _platform_src_root() -> Path:
    return get_platform_dir() / "src"


def _platform_dist_root() -> Path:
    return get_platform_dir() / "dist"


def _platform_scripts_dir() -> Path:
    return get_platform_dir() / "scripts"


def _platform_bare_repo() -> Path:
    return _platform_src_root() / PLATFORM_BARE_REPO


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a command, streaming output to the terminal.

    Long-running commands (`go build`, `git clone`) need live output so the
    user can see progress. We don't capture; on failure the user has already
    seen the diagnostics in their terminal.
    """
    try:
        result = subprocess.run(cmd, cwd=cwd)
    except FileNotFoundError as e:
        raise PlatformInstallError(f"executable not found: {cmd[0]} ({e})") from e
    if result.returncode != 0:
        raise PlatformInstallError(f"command failed (exit {result.returncode}): {' '.join(cmd)}")


def _ensure_bare_repo() -> Path:
    """Clone the platform bare repo if missing or corrupt; fetch updates otherwise.

    `bare.exists()` alone is too loose: a Ctrl-C'd `git clone --bare` leaves a
    directory with `config`, `HEAD`, and `objects/` but no `refs/`, and git
    rejects it as "not a git repository" on every subsequent operation. Probe
    with `rev-parse --is-bare-repository` and re-clone on failure rather than
    leaving the user to manually `rm -rf` the dist tree.
    """
    bare = _platform_bare_repo()
    bare.parent.mkdir(parents=True, exist_ok=True)
    if bare.exists():
        probe = subprocess.run(
            ["git", f"--git-dir={bare}", "rev-parse", "--is-bare-repository"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            print(f"Bare clone at {bare} looks corrupt ({probe.stderr.strip()}); removing.")
            shutil.rmtree(bare)
    if not bare.exists():
        url = SDK_GIT_URLS["platform"].removesuffix(".git")
        print(f"Cloning {url} as a bare repository into {bare}...")
        _run(["git", "clone", "--bare", url, str(bare)])
    else:
        print(f"Fetching updates for {bare}...")
        _run(["git", f"--git-dir={bare}", "fetch", "--all", "--tags"])
    return bare


def _is_hex(s: str) -> bool:
    return bool(s) and all(c in "0123456789abcdef" for c in s.lower())


def _resolve_platform_ref(version_or_ref: str) -> str:
    """Turn a user-supplied version into the actual git ref to checkout.

    `v0.9.0` → `service/v0.9.0` (matches SDK_TAG_INFIXES["platform"]).
    `pr:42` → `refs/pull/42/head` (expanded first, then passes through the
    `/` check).
    A ref that already contains `/`, a full-length hex SHA, or `main` is
    returned as-is. 7-39 char hex inputs are returned unchanged — they
    might be abbreviated SHAs or branch names; `install_platform_source`
    resolves the ambiguity via `_expand_short_sha` once the bare repo is
    available.
    """
    version_or_ref = expand_pr_shorthand(version_or_ref)
    infix = SDK_TAG_INFIXES.get("platform", "service")
    if "/" in version_or_ref and (":" in version_or_ref or "@" in version_or_ref):
        raise PlatformInstallError(
            f"container-image refs are not supported: {version_or_ref!r}; "
            "use a git ref like v0.9.0, service/v0.9.0, main, or a SHA"
        )
    if "/" in version_or_ref or version_or_ref in ("main", "HEAD"):
        return version_or_ref
    if len(version_or_ref) in (40, 64) and _is_hex(version_or_ref):
        return version_or_ref
    if 7 <= len(version_or_ref) <= 39 and _is_hex(version_or_ref):
        return version_or_ref
    # Only apply the `service/v…` infix when the input parses as semver. Plain
    # branch names like `DSPX-3397-platform-service` pass through unchanged
    # so `_ensure_worktree` can resolve them via the standard branch path.
    from otdf_sdk_mgr.semver import parse_semver

    if parse_semver(version_or_ref) is not None:
        return f"{infix}/{normalize_version(version_or_ref)}"
    return version_or_ref


def _expand_short_sha(short: str) -> str:
    """Expand an abbreviated hex string to a full SHA via the bare repo.

    Returns the full 40-char SHA if git resolves the prefix uniquely.
    Raises `PlatformInstallError` if git reports the prefix is ambiguous.
    Returns the input unchanged if git cannot resolve it (caller may then
    treat it as a branch/tag name; `git worktree add` will produce a clear
    `invalid reference` error if the name doesn't exist either).
    """
    bare = _ensure_bare_repo()
    result = subprocess.run(
        ["git", f"--git-dir={bare}", "rev-parse", "--verify", f"{short}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    if "ambiguous" in result.stderr.lower():
        raise PlatformInstallError(
            f"ambiguous abbreviated SHA {short!r}: pass at least 8 chars, or the full 40-char SHA"
        )
    return short


def _worktree_path_for(ref: str) -> Path:
    return _platform_src_root() / ref_slug(ref)


def _ensure_worktree(ref: str) -> Path:
    """Create (or reuse) a git worktree at the given platform ref.

    For mutable refs (branches, PR heads), `_ensure_bare_repo` has already
    re-fetched, and we reset the worktree HEAD to the freshly-fetched ref so
    a subsequent install picks up new commits. For immutable refs (tags,
    SHAs) we just reuse.

    An on-disk worktree dir whose `.git` file points to a missing admin
    location (orphaned by a re-cloned bare repo) is removed and re-added
    rather than re-used — git treats reuse as fatal.
    """
    bare = _ensure_bare_repo()
    # The bare clone's default refspec is `+refs/heads/*:refs/heads/*` plus
    # `--tags`, so GitHub PR refs (`refs/pull/N/head`) are never pulled.
    # Fetch any explicit `refs/...` ref by name into the bare repo before we
    # try to use it.
    if ref.startswith("refs/"):
        print(f"Fetching {ref} into bare repo...")
        _run(["git", f"--git-dir={bare}", "fetch", "origin", f"+{ref}:{ref}"])
    worktree = _worktree_path_for(ref)
    if worktree.exists():
        probe = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            print(
                f"Worktree at {worktree} is orphaned ({probe.stderr.strip()}); removing and re-adding."
            )
            shutil.rmtree(worktree)
        elif is_mutable_ref(ref):
            print(f"Worktree exists at {worktree}; resetting to {ref}.")
            # Worktrees from a bare clone have no `origin` remote, so we
            # reset to the bare repo's just-fetched ref. Mirrors the
            # `install_helper_scripts` pattern below.
            _run(["git", "-C", str(worktree), "reset", "--hard", ref])
            return worktree
        else:
            print(f"Worktree already exists at {worktree}; reusing.")
            return worktree
    print(f"Adding worktree at {worktree} for ref {ref}...")
    _run(["git", f"--git-dir={bare}", "worktree", "add", "--detach", str(worktree), ref])
    return worktree


def _build_service(worktree: Path, dist_dir: Path) -> Path:
    """Run `go build` to produce `dist_dir/service`.

    Writes a `.complete` marker after the build succeeds. Reuse requires both
    the binary and the marker — survives Ctrl-C mid-build, which would
    otherwise leave a half-written binary that the next invocation would
    happily serve.
    """
    dist_dir.mkdir(parents=True, exist_ok=True)
    binary = dist_dir / "service"
    marker = dist_dir / ".complete"
    if binary.exists() and marker.exists():
        print(f"  Binary already built at {binary}; reusing.")
        return binary
    if binary.exists():
        binary.unlink()
    print(f"  Building platform service binary at {binary} from {worktree}...")
    _run(["go", "build", "-o", str(binary), "./service"], cwd=worktree)
    if not binary.exists():
        raise PlatformInstallError(f"go build completed but {binary} is missing")
    marker.write_text("")
    return binary


def _record_version(dist_dir: Path, ref: str, worktree: Path) -> None:
    """Write a `.version` metadata file alongside the binary."""
    sha = _git_rev_parse(worktree, "HEAD")
    (dist_dir / ".version").write_text(f"ref={ref}\nsha={sha}\nworktree={worktree}\n")


def _git_rev_parse(worktree: Path, rev: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", rev], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise PlatformInstallError(
            f"git rev-parse {rev} failed in {worktree}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def install_platform_source(ref: str, dist_name: str | None = None) -> Path:
    """Install a platform build by checking out and building `ref`.

    `ref` may be a plain version (`v0.9.0`), a namespaced tag
    (`service/v0.9.0`), a branch (`main`), a PR shorthand (`pr:42`), a raw
    ref (`refs/pull/42/head`), or a SHA. Returns the dist dir.

    For immutable refs (tags, SHAs) an existing dist is reused. For mutable
    refs (branches, PR heads) the bare repo is re-fetched, the worktree is
    reset, the old dist is removed, and the service binary is rebuilt.
    """
    full_ref = _resolve_platform_ref(ref)
    if 7 <= len(full_ref) <= 39 and _is_hex(full_ref):
        # Abbreviated SHA: resolve to full 40-char SHA so caching matches the
        # full-SHA case. Falls through to branch-name handling if git can't
        # resolve the prefix; raises on ambiguity.
        full_ref = _expand_short_sha(full_ref)
    if dist_name is None:
        if is_mutable_ref(full_ref):
            dist_name = ref_slug(full_ref)
        else:
            # Normalize only the semver tail so namespaced tags like
            # `service/v0.9.0` produce the same dist_name as `v0.9.0`.
            dist_name = normalize_version(full_ref.rsplit("/", 1)[-1])
    dist_dir = _platform_dist_root() / dist_name
    binary = dist_dir / "service"
    marker = dist_dir / ".complete"
    if binary.exists() and marker.exists() and not is_mutable_ref(full_ref):
        print(f"  Dist already present at {dist_dir}; skipping build.")
        return dist_dir
    worktree = _ensure_worktree(full_ref)
    if binary.exists():
        binary.unlink()
    if marker.exists():
        marker.unlink()
    _build_service(worktree, dist_dir)
    _record_version(dist_dir, full_ref, worktree)
    print(f"  Platform {ref} → {dist_dir}")
    return dist_dir


def install_platform_release(version: str, dist_name: str | None = None) -> Path:
    """Install a released platform version (alias for `install_platform_source`).

    Kept as a separate function so the public CLI surface mirrors the SDK
    `install release` semantics, even though there's no published-binary
    fast path today.
    """
    return install_platform_source(version, dist_name=dist_name)


def install_helper_scripts(branch: str = HELPER_SCRIPTS_BRANCH) -> Path:
    """Check out provisioning helper scripts from the platform `main` branch.

    Scripts are shared across instances; refreshed on demand. Returns the
    scripts directory.
    """
    bare = _ensure_bare_repo()
    scripts_dir = _platform_scripts_dir()
    worktree = _worktree_path_for(f"scripts--{branch}")
    if not worktree.exists():
        print(f"Adding scripts worktree at {worktree} ({branch})...")
        _run(["git", f"--git-dir={bare}", "worktree", "add", str(worktree), branch])
    else:
        # Worktrees from a bare clone have no `origin` remote, so `git pull`
        # fails. Reset to the (just-fetched) branch ref in the bare repo.
        print(f"Updating scripts worktree at {worktree}...")
        _run(["git", "-C", str(worktree), "reset", "--hard", branch])
    src_scripts = worktree / "scripts"
    if not src_scripts.exists():
        raise PlatformInstallError(
            f"no scripts/ directory in platform@{branch}; cannot install helper scripts"
        )
    if scripts_dir.exists():
        shutil.rmtree(scripts_dir)
    shutil.copytree(src_scripts, scripts_dir)
    print(f"  Helper scripts copied to {scripts_dir}")
    return scripts_dir
