"""Shared fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Let tests commit with real git, free of the developer's config and off the network.

    A global `commit.gpgsign` or hook would otherwise fail or prompt, and a
    `GIT_DIR` inherited from a git hook would point every command at the
    caller's repo.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
    ):
        monkeypatch.delenv(var, raising=False)
    # A test that misses its local origin fails instead of reaching GitHub.
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    for var in ("GIT_AUTHOR", "GIT_COMMITTER"):
        monkeypatch.setenv(f"{var}_NAME", "test")
        monkeypatch.setenv(f"{var}_EMAIL", "test@example.com")
