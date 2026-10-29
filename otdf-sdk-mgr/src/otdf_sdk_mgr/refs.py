"""Git-ref helpers and a typed `git ls-remote` wrapper used across otdf-sdk-mgr."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from otdf_sdk_mgr.semver import SEMVER_RE

if TYPE_CHECKING:
    from git import Git

_PR_SHORTHAND_RE = re.compile(r"^pr:(\d+)$")
_HEX_SHA_LEN = (40, 64)


def expand_pr_shorthand(ref: str) -> str:
    """Expand `pr:N` (GitHub PR shorthand) to `refs/pull/N/head`.

    Other refs pass through unchanged.
    """
    m = _PR_SHORTHAND_RE.match(ref)
    if m:
        return f"refs/pull/{m.group(1)}/head"
    return ref


def is_mutable_ref(ref: str) -> bool:
    """True if `ref` can change over time (branches, PR heads); False for tags/SHAs.

    Used to decide whether to re-fetch and rebuild on subsequent installs.

    The caller is expected to have already expanded `pr:N` shorthand and any
    tag-namespace prefixes (e.g. `service/v0.9.0`, `sdk/v0.4.0`).
    """
    if len(ref) in _HEX_SHA_LEN and all(c in "0123456789abcdef" for c in ref.lower()):
        return False
    # Namespaced tag refs from monorepo: `service/v0.9.0`, `sdk/v0.4.0`,
    # `otdfctl/v0.31.0`. Anything ending in a clean semver after the last
    # `/` is treated as an immutable tag.
    tail = ref.rsplit("/", 1)[-1]
    return not SEMVER_RE.match(tail)


def ref_slug(ref: str) -> str:
    """Slugify a git ref for use as a directory name.

    Mirrors the pattern already used by `_worktree_path_for` and
    `checkout_sdk_branch`: replace `/` with `--`. Idempotent.
    """
    return ref.replace("/", "--")


def git_ls_remote(
    repo: Git, url: str, *patterns: str, heads: bool = False, tags: bool = False
) -> str:
    """Run `git ls-remote [--heads] [--tags] <url> [<patterns>...]`; return stdout.

    Only narrows the type. GitPython >= 3.1.51 annotates `Git.ls_remote`
    with every shape `Git.execute` can return (bytes, an extended-output
    tuple, a process handle), but without `execute` options it is always a
    `str`. The signature admits no such options, so the cast holds.

    `repo` comes from the caller so tests that patch the caller's `Git`
    (e.g. `otdf_sdk_mgr.resolve.Git`) still intercept the call.
    """
    return cast("str", repo.ls_remote(url, *patterns, heads=heads, tags=tags))


def dist_slug(ref: str) -> str:
    """Normalize a ref to a dist/ directory name.

    Flattens slashes and strips namespace prefixes, matching what `cmd_tip`
    passes as `VERSIONS=` and therefore what the Makefile actually creates.

    `cmd_tip` names its build directory with this and `dist_slug_for`
    predicts that directory with it, so the two cannot drift apart. `ref_slug`
    above flattens only, and `normalize_version` only trims whitespace and
    leading `v`s and adds one `v` back: predicting with either would give
    `sdk/feature` and `feature` different names, hiding from `check_collision`
    that both build into `dist/feature`.

    Examples:
        "main" → "main"
        "otdfctl/v0.24.0" → "v0.24.0"
        "sdk/v1.2.3" → "v1.2.3"
        "refs/pull/123/head" → "refs--pull--123--head"

    Raises:
        ValueError: if nothing nameable is left, as for `sdk/` or `otdfctl/..`:
            `dist/`, `dist/.` and `dist/..` are not a build directory.
    """
    slug = ref.replace("/", "--")
    slug = slug.removeprefix("sdk--")
    slug = slug.removeprefix("otdfctl--")
    if slug in ("", ".", ".."):
        raise ValueError(f"ref {ref!r} names no dist/ directory")
    return slug
