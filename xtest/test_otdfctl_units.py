"""Offline checks for the otdfctl CLI wrapper."""

import json
import subprocess
from pathlib import Path

import pytest

import conftest
from otdfctl import OpentdfCommandLineTool

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


def _ns(i: int) -> dict[str, str]:
    return {"id": f"id-{i}", "name": f"n{i}.example", "fqn": f"https://n{i}.example"}


def _fake_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pages: dict[int, object]
) -> tuple[OpentdfCommandLineTool, list[list[str]]]:
    """An otdfctl whose list output, keyed by --offset, comes from ``pages``."""
    calls: list[list[str]] = []

    class FakePopen:
        returncode = 0

        def __init__(self, cmd: list[str], **_: object) -> None:
            calls.append(cmd)
            offset = next(
                (
                    int(a.removeprefix("--offset="))
                    for a in cmd
                    if a.startswith("--offset=")
                ),
                0,
            )
            self.out = json.dumps(pages[offset]).encode()

        def communicate(self) -> tuple[bytes, bytes]:
            return self.out, b""

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    wrapper = tmp_path / "otdfctl.sh"
    wrapper.touch()
    return OpentdfCommandLineTool(str(wrapper)), calls


def test_list_follows_next_offset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli, calls = _fake_cli(
        monkeypatch,
        tmp_path,
        {
            0: {"namespaces": [_ns(0), _ns(1)], "pagination": {"next_offset": 2}},
            2: {"namespaces": [_ns(2)], "pagination": {"current_offset": 2}},
        },
    )
    assert [n.id for n in cli.namespace_list()] == ["id-0", "id-1", "id-2"]
    assert [c[-1] for c in calls] == ["list", "--offset=2"]


def test_list_accepts_unpaginated_bare_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli, calls = _fake_cli(monkeypatch, tmp_path, {0: [_ns(0)]})
    assert [n.id for n in cli.namespace_list()] == ["id-0"]
    assert len(calls) == 1


def test_list_rejects_pagination_that_does_not_advance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cli, _ = _fake_cli(
        monkeypatch,
        tmp_path,
        {
            0: {"namespaces": [_ns(0)], "pagination": {"next_offset": 1}},
            1: {"namespaces": [_ns(1)], "pagination": {"next_offset": 1}},
        },
    )
    with pytest.raises(AssertionError, match="next_offset 1 <= 1"):
        cli.namespace_list()
