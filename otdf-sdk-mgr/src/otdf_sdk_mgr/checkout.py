"""SDK source checkout using bare repos and worktrees."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from otdf_sdk_mgr.config import SDK_BARE_REPOS, SDK_GIT_URLS, get_sdk_dirs
from otdf_sdk_mgr.refs import expand_pr_shorthand, is_mutable_ref


def _run(cmd: list[str], **kwargs: Any) -> None:
    """Run a command, raising on failure with cwd and stderr in the message."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    except FileNotFoundError as e:
        raise RuntimeError(f"executable not found: {cmd[0]} ({e})") from e
    if result.returncode != 0:
        cwd = kwargs.get("cwd", "")
        cwd_str = f" (cwd={cwd})" if cwd else ""
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd,
            output=result.stdout,
            stderr=(result.stderr or "") + cwd_str,
        )


def checkout_sdk_branch(language: str, branch: str) -> str:
    """Clone bare repo and create/update a worktree for the given branch.

    Returns the slug used for the local worktree directory under
    `sdk/<lang>/src/<slug>` — callers use this as the dist-dir name and
    as the `VERSIONS=` override when invoking `make`.

    For "go", use checkout_go_from_platform instead — the standalone
    opentdf/otdfctl repo is archived; otdfctl source builds come from the
    platform monorepo.
    """
    if language == "go":
        raise ValueError(
            "checkout_sdk_branch does not support 'go'; use checkout_go_from_platform "
            "(otdfctl is now sourced from the opentdf/platform monorepo)."
        )

    sdk_dirs = get_sdk_dirs()
    if language not in sdk_dirs:
        raise ValueError(
            f"Unsupported language '{language}'. Supported values are: {', '.join(sdk_dirs)}"
        )

    branch = expand_pr_shorthand(branch)

    sdk_dir = sdk_dirs[language]
    bare_repo_name = SDK_BARE_REPOS[language]
    # Strip .git suffix to get the base URL for git clone
    repo_url = SDK_GIT_URLS[language].removesuffix(".git")

    bare_repo_path = sdk_dir / "src" / bare_repo_name
    local_name = branch.replace("/", "--")
    if local_name.startswith("sdk--"):
        local_name = local_name.removeprefix("sdk--")
    worktree_path = sdk_dir / "src" / local_name

    if not bare_repo_path.exists():
        print(f"Cloning {repo_url} as a bare repository into {bare_repo_path}...")
        _run(["git", "clone", "--bare", repo_url, str(bare_repo_path)])
    else:
        print(f"Bare repository already exists at {bare_repo_path}. Fetching updates...")
        _run(["git", f"--git-dir={bare_repo_path}", "fetch", "--all", "--tags"])

    # PR refs (`refs/pull/N/head`) aren't in the default bare-clone refspec;
    # fetch any explicit `refs/...` ref by name so worktree-add can find it.
    if branch.startswith("refs/"):
        print(f"Fetching {branch} into bare repo...")
        _run(
            [
                "git",
                f"--git-dir={bare_repo_path}",
                "fetch",
                "origin",
                f"+{branch}:{branch}",
            ]
        )

    if worktree_path.exists():
        if is_mutable_ref(branch):
            print(f"Worktree exists at {worktree_path}; resetting to '{branch}'.")
            # Worktrees from a bare clone have no `origin` remote, so reset
            # to the just-fetched ref in the bare repo instead of `git pull`.
            _run(["git", "-C", str(worktree_path), "fetch", "origin", branch])
            _run(["git", "-C", str(worktree_path), "reset", "--hard", "FETCH_HEAD"])
        else:
            print(f"Worktree for '{branch}' already exists at {worktree_path}; reusing.")
    else:
        print(f"Setting up worktree for branch '{branch}' at {worktree_path}...")
        _run(
            [
                "git",
                f"--git-dir={bare_repo_path}",
                "worktree",
                "add",
                str(worktree_path),
                branch,
            ]
        )
    return local_name


def checkout_go_from_platform(ref: str) -> Path:
    """Check out the opentdf/platform monorepo and arrange xtest/sdk/go/src/<slug>
    as a symlink to the otdfctl subdir of that checkout.

    Returns the platform checkout directory so callers can locate go.work for
    GOWORK-based source builds. The slug (`Path.name` of the worktree dir) is
    also the dist-dir name used by the go SDK Makefile.

    Accepts `pr:N` shorthand in addition to branches, tags, and SHAs.
    """
    ref = expand_pr_shorthand(ref)

    go_dir = get_sdk_dirs()["go"]
    platform_url = SDK_GIT_URLS["platform"].removesuffix(".git")
    platform_src_dir = go_dir / "platform-src"
    bare_repo_path = platform_src_dir / "platform.git"

    local_name = ref.replace("/", "--").removeprefix("otdfctl--")
    worktree_path = platform_src_dir / local_name
    src_link = go_dir / "src" / local_name

    platform_src_dir.mkdir(parents=True, exist_ok=True)

    if not bare_repo_path.exists():
        print(f"Cloning {platform_url} as a bare repository into {bare_repo_path}...")
        _run(["git", "clone", "--bare", platform_url, str(bare_repo_path)])
    else:
        print(f"Bare repository already exists at {bare_repo_path}. Fetching updates...")
        _run(["git", f"--git-dir={bare_repo_path}", "fetch", "--all", "--tags"])

    # PR refs (`refs/pull/N/head`) aren't in the default bare-clone refspec;
    # fetch any explicit `refs/...` ref by name so worktree-add can find it.
    if ref.startswith("refs/"):
        print(f"Fetching {ref} into bare repo...")
        _run(
            [
                "git",
                f"--git-dir={bare_repo_path}",
                "fetch",
                "origin",
                f"+{ref}:{ref}",
            ]
        )

    if worktree_path.exists():
        if is_mutable_ref(ref):
            print(f"Worktree for ref '{ref}' exists at {worktree_path}; resetting.")
            _run(["git", f"--git-dir={bare_repo_path}", "fetch", "origin", ref, "--tags"])
            _run(["git", "-C", str(worktree_path), "checkout", "--force", "FETCH_HEAD"])
        else:
            print(f"Worktree for ref '{ref}' already exists at {worktree_path}; reusing.")
    else:
        print(f"Setting up worktree for ref '{ref}' at {worktree_path}...")
        _run(
            [
                "git",
                f"--git-dir={bare_repo_path}",
                "worktree",
                "add",
                str(worktree_path),
                ref,
            ]
        )

    otdfctl_dir = worktree_path / "otdfctl"
    if not otdfctl_dir.is_dir():
        raise RuntimeError(
            f"Platform checkout at {worktree_path} has no otdfctl/ directory; "
            f"ref '{ref}' predates the otdfctl monorepo migration (v0.31.0)."
        )

    src_link.parent.mkdir(parents=True, exist_ok=True)
    if src_link.is_symlink():
        src_link.unlink()
    elif src_link.exists():
        if src_link.is_dir():
            shutil.rmtree(src_link)
        else:
            src_link.unlink()
    src_link.symlink_to(Path("..") / "platform-src" / local_name / "otdfctl")
    print(f"Symlinked {src_link} → {otdfctl_dir}")

    return worktree_path
