"""Tests for the ref-handling helpers."""

import pytest

from otdf_sdk_mgr.refs import expand_pr_shorthand, is_mutable_ref, ref_slug


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("pr:42", "refs/pull/42/head"),
        ("pr:1", "refs/pull/1/head"),
        ("pr:12345", "refs/pull/12345/head"),
        ("main", "main"),
        ("v0.9.0", "v0.9.0"),
        ("feature/pr-42", "feature/pr-42"),  # `/` disambiguates from shorthand
        ("refs/pull/42/head", "refs/pull/42/head"),
        ("pr:abc", "pr:abc"),  # non-numeric, not shorthand
        ("", ""),
    ],
)
def test_expand_pr_shorthand(inp, expected):
    assert expand_pr_shorthand(inp) == expected


@pytest.mark.parametrize(
    "ref,expected",
    [
        # Immutable: tags and tag-like refs
        ("v0.9.0", False),
        ("v1.2.3", False),
        ("service/v0.9.0", False),
        ("sdk/v0.4.0", False),
        ("otdfctl/v0.31.0", False),
        # Immutable: SHAs
        ("a" * 40, False),
        ("b" * 64, False),
        ("0123456789abcdef0123456789abcdef01234567", False),
        # Mutable: branches and PR heads
        ("main", True),
        ("HEAD", True),
        ("feature/my-branch", True),
        ("DSPX-3302-02-platform-installer", True),
        ("refs/pull/42/head", True),
        # Mutable: short hex (could be a SHA, but also could be a branch);
        # treated as mutable since it's not full-length.
        ("abc1234", True),
    ],
)
def test_is_mutable_ref(ref, expected):
    assert is_mutable_ref(ref) is expected


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("main", "main"),
        ("feature/x", "feature--x"),
        ("refs/pull/42/head", "refs--pull--42--head"),
        ("service/v0.9.0", "service--v0.9.0"),
        ("a" * 40, "a" * 40),
    ],
)
def test_ref_slug(inp, expected):
    assert ref_slug(inp) == expected
