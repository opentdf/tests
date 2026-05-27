"""Pure-function tests for platform_installer."""

import pytest

from otdf_sdk_mgr.platform_installer import _resolve_platform_ref
from otdf_sdk_mgr.refs import is_mutable_ref, ref_slug
from otdf_sdk_mgr.semver import normalize_version


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("v0.9.0", "service/v0.9.0"),
        ("0.9.0", "service/v0.9.0"),
        ("main", "main"),
        ("HEAD", "HEAD"),
        ("service/v0.9.0", "service/v0.9.0"),
        ("a" * 40, "a" * 40),
        ("b" * 64, "b" * 64),
        ("abc1234", "service/vabc1234"),
        ("deadbeef", "service/vdeadbeef"),
        # PR shorthand expands before the `/` check, then passes through.
        ("pr:42", "refs/pull/42/head"),
        ("pr:1234", "refs/pull/1234/head"),
        # Raw refs are passed through unchanged.
        ("refs/pull/7/head", "refs/pull/7/head"),
    ],
)
def test_resolve_platform_ref(inp, expected):
    assert _resolve_platform_ref(inp) == expected


@pytest.mark.parametrize(
    "ref,expected_dist_name",
    [
        # Immutable refs: namespaced tags and plain tags should produce the same dist_name
        ("service/v0.9.0", "v0.9.0"),
        ("v0.9.0", "v0.9.0"),
        ("0.9.0", "v0.9.0"),
        # Mutable refs: use ref_slug
        ("main", "main"),
        ("refs/pull/42/head", "refs--pull--42--head"),
        # SHAs: immutable, normalize the tail (which is the full SHA)
        ("a" * 40, "v" + "a" * 40),
    ],
)
def test_dist_name_derivation(ref, expected_dist_name):
    """Verify that dist_name is derived consistently for immutable refs.

    Namespaced tags like `service/v0.9.0` should produce the same dist_name as
    plain tags `v0.9.0` or `0.9.0`, ensuring immutable refs reuse existing dist dirs.
    """
    full_ref = _resolve_platform_ref(ref)
    if is_mutable_ref(full_ref):
        dist_name = ref_slug(full_ref)
    else:
        # Normalize only the semver tail for immutable refs
        dist_name = normalize_version(full_ref.rsplit("/", 1)[-1])
    assert dist_name == expected_dist_name
