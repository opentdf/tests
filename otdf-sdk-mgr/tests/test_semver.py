"""Tests for semver.py — pure functions, no mocking needed."""

from otdf_sdk_mgr.semver import is_stable, normalize_version, parse_semver, semver_sort_key


class TestParseSemver:
    def test_basic(self):
        assert parse_semver("1.2.3") == (1, 2, 3, None)

    def test_v_prefix(self):
        assert parse_semver("v1.2.3") == (1, 2, 3, None)

    def test_pre_release(self):
        assert parse_semver("1.2.3-beta.1") == (1, 2, 3, "beta.1")

    def test_zeros(self):
        assert parse_semver("0.0.0") == (0, 0, 0, None)

    def test_build_metadata_only(self):
        # build metadata is parsed but discarded; pre stays None
        assert parse_semver("1.2.3+build.1") == (1, 2, 3, None)

    def test_pre_and_build(self):
        assert parse_semver("1.2.3-pre+build") == (1, 2, 3, "pre")

    def test_invalid_branch(self):
        assert parse_semver("main") is None

    def test_invalid_empty(self):
        assert parse_semver("") is None

    def test_invalid_partial(self):
        assert parse_semver("v1.2") is None

    def test_invalid_alpha(self):
        assert parse_semver("abc") is None


class TestIsStable:
    def test_stable(self):
        assert is_stable("1.2.3") is True

    def test_v_stable(self):
        assert is_stable("v1.2.3") is True

    def test_pre_release(self):
        assert is_stable("1.2.3-beta.1") is False

    def test_rc(self):
        assert is_stable("1.2.3-rc.1") is False

    def test_build_metadata_only_is_stable(self):
        # build metadata does not make a version pre-release
        assert is_stable("1.2.3+build.42") is True

    def test_non_semver(self):
        assert is_stable("main") is False

    def test_empty(self):
        assert is_stable("") is False


class TestSemverSortKey:
    def test_pre_before_stable_same_version(self):
        pre = semver_sort_key("1.2.3-alpha")
        stable = semver_sort_key("1.2.3")
        assert pre < stable

    def test_cross_version_ordering(self):
        assert semver_sort_key("1.0.0") < semver_sort_key("2.0.0")
        assert semver_sort_key("1.2.3") < semver_sort_key("1.2.4")
        assert semver_sort_key("1.9.0") < semver_sort_key("1.10.0")

    def test_non_semver_fallback(self):
        key = semver_sort_key("main")
        assert key == (0, 0, 0, 0, "main")

    def test_build_metadata_ignored_for_ordering(self):
        # 1.2.3+build should sort same as 1.2.3 (both stable, same version)
        assert semver_sort_key("1.2.3+build") == semver_sort_key("1.2.3")


class TestNormalizeVersion:
    def test_adds_v_prefix(self):
        assert normalize_version("1.2.3") == "v1.2.3"

    def test_preserves_v_prefix(self):
        assert normalize_version("v1.2.3") == "v1.2.3"

    def test_strips_whitespace(self):
        assert normalize_version("  1.2.3  ") == "v1.2.3"
