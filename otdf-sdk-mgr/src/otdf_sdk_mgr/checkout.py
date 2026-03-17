"""SDK source checkout using bare repos and worktrees."""

from __future__ import annotations

import subprocess
from typing import Any

from otdf_sdk_mgr.config import SDK_BARE_REPOS, SDK_GIT_URLS, get_sdk_dirs


def _run(cmd: list[str], **kwargs: Any) -> None:
    """Run a command, raising on failure."""
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)


def checkout_sdk_branch(language: str, branch: str) -> None:
    """Clone bare repo and create/update a worktree for the given branch."""
    sdk_dirs = get_sdk_dirs()
    if language not in sdk_dirs:
        raise ValueError(
            f"Unsupported language '{language}'. Supported values are: {', '.join(sdk_dirs)}"
        )

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
        _run(["git", f"--git-dir={bare_repo_path}", "fetch", "--all"])

    if worktree_path.exists():
        print(f"Worktree for branch '{branch}' already exists at {worktree_path}. Updating...")
        _run(["git", "-C", str(worktree_path), "pull", "origin", branch])
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
