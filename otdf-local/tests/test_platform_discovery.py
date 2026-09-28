"""Tests for locating a startable platform source tree.

Two layouts coexist: a `platform/` checkout beside `xtest/`, and the
`xtest/platform/src/<ref>/` worktrees that `otdf-sdk-mgr` creates. Discovery
only knew about the first, so `install benchmark --platform main` put a
platform somewhere `otdf-local up` could not see, and the local benchmark
sequence worked only with `OTDF_LOCAL_PLATFORM_DIR` set by hand.
"""

from pathlib import Path

import pytest
from otdf_local.config.settings import _find_platform_dir


def _make_platform(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "docker-compose.yaml").write_text("services: {}\n")
    (path / "opentdf-dev.yaml").write_text("services: {}\n")
    return path


@pytest.fixture
def xtest_root(tmp_path: Path) -> Path:
    root = tmp_path / "tests" / "xtest"
    root.mkdir(parents=True)
    return root


def test_finds_a_sibling_checkout(xtest_root: Path):
    expected = _make_platform(xtest_root.parent / "platform")
    assert _find_platform_dir(xtest_root) == expected


def test_finds_an_installed_worktree(xtest_root: Path):
    expected = _make_platform(xtest_root / "platform" / "src" / "main")
    assert _find_platform_dir(xtest_root) == expected


def test_a_sibling_checkout_is_not_shadowed_by_an_installed_one(xtest_root: Path):
    # An explicit checkout is a deliberate act; an installed ref is a side
    # effect of running the installer. The deliberate one wins.
    sibling = _make_platform(xtest_root.parent / "platform")
    _make_platform(xtest_root / "platform" / "src" / "main")
    assert _find_platform_dir(xtest_root) == sibling


def test_the_bare_repo_is_not_mistaken_for_a_worktree(xtest_root: Path):
    # `platform.git` sits in src/ beside the worktrees and has neither file,
    # so it is skipped by shape rather than by name.
    (xtest_root / "platform" / "src" / "platform.git").mkdir(parents=True)
    expected = _make_platform(xtest_root / "platform" / "src" / "main")
    assert _find_platform_dir(xtest_root) == expected


def test_several_installed_refs_are_ambiguous_rather_than_arbitrary(xtest_root: Path):
    # Picking one would silently decide which platform version everything is
    # measured against -- the one question a benchmark must not guess at.
    _make_platform(xtest_root / "platform" / "src" / "main")
    _make_platform(xtest_root / "platform" / "src" / "v0.9.0")

    with pytest.raises(FileNotFoundError) as excinfo:
        _find_platform_dir(xtest_root)

    message = str(excinfo.value)
    assert "main" in message and "v0.9.0" in message
    assert "OTDF_LOCAL_PLATFORM_DIR" in message


def test_an_incomplete_checkout_is_not_startable(xtest_root: Path):
    # `go run ./service` needs the tree and the config template both.
    partial = xtest_root / "platform" / "src" / "main"
    partial.mkdir(parents=True)
    (partial / "docker-compose.yaml").write_text("services: {}\n")

    with pytest.raises(FileNotFoundError, match="opentdf-dev.yaml"):
        _find_platform_dir(xtest_root)


def test_nothing_installed_says_how_to_install(xtest_root: Path):
    with pytest.raises(FileNotFoundError, match="otdf-sdk-mgr install tip platform"):
        _find_platform_dir(xtest_root)
