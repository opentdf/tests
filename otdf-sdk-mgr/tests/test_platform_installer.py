"""Pure-function tests for platform_installer."""

import pytest

from otdf_sdk_mgr.platform_installer import _resolve_platform_ref


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
