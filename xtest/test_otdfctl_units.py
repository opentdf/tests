"""Offline checks for selecting the configured otdfctl CLI wrapper."""

from pathlib import Path

import pytest

import conftest

pytestmark = pytest.mark.no_audit_logs


def test_release_only_selection_uses_installed_wrapper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wrapper = tmp_path / "sdk/go/dist/v0.41.0/otdfctl.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OTDFCTL_HEADS", "[]")
    monkeypatch.setenv("OTDFCTL_TAG", "v0.41.0")

    assert conftest.load_otdfctl().otdfctl == ["sdk/go/dist/v0.41.0/otdfctl.sh"]


def test_selected_wrapper_missing_fails_instead_of_using_latest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fallback = tmp_path / "sdk/go/otdfctl.sh"
    fallback.parent.mkdir(parents=True)
    fallback.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OTDFCTL_HEADS", "[]")
    monkeypatch.setenv("OTDFCTL_TAG", "v0.41.0")

    with pytest.raises(FileNotFoundError, match="dist/v0.41.0/otdfctl.sh"):
        conftest.load_otdfctl()
