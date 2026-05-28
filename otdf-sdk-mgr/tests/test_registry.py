"""Tests for the registry module."""

from __future__ import annotations

import urllib.error

import pytest

from otdf_sdk_mgr import registry
from otdf_sdk_mgr.registry import (
    RegistryUnreachableError,
    _github_headers,
    list_java_github_releases,
    list_java_maven_versions,
    list_js_versions,
    list_platform_versions,
)


def test_github_headers_without_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    h = _github_headers()
    assert h == {"Accept": "application/json"}


def test_github_headers_with_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-123")
    h = _github_headers()
    assert h["Authorization"] == "Bearer fake-token-123"
    assert h["Accept"] == "application/json"


def test_list_js_versions_raises_on_network_error(monkeypatch: pytest.MonkeyPatch):
    def boom(_url: str):
        raise urllib.error.URLError("nodename nor servname provided")

    monkeypatch.setattr(registry, "fetch_json", boom)
    with pytest.raises(RegistryUnreachableError, match="npm registry"):
        list_js_versions()


def test_list_java_maven_versions_raises_on_network_error(monkeypatch: pytest.MonkeyPatch):
    def boom(_url: str):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(registry, "fetch_text", boom)
    with pytest.raises(RegistryUnreachableError, match="Maven metadata"):
        list_java_maven_versions()


def test_list_java_github_releases_raises_on_network_error(monkeypatch: pytest.MonkeyPatch):
    def boom(_url: str):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(registry, "fetch_json", boom)
    with pytest.raises(RegistryUnreachableError, match="GitHub releases"):
        list_java_github_releases()


def test_list_platform_versions_parses_ls_remote(monkeypatch: pytest.MonkeyPatch):
    """Verify tag parsing: skip peeled `^{}`, filter to `service/` infix, drop non-semver."""
    raw = "\n".join(
        [
            "deadbeef\trefs/tags/service/v0.9.0",
            "deadbef0\trefs/tags/service/v0.9.0^{}",
            "deadbef1\trefs/tags/service/v0.10.0-rc1",
            "deadbef2\trefs/tags/otdfctl/v0.31.0",  # different infix — skip
            "deadbef3\trefs/tags/service/not-a-version",  # not semver — skip
            "deadbef4\trefs/heads/main",  # not a tag — skip
        ]
    )

    class FakeGit:
        def ls_remote(self, *_args, **_kwargs):
            return raw

    monkeypatch.setattr("git.Git", lambda: FakeGit())

    results = list_platform_versions()
    versions = [r["version"] for r in results]
    assert "0.9.0" in versions
    assert "0.10.0-rc1" in versions
    assert all("not-a-version" not in v for v in versions)
    assert all(r["sdk"] == "platform" for r in results)
    assert all(r["source"] == "platform-git-tag" for r in results)


def test_list_java_github_releases_403_rate_limit(monkeypatch: pytest.MonkeyPatch, capsys):
    """403 from GitHub API surfaces a rate-limit warning before re-raising."""
    err = urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=403,
        msg="rate limited",
        hdrs={"X-RateLimit-Reset": "1700000000"},  # type: ignore[arg-type]
        fp=None,
    )

    def boom(_url: str):
        raise err

    monkeypatch.setattr(
        registry.urllib.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(err)
    )

    with pytest.raises(urllib.error.HTTPError):
        registry.fetch_json("https://api.github.com/repos/test/releases")
    captured = capsys.readouterr()
    assert "rate limit" in captured.err.lower()
