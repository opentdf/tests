"""Tests for resolve.py — mocks git.Git to avoid network calls."""

from typing import cast
from unittest.mock import MagicMock, patch

from otdf_sdk_mgr.resolve import (
    ResolveResult,
    _try_resolve_js_npm,
    is_resolve_error,
    is_resolve_success,
    resolve,
)

SHA40 = "a" * 40
SHA64 = "b" * 64
SHA7 = "c" * 7


# A realistic ls_remote output (tab-separated "sha\tref" per line)
def make_ls_remote(*entries):
    """Build a ls_remote string from (sha, ref) pairs."""
    return "\n".join(f"{sha}\t{ref}" for sha, ref in entries)


def patch_git(ls_remote_output):
    mock_git = MagicMock()
    mock_git.ls_remote.return_value = ls_remote_output
    return patch("otdf_sdk_mgr.resolve.Git", return_value=mock_git)


# ---------------------------------------------------------------------------
# Type guards
# ---------------------------------------------------------------------------


class TestTypeGuards:
    def test_is_resolve_error(self):
        err = cast(ResolveResult, {"sdk": "go", "alias": "x", "err": "oops"})
        assert is_resolve_error(err) is True
        assert is_resolve_success(err) is False

    def test_is_resolve_success(self):
        ok = cast(ResolveResult, {"sdk": "go", "alias": "x", "sha": SHA40, "tag": "v1.0.0"})
        assert is_resolve_success(ok) is True
        assert is_resolve_error(ok) is False


# ---------------------------------------------------------------------------
# resolve() — "main"
# ---------------------------------------------------------------------------


class TestResolveMain:
    def test_main_returns_head(self):
        ls = make_ls_remote((SHA40, "refs/heads/main"))
        with patch_git(ls):
            result = resolve("go", "main", None)
        assert is_resolve_success(result)
        assert result.get("head") is True
        assert result["tag"] == "main"
        assert result["sha"] == SHA40

    def test_refs_heads_main_alias(self):
        ls = make_ls_remote((SHA40, "refs/heads/main"))
        with patch_git(ls):
            result = resolve("go", "refs/heads/main", None)
        assert is_resolve_success(result)
        assert result["tag"] == "main"


# ---------------------------------------------------------------------------
# resolve() — SHA inputs
# ---------------------------------------------------------------------------


class TestResolveSHA:
    def test_sha_no_matches_returns_sha_as_tag(self):
        ls = make_ls_remote(("d" * 40, "refs/heads/other"))
        with patch_git(ls):
            result = resolve("go", SHA7, None)
        assert is_resolve_success(result)
        assert result["sha"] == SHA7
        assert result["tag"] == SHA7

    def test_sha1_short_matches(self):
        ls = make_ls_remote((SHA40, "refs/tags/v1.0.0"))
        with patch_git(ls):
            result = resolve("go", SHA7, None)
        # SHA7 = "ccc..." but SHA40 = "aaa..." so no match; override for this test
        ls2 = make_ls_remote((SHA7 + "0" * 33, "refs/tags/v1.0.0"))
        with patch_git(ls2):
            result = resolve("go", SHA7, None)
        assert is_resolve_success(result)
        assert result["tag"] == "v1.0.0"

    def test_sha1_full_matches(self):
        ls = make_ls_remote((SHA40, "refs/tags/v2.0.0"))
        with patch_git(ls):
            result = resolve("go", SHA40, None)
        assert is_resolve_success(result)
        assert result["tag"] == "v2.0.0"

    def test_sha256_full_matches(self):
        ls = make_ls_remote((SHA64, "refs/tags/v3.0.0"))
        with patch_git(ls):
            result = resolve("go", SHA64, None)
        assert is_resolve_success(result)
        assert result["tag"] == "v3.0.0"

    def test_single_match_strips_refs_tags(self):
        ls = make_ls_remote((SHA40, "refs/tags/v1.2.3"))
        with patch_git(ls):
            result = resolve("go", SHA40, None)
        assert is_resolve_success(result)
        assert result["tag"] == "v1.2.3"

    def test_multiple_matches_pr_takes_priority(self):
        ls = make_ls_remote(
            (SHA40, "refs/pull/99/head"),
            (SHA40, "refs/heads/some-branch"),
        )
        with patch_git(ls):
            result = resolve("go", SHA40, None)
        assert is_resolve_success(result)
        assert result["tag"] == "pull-99"

    def test_multiple_matches_merge_queue(self):
        mq_ref = f"refs/heads/gh-readonly-queue/main/pr-42-{SHA40}"
        ls = make_ls_remote(
            (SHA40, mq_ref),
            (SHA40, "refs/heads/main"),
        )
        with patch_git(ls):
            result = resolve("go", SHA40, None)
        assert is_resolve_success(result)
        assert result["tag"] == "mq-main-42"
        assert result.get("pr") == "42"

    def test_multiple_matches_branch_only(self):
        ls = make_ls_remote(
            (SHA40, "refs/heads/feature/my-branch"),
            (SHA40, "refs/heads/main"),
        )
        with patch_git(ls):
            result = resolve("go", SHA40, None)
        assert is_resolve_success(result)
        assert result.get("head") is True
        assert result["tag"] == "feature--my-branch"


# ---------------------------------------------------------------------------
# resolve() — refs/pull/NNN
# ---------------------------------------------------------------------------


class TestResolvePR:
    def test_pr_found(self):
        # The code filters rows where r.endswith(version), so the ref must end with "refs/pull/123"
        ls = make_ls_remote((SHA40, "refs/pull/123"))
        with patch_git(ls):
            result = resolve("go", "refs/pull/123", None)
        assert is_resolve_success(result)
        assert result.get("pr") == "123"
        assert result["tag"] == "pull-123"
        assert result.get("head") is True

    def test_pr_not_found(self):
        ls = make_ls_remote((SHA40, "refs/heads/main"))
        with patch_git(ls):
            result = resolve("go", "refs/pull/999", None)
        assert is_resolve_error(result)


# ---------------------------------------------------------------------------
# resolve() — branch name
# ---------------------------------------------------------------------------


class TestResolveBranch:
    def test_exact_branch_match(self):
        ls = make_ls_remote(
            (SHA40, "refs/heads/my-feature"),
            (SHA40, "refs/heads/main"),
        )
        with patch_git(ls):
            result = resolve("go", "my-feature", None)
        assert is_resolve_success(result)
        assert result.get("head") is True
        assert result["tag"] == "my-feature"


# ---------------------------------------------------------------------------
# resolve() — version tags
# ---------------------------------------------------------------------------


class TestResolveVersionTags:
    def test_exact_stable_version(self):
        ls = make_ls_remote(
            (SHA40, "refs/tags/v0.3.5"),
            ("0" * 40, "refs/tags/v0.3.4"),
        )
        with patch_git(ls):
            result = resolve("go", "v0.3.5", None)
        assert is_resolve_success(result)
        assert result["tag"] == "v0.3.5"
        assert result["sha"] == SHA40

    def test_pre_release_version_fallback(self):
        ls = make_ls_remote(
            (SHA40, "refs/tags/v0.3.5-beta.1"),
        )
        with patch_git(ls):
            result = resolve("go", "v0.3.5-beta.1", None)
        assert is_resolve_success(result)
        assert result["tag"] == "v0.3.5-beta.1"

    def test_lts_resolves_to_config_version(self):
        from otdf_sdk_mgr.config import LTS_VERSIONS

        lts_ver = LTS_VERSIONS["go"]
        ls = make_ls_remote(
            (SHA40, f"refs/tags/v{lts_ver}"),
        )
        with patch_git(ls):
            result = resolve("go", "lts", None)
        assert is_resolve_success(result)
        assert result["tag"] in [lts_ver, f"v{lts_ver}"]

    def test_lts_unknown_sdk_raises(self):
        # SDK not in SDK_GIT_URLS → KeyError, caught → ResolveError
        result = resolve("unknownsdk", "lts", None)
        assert is_resolve_error(result)


# ---------------------------------------------------------------------------
# resolve() — "latest"
# ---------------------------------------------------------------------------


class TestResolveLatest:
    def test_non_java_returns_last_stable(self):
        ls = make_ls_remote(
            ("1" * 40, "refs/tags/v0.1.0"),
            ("2" * 40, "refs/tags/v0.2.0"),
            ("3" * 40, "refs/tags/v0.3.0"),
        )
        with patch_git(ls):
            result = resolve("go", "latest", None)
        assert is_resolve_success(result)
        assert result["tag"] == "v0.3.0"

    def test_java_with_cli_available(self):
        ls = make_ls_remote(
            ("1" * 40, "refs/tags/v0.1.0"),
            ("2" * 40, "refs/tags/v0.2.0"),
        )
        mock_releases = [
            {"version": "v0.1.0", "has_cli": False},
            {"version": "v0.2.0", "has_cli": True},
        ]
        with (
            patch_git(ls),
            patch("otdf_sdk_mgr.registry.list_java_github_releases", return_value=mock_releases),
        ):
            result = resolve("java", "latest", None)
        assert is_resolve_success(result)
        assert result["tag"] == "v0.2.0"

    def test_java_no_cli_available_falls_back_to_source(self):
        ls = make_ls_remote(
            ("1" * 40, "refs/tags/v0.1.0"),
            ("2" * 40, "refs/tags/v0.2.0"),
        )
        mock_releases = [
            {"version": "v0.1.0", "has_cli": False},
            {"version": "v0.2.0", "has_cli": False},
        ]
        with (
            patch_git(ls),
            patch("otdf_sdk_mgr.registry.list_java_github_releases", return_value=mock_releases),
        ):
            result = resolve("java", "latest", None)
        assert is_resolve_success(result)
        assert result.get("head") is True


# ---------------------------------------------------------------------------
# _try_resolve_js_npm()
# ---------------------------------------------------------------------------


class TestTryResolveJsNpm:
    def test_npm_concrete_version(self):
        tags = [(SHA40, "v1.2.3"), ("0" * 40, "v1.2.2")]
        with patch("otdf_sdk_mgr.registry.fetch_json", return_value={"version": "1.2.3"}):
            result = _try_resolve_js_npm("js", "1.2.3", "1.2.3", tags, None)
        assert result is not None
        assert result["tag"] == "1.2.3"
        assert result["sha"] == SHA40

    def test_npm_dist_tag_resolved(self):
        tags = [(SHA40, "v0.9.0")]
        with patch("otdf_sdk_mgr.registry.fetch_json", return_value={"version": "0.9.0"}):
            result = _try_resolve_js_npm("js", "next", "next", tags, None)
        assert result is not None
        assert result["tag"] == "0.9.0"
        assert result["sha"] == SHA40

    def test_npm_raises_returns_none(self):
        with patch("otdf_sdk_mgr.registry.fetch_json", side_effect=Exception("network error")):
            result = _try_resolve_js_npm("js", "1.2.3", "1.2.3", [], None)
        assert result is None

    def test_unknown_sdk_returns_none(self):
        result = _try_resolve_js_npm("go", "1.2.3", "1.2.3", [], None)
        assert result is None
