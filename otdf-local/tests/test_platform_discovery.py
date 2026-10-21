"""Tests for locating a startable platform source tree.

Layouts: a `platform/` checkout beside `xtest/`, the `xtest/platform/src/<ref>/`
worktrees that `otdf-sdk-mgr` creates, and a `platform/` beside a further
ancestor.
"""

from pathlib import Path

import pytest
from otdf_local.config.settings import Settings, _find_platform_dir


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
    _make_platform(xtest_root / "platform" / "src" / "main")
    _make_platform(xtest_root / "platform" / "src" / "v0.9.0")

    with pytest.raises(FileNotFoundError) as excinfo:
        _find_platform_dir(xtest_root)

    message = str(excinfo.value)
    assert "main" in message and "v0.9.0" in message
    assert "OTDF_LOCAL_PLATFORM_DIR" in message


def test_an_incomplete_checkout_is_not_startable(xtest_root: Path):
    # Missing opentdf-dev.yaml, the committed config the template is seeded from.
    partial = xtest_root / "platform" / "src" / "main"
    partial.mkdir(parents=True)
    (partial / "docker-compose.yaml").write_text("services: {}\n")

    with pytest.raises(FileNotFoundError, match="opentdf-dev.yaml"):
        _find_platform_dir(xtest_root)


def test_nothing_installed_says_how_to_install(xtest_root: Path):
    with pytest.raises(FileNotFoundError, match="otdf-sdk-mgr install tip platform"):
        _find_platform_dir(xtest_root)


def test_the_helper_scripts_checkout_is_not_an_installed_ref(xtest_root: Path):
    # `otdf-sdk-mgr install scripts` checks out platform main as
    # `scripts--main`; counting it would make every scenario install ambiguous.
    _make_platform(xtest_root / "platform" / "src" / "scripts--main")
    expected = _make_platform(xtest_root / "platform" / "src" / "main")
    assert _find_platform_dir(xtest_root) == expected


def test_an_incomplete_sibling_falls_through_to_an_installed_worktree(
    xtest_root: Path,
):
    (xtest_root.parent / "platform").mkdir()
    (xtest_root.parent / "platform" / "docker-compose.yaml").write_text("")
    expected = _make_platform(xtest_root / "platform" / "src" / "main")
    assert _find_platform_dir(xtest_root) == expected


def test_a_sibling_checkout_settles_several_installed_refs(xtest_root: Path):
    sibling = _make_platform(xtest_root.parent / "platform")
    _make_platform(xtest_root / "platform" / "src" / "main")
    _make_platform(xtest_root / "platform" / "src" / "service--v0.9.0")
    assert _find_platform_dir(xtest_root) == sibling


def test_an_installed_worktree_beats_a_distant_ancestor_checkout(xtest_root: Path):
    # e.g. a multi-repo workspace with its own platform/ above tests/.
    _make_platform(xtest_root.parent.parent / "platform")
    expected = _make_platform(xtest_root / "platform" / "src" / "main")
    assert _find_platform_dir(xtest_root) == expected


def test_a_distant_ancestor_checkout_is_the_last_resort(xtest_root: Path):
    expected = _make_platform(xtest_root.parent.parent / "platform")
    assert _find_platform_dir(xtest_root) == expected


def test_the_env_var_settles_several_installed_refs(
    xtest_root: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_platform(xtest_root / "platform" / "src" / "main")
    chosen = _make_platform(xtest_root / "platform" / "src" / "service--v0.9.0")
    monkeypatch.setenv("OTDF_LOCAL_XTEST_ROOT", str(xtest_root))
    monkeypatch.setenv("OTDF_LOCAL_PLATFORM_DIR", str(chosen))
    assert Settings().platform_dir == chosen


def test_discovery_searches_from_the_configured_xtest_root(
    xtest_root: Path, monkeypatch: pytest.MonkeyPatch
):
    expected = _make_platform(xtest_root / "platform" / "src" / "main")
    monkeypatch.setenv("OTDF_LOCAL_XTEST_ROOT", str(xtest_root))
    monkeypatch.delenv("OTDF_LOCAL_PLATFORM_DIR", raising=False)
    assert Settings().platform_dir == expected
