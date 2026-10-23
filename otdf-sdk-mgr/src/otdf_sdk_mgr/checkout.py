"""SDK source checkout using bare repos and worktrees."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from otdf_sdk_mgr.config import SDK_BARE_REPOS, SDK_GIT_URLS, get_sdk_dirs
from otdf_sdk_mgr.refs import expand_pr_shorthand, is_mutable_target

# `git clone --bare` records no fetch refspec: `git fetch` alone updates no refs
# and `--tags` adds only tags, so the bare repo's branches stay where the clone
# left them. Fetch origin's branches into remote-tracking refs instead. No
# worktree has those checked out, and `--prune` deletes the ones origin dropped,
# so `upstream_ref` can tell a deleted branch from a live one and an `x` → `x/y`
# rename doesn't collide. `--force` lets `--tags` move a tag that origin
# re-created on another commit, as after a botched release; git 2.20+ otherwise
# rejects it ("would clobber existing tag") and fails the whole fetch. Forcing a
# `+refs/tags/*:refs/tags/*` refspec instead would put tags under `--prune`,
# which `--tags` exempts, and delete the ones origin dropped as well.
BARE_REFRESH = [
    "fetch",
    "--prune",
    "--tags",
    "--force",
    "origin",
    "+refs/heads/*:refs/remotes/origin/*",
]


class CheckoutError(ValueError):
    """A ref can't be checked out from a bare repo."""


def _run(cmd: list[str], **kwargs: Any) -> None:
    """Run a command, raising on failure with cwd and stderr in the message."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)
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


def _has_ref(git_dir: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", "show-ref", "--verify", "--quiet", ref], check=False
    )
    return result.returncode == 0


def upstream_ref(git_dir: Path, ref: str) -> str:
    """Name what to check out for `ref` from a bare repo refreshed by BARE_REFRESH.

    A branch name resolves to origin's copy, `refs/remotes/origin/<ref>`, which
    wins over a tag of the same name; the bare repo's own branches date from
    the clone. `HEAD` resolves to the branch the bare repo's HEAD names.
    `refs/...` refs, tags, SHAs and unknown names pass through for git to
    resolve. Raises CheckoutError when `ref` matches only a clone-time local
    branch, i.e. origin has since deleted it, rather than check out that stale
    copy.
    """
    if ref.startswith("refs/"):
        return ref
    if ref == "HEAD":
        # `git clone` pointed the bare repo's HEAD at origin's default branch
        # as of the clone; BARE_REFRESH doesn't update it. Not `--short`: with
        # a tag of the same name that gives `heads/main`, which matches no
        # check below and would check out the stale local branch.
        result = subprocess.run(
            ["git", f"--git-dir={git_dir}", "symbolic-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise CheckoutError(f"cannot resolve HEAD in {git_dir}: {result.stderr.strip()}")
        ref = result.stdout.strip().removeprefix("refs/heads/")
    tracking = f"refs/remotes/origin/{ref}"
    if _has_ref(git_dir, tracking):
        return tracking
    if _has_ref(git_dir, f"refs/heads/{ref}") and not _has_ref(git_dir, f"refs/tags/{ref}"):
        raise CheckoutError(
            f"branch '{ref}' is not on origin; {git_dir} has only a local copy, which may be stale"
        )
    return ref


def require_worktree(worktree: Path, bare_repo: Path) -> None:
    """Raise CheckoutError unless `worktree` is a git worktree of `bare_repo`.

    Worktrees live inside the opentdf/tests checkout. In one that has lost its
    `.git` file, git climbs to that checkout, and a `reset --hard` meant for
    the worktree throws away the developer's uncommitted work instead.
    GIT_CEILING_DIRECTORIES stops the climb. Comparing the common dir refuses
    a directory that belongs to some other repo, such as a clone made by hand.
    """
    result = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(worktree.resolve().parent)},
    )
    # Relative to the worktree when git prints it relative (`.git` in a clone);
    # not `--path-format=absolute`, which needs git 2.31.
    common_dir = (worktree / result.stdout.strip()).resolve()
    if result.returncode != 0 or common_dir != bare_repo.resolve():
        raise CheckoutError(
            f"{worktree} is not a git worktree of {bare_repo}; remove it and rerun to recreate it"
        )


def _commit(worktree: Path, rev: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def needs_reset(worktree: Path, ref: str, target: str) -> bool:
    """Whether to `reset --hard` an existing worktree of `ref` to `target`.

    Call require_worktree first, or git may answer for the enclosing checkout.
    A ref that can move (`is_mutable_target`) is always reset. So is a tag
    that origin re-created on another commit: builds run on whatever the
    worktree holds, so reuse would build the old commit under the tag's name.
    BARE_REFRESH has already fetched the tag, so comparing costs no network,
    and a SHA never differs from itself. A target that names no commit, such
    as a version-named branch origin deleted, counts as moved, so the reset
    fails on it instead of the worktree being reused.
    """
    if is_mutable_target(ref, target):
        return True
    head = _commit(worktree, "HEAD")
    return head is None or head != _commit(worktree, target)


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
    # Refresh after a fresh clone too: the clone fills no remote-tracking refs.
    print(f"Fetching updates into {bare_repo_path}...")
    _run(["git", f"--git-dir={bare_repo_path}", *BARE_REFRESH])
    # A worktree directory removed by hand, or by `otdf-sdk-mgr clean`, stays
    # registered, and `worktree add` refuses a registered path.
    _run(["git", f"--git-dir={bare_repo_path}", "worktree", "prune"])

    # PR refs (`refs/pull/N/head`) aren't under refs/heads/, so BARE_REFRESH
    # skips them; fetch any explicit `refs/...` ref by name so worktree-add,
    # or the reset below, sees its current tip.
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
    target = upstream_ref(bare_repo_path, branch)

    if worktree_path.exists():
        require_worktree(worktree_path, bare_repo_path)
        if needs_reset(worktree_path, branch, target):
            print(f"Worktree exists at {worktree_path}; resetting to '{branch}'.")
            _run(["git", "-C", str(worktree_path), "reset", "--hard", target])
        else:
            print(f"Worktree for '{branch}' already exists at {worktree_path}; reusing.")
    else:
        print(f"Setting up worktree for branch '{branch}' at {worktree_path}...")
        # Detached: worktrees never own a branch, so two can follow the same
        # one, and a name that is both a stale clone-time branch and a tag
        # checks out the tag.
        _run(
            [
                "git",
                f"--git-dir={bare_repo_path}",
                "worktree",
                "add",
                "--detach",
                str(worktree_path),
                target,
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
    # Refresh after a fresh clone too: the clone fills no remote-tracking refs.
    print(f"Fetching updates into {bare_repo_path}...")
    _run(["git", f"--git-dir={bare_repo_path}", *BARE_REFRESH])
    # A worktree directory removed by hand stays registered, and `worktree
    # add` refuses a registered path.
    _run(["git", f"--git-dir={bare_repo_path}", "worktree", "prune"])

    # PR refs (`refs/pull/N/head`) aren't under refs/heads/, so BARE_REFRESH
    # skips them; fetch any explicit `refs/...` ref by name so worktree-add,
    # or the reset below, sees its current tip.
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
    target = upstream_ref(bare_repo_path, ref)

    if worktree_path.exists():
        require_worktree(worktree_path, bare_repo_path)
        if needs_reset(worktree_path, ref, target):
            print(f"Worktree for ref '{ref}' exists at {worktree_path}; resetting.")
            _run(["git", "-C", str(worktree_path), "reset", "--hard", target])
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
                "--detach",
                str(worktree_path),
                target,
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
