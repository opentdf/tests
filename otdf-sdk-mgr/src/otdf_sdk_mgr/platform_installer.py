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

from otdf_sdk_mgr.checkout import BARE_REFRESH, CheckoutError, require_worktree, upstream_ref
from otdf_sdk_mgr.config import SDK_GIT_URLS, SDK_TAG_INFIXES
from otdf_sdk_mgr.refs import expand_pr_shorthand, is_mutable_target, ref_slug
from otdf_sdk_mgr.semver import normalize_version, parse_semver

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
        result = subprocess.run(cmd, cwd=cwd, check=False)
    except FileNotFoundError as e:
        raise PlatformInstallError(f"executable not found: {cmd[0]} ({e})") from e
    if result.returncode != 0:
        raise PlatformInstallError(f"command failed (exit {result.returncode}): {' '.join(cmd)}")


def _ensure_bare_repo() -> Path:
    """Clone the platform bare repo if missing, then refresh it (BARE_REFRESH)."""
    bare = _platform_bare_repo()
    bare.parent.mkdir(parents=True, exist_ok=True)
    if not bare.exists():
        url = SDK_GIT_URLS["platform"].removesuffix(".git")
        print(f"Cloning {url} as a bare repository into {bare}...")
        _run(["git", "clone", "--bare", url, str(bare)])
    # Refresh after a fresh clone too: the clone fills no remote-tracking refs.
    print(f"Fetching updates for {bare}...")
    _run(["git", f"--git-dir={bare}", *BARE_REFRESH])
    # A worktree directory removed by hand stays registered, and `worktree
    # add` refuses a registered path.
    _run(["git", f"--git-dir={bare}", "worktree", "prune"])
    return bare


def _upstream_ref(bare: Path, ref: str) -> str:
    """`checkout.upstream_ref`, raising PlatformInstallError."""
    try:
        return upstream_ref(bare, ref)
    except CheckoutError as e:
        raise PlatformInstallError(str(e)) from e


def _require_worktree(worktree: Path, bare: Path) -> None:
    """`checkout.require_worktree`, raising PlatformInstallError."""
    try:
        require_worktree(worktree, bare)
    except CheckoutError as e:
        raise PlatformInstallError(str(e)) from e


def _is_hex(s: str) -> bool:
    return bool(s) and all(c in "0123456789abcdef" for c in s.lower())


def _is_version(s: str) -> bool:
    """A plain version, `v0.9.0` or `0.9.0`. SEMVER_RE would let a `/` into a
    pre-release suffix, but a name with one is a ref."""
    return "/" not in s and parse_semver(s) is not None


def _resolve_platform_ref(version_or_ref: str) -> str:
    """Turn a user-supplied version or ref into the git ref to check out.

    Only a plain version names a release, so only it gets the tag infix:
    `v0.9.0` or `0.9.0` → `service/v0.9.0` (SDK_TAG_INFIXES["platform"]).
    `pr:42` → `refs/pull/42/head`. Anything else is returned as-is for git
    to resolve: a branch (`main`, `my-branch`, `release/v1.2.3`), `HEAD`, a
    namespaced tag (`service/v0.9.0`), a `refs/...` ref, or a SHA. 7-39 char
    hex might be an abbreviated SHA or a branch name; `install_platform_source`
    resolves the ambiguity via `_expand_short_sha` once the bare repo is
    available.
    """
    version_or_ref = expand_pr_shorthand(version_or_ref)
    if "/" in version_or_ref and (":" in version_or_ref or "@" in version_or_ref):
        raise PlatformInstallError(
            f"container-image refs are not supported: {version_or_ref!r}; "
            "use a git ref like v0.9.0, service/v0.9.0, main, or a SHA"
        )
    if _is_version(version_or_ref):
        infix = SDK_TAG_INFIXES.get("platform", "service")
        return f"{infix}/{normalize_version(version_or_ref)}"
    return version_or_ref


def _is_pinned(full_ref: str) -> bool:
    """True if `full_ref` names one commit for good: a full SHA, or a release
    tag `service/vX.Y.Z`.

    Only these may reuse a dist without refreshing the bare repo. Anything else
    might be a branch, whatever its name looks like (`release/v1.2.3`), and
    only origin can say.
    """
    if len(full_ref) in (40, 64) and _is_hex(full_ref):
        return True
    infix = SDK_TAG_INFIXES.get("platform", "service")
    version = full_ref.removeprefix(f"{infix}/")
    return version != full_ref and _is_version(version)


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
        check=False,
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
    """Create (or reuse) a detached git worktree at the given platform ref.

    Branch names resolve to origin's current tip via `upstream_ref`; a branch
    origin has deleted raises PlatformInstallError. For mutable refs
    (`is_mutable_target`: branches, whatever their names look like, and PR
    heads) an existing worktree is reset to that tip so a subsequent install
    picks up new commits, unless it is not a worktree of the bare repo
    (PlatformInstallError). For immutable refs (tags, SHAs) we just reuse.
    """
    bare = _ensure_bare_repo()
    # `_ensure_bare_repo` refreshes branches and tags only (BARE_REFRESH), so
    # GitHub PR refs (`refs/pull/N/head`) are never pulled. Fetch any explicit
    # `refs/...` ref by name into the bare repo so the worktree add, or the
    # reset, sees its current tip.
    if ref.startswith("refs/"):
        print(f"Fetching {ref} into bare repo...")
        _run(["git", f"--git-dir={bare}", "fetch", "origin", f"+{ref}:{ref}"])
    target = _upstream_ref(bare, ref)
    worktree = _worktree_path_for(ref)
    if worktree.exists():
        if is_mutable_target(ref, target):
            print(f"Worktree exists at {worktree}; resetting to {ref}.")
            _require_worktree(worktree, bare)
            _run(["git", "-C", str(worktree), "reset", "--hard", target])
        else:
            print(f"Worktree already exists at {worktree}; reusing.")
        return worktree
    print(f"Adding worktree at {worktree} for ref {ref}...")
    _run(["git", f"--git-dir={bare}", "worktree", "add", "--detach", str(worktree), target])
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
        ["git", "-C", str(worktree), "rev-parse", rev], capture_output=True, text=True, check=False
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

    A release or a full SHA reuses an existing dist without touching the bare
    repo, so a cached release installs offline. Anything else might be a
    branch, whatever its name looks like, so it goes through
    `_ensure_worktree`, which re-fetches the bare repo and resets the worktree
    if the ref can move; then the old dist is removed and the service binary
    is rebuilt.
    """
    full_ref = _resolve_platform_ref(ref)
    if 7 <= len(full_ref) <= 39 and _is_hex(full_ref):
        # Abbreviated SHA: resolve to full 40-char SHA so caching matches the
        # full-SHA case. Falls through to branch-name handling if git can't
        # resolve the prefix; raises on ambiguity.
        full_ref = _expand_short_sha(full_ref)
    pinned = _is_pinned(full_ref)
    if dist_name is None:
        if pinned:
            # Normalize only the semver tail so namespaced tags like
            # `service/v0.9.0` produce the same dist_name as `v0.9.0`.
            dist_name = normalize_version(full_ref.rsplit("/", 1)[-1])
        else:
            dist_name = ref_slug(full_ref)
    dist_dir = _platform_dist_root() / dist_name
    binary = dist_dir / "service"
    marker = dist_dir / ".complete"
    if binary.exists() and marker.exists() and pinned:
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
    target = _upstream_ref(bare, branch)
    scripts_dir = _platform_scripts_dir()
    worktree = _worktree_path_for(f"scripts--{branch}")
    if not worktree.exists():
        print(f"Adding scripts worktree at {worktree} ({branch})...")
        _run(["git", f"--git-dir={bare}", "worktree", "add", "--detach", str(worktree), target])
    else:
        print(f"Updating scripts worktree at {worktree}...")
        _require_worktree(worktree, bare)
        _run(["git", "-C", str(worktree), "reset", "--hard", target])
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
