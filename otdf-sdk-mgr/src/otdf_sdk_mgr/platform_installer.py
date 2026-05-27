"""Installer for the OpenTDF platform service.

Mirrors the SDK installer pattern but produces a built `service` binary at
`xtest/platform/dist/<version>/service`. v1 supports source builds only —
container images and release tarballs are not published by `opentdf/platform`
today.

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
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise PlatformInstallError(f"command failed (exit {result.returncode}): {' '.join(cmd)}")


def _ensure_bare_repo() -> Path:
    """Clone the platform bare repo if missing; fetch updates otherwise."""
    bare = _platform_bare_repo()
    bare.parent.mkdir(parents=True, exist_ok=True)
    if not bare.exists():
        url = SDK_GIT_URLS["platform"].removesuffix(".git")
        print(f"Cloning {url} as a bare repository into {bare}...")
        _run(["git", "clone", "--bare", url, str(bare)])
    else:
        print(f"Fetching updates for {bare}...")
        _run(["git", f"--git-dir={bare}", "fetch", "--all", "--tags"])
    return bare


def _resolve_platform_ref(version_or_ref: str) -> str:
    """Turn a user-supplied version into the actual git ref to checkout.

    `v0.9.0` → `service/v0.9.0` (matches SDK_TAG_INFIXES["platform"]).
    `pr:42` → `refs/pull/42/head` (expanded first, then passes through the
    `/` check).
    A ref that already contains `/`, a hex SHA, or `main` is returned as-is.
    """
    version_or_ref = expand_pr_shorthand(version_or_ref)
    infix = SDK_TAG_INFIXES.get("platform", "service")
    if "/" in version_or_ref or version_or_ref in ("main", "HEAD"):
        return version_or_ref
    if len(version_or_ref) in (40, 64) and all(
        c in "0123456789abcdef" for c in version_or_ref.lower()
    ):
        return version_or_ref
    return f"{infix}/{normalize_version(version_or_ref)}"


def _worktree_path_for(ref: str) -> Path:
    return _platform_src_root() / ref_slug(ref)


def _ensure_worktree(ref: str) -> Path:
    """Create (or reuse) a git worktree at the given platform ref.

    For mutable refs (branches, PR heads), `_ensure_bare_repo` has already
    re-fetched, and we reset the worktree HEAD to the freshly-fetched ref so
    a subsequent install picks up new commits. For immutable refs (tags,
    SHAs) we just reuse.
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
        if is_mutable_ref(ref):
            print(f"Worktree exists at {worktree}; resetting to {ref}.")
            # Worktrees from a bare clone have no `origin` remote, so we
            # reset to the bare repo's just-fetched ref. Mirrors the
            # `install_helper_scripts` pattern below.
            _run(["git", "-C", str(worktree), "reset", "--hard", ref])
        else:
            print(f"Worktree already exists at {worktree}; reusing.")
        return worktree
    print(f"Adding worktree at {worktree} for ref {ref}...")
    _run(["git", f"--git-dir={bare}", "worktree", "add", "--detach", str(worktree), ref])
    return worktree


def _build_service(worktree: Path, dist_dir: Path) -> Path:
    """Run `go build` to produce `dist_dir/service`."""
    dist_dir.mkdir(parents=True, exist_ok=True)
    binary = dist_dir / "service"
    if binary.exists():
        print(f"  Binary already built at {binary}; reusing.")
        return binary
    print(f"  Building platform service binary at {binary} from {worktree}...")
    _run(["go", "build", "-o", str(binary), "./service"], cwd=worktree)
    if not binary.exists():
        raise PlatformInstallError(f"go build completed but {binary} is missing")
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
    if dist_name is None:
        if is_mutable_ref(full_ref):
            dist_name = ref_slug(full_ref)
        else:
            # For immutable refs (tags, SHAs), normalize only the semver tail so
            # namespaced tags like `service/v0.9.0` produce the same dist_name as `v0.9.0`.
            dist_name = normalize_version(full_ref.rsplit("/", 1)[-1])
    dist_dir = _platform_dist_root() / dist_name
    binary = dist_dir / "service"
    if binary.exists() and not is_mutable_ref(full_ref):
        print(f"  Dist already present at {dist_dir}; skipping build.")
        return dist_dir
    worktree = _ensure_worktree(full_ref)
    if binary.exists():
        # Mutable ref: drop the stale binary so `_build_service` actually rebuilds.
        binary.unlink()
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


def list_platform_versions() -> list[str]:
    """Return all `service/vX.Y.Z` tags from the platform repo, version-only."""
    from git import Git

    repo = Git()
    raw = repo.ls_remote(SDK_GIT_URLS["platform"], tags=True)
    infix = SDK_TAG_INFIXES.get("platform", "service")
    out: list[str] = []
    for line in raw.strip().splitlines():
        if not line:
            continue
        _, ref = line.split("\t", 1)
        if ref.endswith("^{}"):
            continue
        tag = ref.removeprefix("refs/tags/")
        if tag.startswith(f"{infix}/"):
            out.append(tag.removeprefix(f"{infix}/"))
    out.sort()
    return out
