"""Tests for platform_installer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from otdf_sdk_mgr import platform_installer
from otdf_sdk_mgr.platform_installer import _resolve_platform_ref, install_platform_source


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
    ],
)
def test_dist_name_derivation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ref: str, expected_dist_name: str
):
    """install_platform_source picks dist_name consistently for each ref form."""
    _stub_installer(monkeypatch, tmp_path)
    dist_dir = install_platform_source(ref)
    assert dist_dir.name == expected_dist_name


def test_immutable_ref_with_complete_marker_skips_rebuild(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """An existing immutable build (binary + .complete) is reused, not rebuilt."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = tmp_path / "dist" / "v0.9.0"
    dist_dir.mkdir(parents=True)
    (dist_dir / "service").write_text("prebuilt")
    (dist_dir / ".complete").write_text("")

    install_platform_source("v0.9.0")

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


def test_mutable_ref_drops_existing_binary_and_rebuilds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A mutable ref (branch) re-fetches and rebuilds even if a binary exists."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = tmp_path / "dist" / "main"
    dist_dir.mkdir(parents=True)
    stale_binary = dist_dir / "service"
    stale_binary.write_text("stale")
    (dist_dir / ".complete").write_text("")

    install_platform_source("main")

    assert calls["ensure_worktree"] == ["main"]
    assert len(calls["build_service"]) == 1


def test_pr_ref_expands_and_fetches_refspec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """install_platform_source("pr:123") delegates to _ensure_worktree with the
    expanded ref. The real `_ensure_worktree` would then run `git fetch origin
    +refs/pull/123/head:refs/pull/123/head` — exercised by the explicit test
    below that doesn't stub `_ensure_worktree`."""
    calls = _stub_installer(monkeypatch, tmp_path)
    install_platform_source("pr:123")
    assert calls["ensure_worktree"] == ["refs/pull/123/head"]


def test_ensure_worktree_fetches_pr_refspec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """_ensure_worktree explicitly fetches `refs/...` refs before `worktree add`.

    The bare clone's default refspec is `+refs/heads/*:refs/heads/*` plus
    `--tags`, so PR refs are never pulled and `git worktree add
    refs/pull/N/head` fails without the explicit fetch.
    """
    run_calls: list[list[str]] = []

    def fake_run(cmd, cwd=None):
        run_calls.append(list(cmd))

    bare = tmp_path / "platform.git"
    bare.mkdir()
    monkeypatch.setattr(platform_installer, "_run", fake_run)
    monkeypatch.setattr(platform_installer, "_ensure_bare_repo", lambda: bare)
    monkeypatch.setattr(platform_installer, "_platform_src_root", lambda: tmp_path / "src")

    platform_installer._ensure_worktree("refs/pull/123/head")

    fetches = [c for c in run_calls if len(c) >= 4 and c[2] == "fetch"]
    assert any("+refs/pull/123/head:refs/pull/123/head" in c for c in fetches), run_calls


def test_short_sha_expansion_at_install_time(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Abbreviated hex refs are expanded via `_expand_short_sha` before caching."""
    calls = _stub_installer(monkeypatch, tmp_path)
    dist_dir = install_platform_source("abc1234")
    assert calls["expand_short_sha"] == ["abc1234"]
    assert dist_dir.name == "v" + "a" * 40
