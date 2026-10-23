"""Tests for platform_installer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from otdf_sdk_mgr import platform_installer
from otdf_sdk_mgr.platform_installer import (
    PlatformInstallError,
    _resolve_platform_ref,
    install_platform_source,
)
from otdf_sdk_mgr.refs import ref_slug


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("v0.9.0", "service/v0.9.0"),
        ("0.9.0", "service/v0.9.0"),
        ("v0.9.0-rc.1", "service/v0.9.0-rc.1"),
        # Anything else that isn't a version is a ref for git to resolve.
        ("main", "main"),
        ("HEAD", "HEAD"),
        ("my-branch", "my-branch"),
        ("release/v1.2.3", "release/v1.2.3"),
        ("service/v0.9.0", "service/v0.9.0"),
        ("a" * 40, "a" * 40),
        ("b" * 64, "b" * 64),
        # 7-39 char hex passes through unchanged; install_platform_source
        # expands via `git rev-parse` once the bare repo is available.
        ("abc1234", "abc1234"),
        ("deadbeef", "deadbeef"),
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
    "inp",
    [
        "ghcr.io/opentdf/platform:v0.9.0",
        "registry.example.com/opentdf/platform@sha256:" + "a" * 64,
        "docker.io/library/foo:latest",
    ],
)
def test_resolve_platform_ref_rejects_container_image_refs(inp):
    with pytest.raises(PlatformInstallError, match="container-image"):
        _resolve_platform_ref(inp)


def _stub_installer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """Replace every subprocess-touching helper with in-memory recorders.

    Returns a `calls` dict that test cases inspect.
    """
    calls: dict[str, Any] = {
        "run": [],
        "ensure_worktree": [],
        "build_service": [],
        "record_version": 0,
        "expand_short_sha": [],
    }
    dist_root = tmp_path / "dist"

    def _record(name: str):
        def fn(*args, **kwargs):
            calls[name].append((args, kwargs))

        return fn

    monkeypatch.setattr(platform_installer, "_platform_dist_root", lambda: dist_root)
    monkeypatch.setattr(platform_installer, "_run", _record("run"))

    def fake_ensure_worktree(ref: str) -> Path:
        calls["ensure_worktree"].append(ref)
        p = tmp_path / "src" / ref.replace("/", "--")
        p.mkdir(parents=True, exist_ok=True)
        return p

    def fake_build_service(worktree: Path, dist_dir: Path) -> Path:
        calls["build_service"].append((str(worktree), str(dist_dir)))
        dist_dir.mkdir(parents=True, exist_ok=True)
        binary = dist_dir / "service"
        binary.write_text("fake binary")
        (dist_dir / ".complete").write_text("")
        return binary

    def fake_record_version(dist_dir: Path, ref: str, worktree: Path) -> None:
        calls["record_version"] += 1

    def fake_expand_short_sha(short: str) -> str:
        calls["expand_short_sha"].append(short)
        return "a" * 40

    monkeypatch.setattr(platform_installer, "_ensure_worktree", fake_ensure_worktree)
    monkeypatch.setattr(platform_installer, "_build_service", fake_build_service)
    monkeypatch.setattr(platform_installer, "_record_version", fake_record_version)
    monkeypatch.setattr(platform_installer, "_expand_short_sha", fake_expand_short_sha)
    return calls


@pytest.mark.parametrize(
    "ref,expected_dist_name",
    [
        # Immutable refs: namespaced tags and plain tags share a dist_name.
        ("service/v0.9.0", "v0.9.0"),
        ("v0.9.0", "v0.9.0"),
        ("0.9.0", "v0.9.0"),
        # Mutable refs: use ref_slug
        ("main", "main"),
        ("refs/pull/42/head", "refs--pull--42--head"),
        ("my-branch", "my-branch"),
        # A branch named like a version, not release v1.2.3's dist.
        ("release/v1.2.3", "release--v1.2.3"),
    ],
)
def test_dist_name_derivation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ref: str, expected_dist_name: str
):
    """install_platform_source picks dist_name consistently for each ref form."""
    _stub_installer(monkeypatch, tmp_path)
    dist_dir = install_platform_source(ref)
    assert dist_dir.name == expected_dist_name


@pytest.mark.parametrize(
    "ref,dist_name",
    [
        ("v0.9.0", "v0.9.0"),
        ("service/v0.9.0", "v0.9.0"),
        ("a" * 40, "v" + "a" * 40),
    ],
)
def test_immutable_ref_with_complete_marker_skips_rebuild(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ref: str, dist_name: str
):
    """An existing release or SHA build (binary + .complete) is reused, not
    rebuilt, without touching the bare repo."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = tmp_path / "dist" / dist_name
    dist_dir.mkdir(parents=True)
    (dist_dir / "service").write_text("prebuilt")
    (dist_dir / ".complete").write_text("")

    install_platform_source(ref)

    assert calls["build_service"] == []
    assert calls["ensure_worktree"] == []


def test_immutable_ref_without_complete_marker_rebuilds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A partial dist (binary without .complete) is treated as corrupt and rebuilt."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = tmp_path / "dist" / "v0.9.0"
    dist_dir.mkdir(parents=True)
    (dist_dir / "service").write_text("half-built")

    install_platform_source("v0.9.0")

    assert len(calls["build_service"]) == 1


@pytest.mark.parametrize("ref", ["main", "my-branch", "release/v1.2.3", "sdk/v0.4.0"])
def test_mutable_ref_drops_existing_binary_and_rebuilds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ref: str
):
    """A branch re-fetches and rebuilds even if a binary exists, whatever its
    name looks like. So does any ref that isn't provably a release or a SHA
    before the bare repo is refreshed: `sdk/v0.4.0` is a tag in the
    monorepo, but `release/v1.2.3` is shaped the same."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = tmp_path / "dist" / ref_slug(ref)
    dist_dir.mkdir(parents=True)
    stale_binary = dist_dir / "service"
    stale_binary.write_text("stale")
    (dist_dir / ".complete").write_text("")

    assert install_platform_source(ref) == dist_dir
    assert calls["ensure_worktree"] == [ref]
    assert len(calls["build_service"]) == 1


def test_pr_ref_expands_and_fetches_refspec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """install_platform_source("pr:123") delegates to _ensure_worktree with the
    expanded ref. test_checkout.py runs the real `_ensure_worktree` on a PR ref
    against a local origin."""
    calls = _stub_installer(monkeypatch, tmp_path)
    install_platform_source("pr:123")
    assert calls["ensure_worktree"] == ["refs/pull/123/head"]


def test_short_sha_expansion_at_install_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Abbreviated hex refs are expanded via `_expand_short_sha` before caching."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = install_platform_source("abc1234")
    assert calls["expand_short_sha"] == ["abc1234"]
    assert dist_dir.name == "v" + "a" * 40
