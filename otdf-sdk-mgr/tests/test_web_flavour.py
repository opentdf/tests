"""Tests for how otdf-sdk-mgr wires up the headless-browser `web` flavour."""

from __future__ import annotations

from pathlib import Path

import pytest

from otdf_sdk_mgr import checkout, installers
from otdf_sdk_mgr.config import ALL_SDKS, DEFAULT_SDKS, get_sdk_dirs


def test_web_is_known_but_not_installed_by_default():
    # Staging `web` downloads a Playwright browser, so a bare `install stable`
    # must not pull it in; naming it explicitly must work.
    assert "web" in ALL_SDKS
    assert "web" not in DEFAULT_SDKS
    assert "web" in installers.INSTALLERS


def test_web_checkout_reuses_the_js_worktree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """`web` and `js` are one repository; checking out `web` must not clone it twice."""
    monkeypatch.setenv("OTDF_SDK_DIR", str(tmp_path))
    calls: list[list[str]] = []
    monkeypatch.setattr(checkout, "_run", lambda cmd, **_kw: calls.append(cmd))

    slug = checkout.checkout_sdk_branch("web", "main")

    assert slug == "main"
    js_src = tmp_path / "js" / "src"
    assert calls[0][:3] == ["git", "clone", "--bare"]
    assert calls[0][-1] == str(js_src / "web-sdk.git")
    assert calls[-1][-2:] == [str(js_src / "main"), "main"]
    assert not (tmp_path / "web" / "src").exists()


def test_install_web_release_delegates_to_stage_sh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OTDF_SDK_DIR", str(tmp_path))
    calls: list[list[str]] = []
    monkeypatch.setattr(installers.subprocess, "check_call", lambda cmd, **_kw: calls.append(cmd))

    dist = get_sdk_dirs()["web"] / "dist" / "v0.22.0"
    installers.install_web_release("sdk/v0.22.0", dist)

    assert calls == [[str(tmp_path / "web" / "stage.sh"), str(dist), "@opentdf/sdk@0.22.0"]]


def test_install_web_release_wraps_stage_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("OTDF_SDK_DIR", str(tmp_path))

    def boom(cmd: list[str], **_kw: object) -> None:
        raise installers.subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(installers.subprocess, "check_call", boom)
    with pytest.raises(installers.InstallError, match="@opentdf/sdk@0.22.0"):
        installers.install_web_release("0.22.0", tmp_path / "web" / "dist" / "v0.22.0")
