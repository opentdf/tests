"""Git-ref helpers shared by platform and SDK installers."""

from __future__ import annotations

import re

from otdf_sdk_mgr.semver import SEMVER_RE

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
    if SEMVER_RE.match(tail):
        return False
    return True


def ref_slug(ref: str) -> str:
    """Slugify a git ref for use as a directory name.

    Mirrors the pattern already used by `_worktree_path_for` and
    `checkout_sdk_branch`: replace `/` with `--`. Idempotent.
    """
    return ref.replace("/", "--")


def dist_slug(ref: str) -> str:
    """Normalize a ref to a dist/ directory name.

    Flattens slashes and strips namespace prefixes, matching what `cmd_tip`
    passes as `VERSIONS=` and therefore what the Makefile actually creates.

    This is the one slug function for dist paths. `ref_slug` above flattens
    only and `normalize_version` only adds a leading `v`, so reaching for
    either here reintroduces the collision between `otdfctl/v0.24.0` and
    `v0.24.0` that `check_collision` exists to catch.

    Examples:
        "main" → "main"
        "otdfctl/v0.24.0" → "v0.24.0"
        "sdk/v1.2.3" → "v1.2.3"
        "refs/pull/123/head" → "refs--pull--123--head"
    """
    slug = ref.replace("/", "--")
    slug = slug.removeprefix("sdk--")
    slug = slug.removeprefix("otdfctl--")
    return slug
