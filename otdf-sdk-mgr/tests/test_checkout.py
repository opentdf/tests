"""Bare-repo checkouts against real git, with a local origin and no network."""

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from otdf_sdk_mgr import checkout, config, platform_installer
from otdf_sdk_mgr.checkout import CheckoutError
from otdf_sdk_mgr.cli_install import install_app
from otdf_sdk_mgr.platform_installer import PlatformInstallError
from otdf_sdk_mgr.refs import expand_pr_shorthand

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _head(repo: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=repo)


def _advance(origin: Path, path: str = "next") -> str:
    """Commit a change to `path` onto origin's `main`, as if a PR had landed
    upstream; return the new tip."""
    with (origin / path).open("a") as f:
        f.write("next\n")
    _git("add", ".", cwd=origin)
    _git("commit", "-q", "-m", "next", cwd=origin)
    return _head(origin)


def _assert_untouched(worktree: Path, head: str) -> None:
    """HEAD hasn't moved, and the index and files still match it."""
    assert _head(worktree) == head
    assert _git("status", "--porcelain", cwd=worktree) == ""


@pytest.fixture
def origin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_git: None) -> Path:
    """A one-commit repo standing in for the js and platform remotes (go
    builds come from platform)."""
    repo = tmp_path / "origin"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    # checkout_go_from_platform requires the monorepo's otdfctl/ subtree, and
    # install_helper_scripts its scripts/.
    for path in ("otdfctl/go.mod", "scripts/a.sh"):
        (repo / path).parent.mkdir()
        (repo / path).write_text("first\n")
    _git("add", ".", cwd=repo)
    _git("commit", "-q", "-m", "first", cwd=repo)
    _git("branch", "other", cwd=repo)

    for name in ("js", "platform"):
        monkeypatch.setitem(config.SDK_GIT_URLS, name, str(repo))
    monkeypatch.setattr(
        checkout, "get_sdk_dirs", lambda: {"js": tmp_path / "js", "go": tmp_path / "go"}
    )
    monkeypatch.setenv("OTDF_PLATFORM_DIR", str(tmp_path / "platform"))
    return repo


ENTRY_POINTS = ["sdk", "go", "platform"]


def _check_out(entry: str, origin: Path, ref: str) -> Path:
    """Check out `ref` through one of the bare-repo entry points; return the worktree."""
    if entry == "sdk":
        return origin.parent / "js" / "src" / checkout.checkout_sdk_branch("js", ref)
    if entry == "go":
        return checkout.checkout_go_from_platform(ref)
    # install_platform_source expands `pr:N` before it gets here.
    return platform_installer._ensure_worktree(expand_pr_shorthand(ref))


@pytest.mark.parametrize("entry", ENTRY_POINTS)
class TestEveryEntryPoint:
    def test_new_worktree_gets_the_branch_as_it_is_now(self, entry: str, origin: Path):
        """Not as it was when some earlier checkout cloned the bare repo."""
        _check_out(entry, origin, "other")
        tip = _advance(origin)

        assert _head(_check_out(entry, origin, "main")) == tip

    def test_existing_worktree_follows_its_branch(self, entry: str, origin: Path):
        _check_out(entry, origin, "main")
        tip = _advance(origin)

        assert _head(_check_out(entry, origin, "main")) == tip

    def test_head_follows_origins_default_branch(self, entry: str, origin: Path):
        """`reset --hard HEAD` inside the worktree would reset it to itself."""
        _check_out(entry, origin, "HEAD")
        tip = _advance(origin)

        assert _head(_check_out(entry, origin, "HEAD")) == tip

    def test_head_beside_a_tag_named_like_the_default_branch(self, entry: str, origin: Path):
        """`symbolic-ref --short` answers `heads/main` here, which names the
        clone-time branch."""
        _git("tag", "main", cwd=origin)
        _check_out(entry, origin, "other")
        tip = _advance(origin)

        assert _head(_check_out(entry, origin, "HEAD")) == tip

    def test_branch_gone_from_origin_is_refused(self, entry: str, origin: Path):
        """The bare repo still has the clone's copy of `other`; don't build it."""
        _check_out(entry, origin, "main")
        _git("branch", "-D", "other", cwd=origin)

        error = PlatformInstallError if entry == "platform" else CheckoutError
        with pytest.raises(error, match="'other' is not on origin"):
            _check_out(entry, origin, "other")

    @pytest.mark.parametrize("kind", ["tag", "sha"])
    def test_immutable_ref_is_checked_out_then_reused(self, entry: str, kind: str, origin: Path):
        _check_out(entry, origin, "main")
        pinned = _advance(origin)
        ref = pinned
        if kind == "tag":
            ref = "v1.2.3"
            _git("tag", ref, cwd=origin)

        worktree = _check_out(entry, origin, ref)
        assert _head(worktree) == pinned

        _advance(origin)
        _check_out(entry, origin, ref)

        _assert_untouched(worktree, pinned)

    def test_pr_ref_follows_a_force_push(self, entry: str, origin: Path):
        """BARE_REFRESH skips `refs/pull/*`, so each checkout fetches the PR
        head itself, and has to overwrite the old one."""
        _git("update-ref", "refs/pull/1/head", _advance(origin), cwd=origin)
        worktree = _check_out(entry, origin, "pr:1")
        _git("reset", "-q", "--hard", "HEAD~1", cwd=origin)
        rewritten = _advance(origin, "rewritten")
        _git("update-ref", "refs/pull/1/head", rewritten, cwd=origin)

        _check_out(entry, origin, "pr:1")

        assert _head(worktree) == rewritten


class TestSdkCheckout:
    def test_refresh_leaves_other_worktrees_alone(self, origin: Path):
        """Refreshing for one worktree must not move another's HEAD past its
        index and files."""
        worktree = _check_out("sdk", origin, "main")
        before = _head(worktree)
        _advance(origin)

        _check_out("sdk", origin, "other")

        _assert_untouched(worktree, before)

    def test_existing_worktree_follows_a_force_push(self, origin: Path):
        worktree = _check_out("sdk", origin, "main")
        _git("commit", "-q", "--amend", "-m", "rewritten", cwd=origin)

        _check_out("sdk", origin, "main")

        assert _head(worktree) == _head(origin)

    def test_branch_renamed_to_a_subpath(self, origin: Path):
        """`other` and `other/thing` can't coexist as refs; the refresh has to
        prune the stale one before it can fetch the new one."""
        _check_out("sdk", origin, "main")
        _git("branch", "-m", "other", "other/thing", cwd=origin)

        worktree = _check_out("sdk", origin, "other/thing")

        assert _head(worktree) == _head(origin)


class TestGoCheckout:
    def test_src_link_follows_the_refreshed_checkout(self, origin: Path):
        checkout.checkout_go_from_platform("main")
        tip = _advance(origin)

        checkout.checkout_go_from_platform("main")

        assert _head(origin.parent / "go" / "src" / "main") == tip


class TestPlatformWorktree:
    def test_helper_scripts_follow_their_branch(self, origin: Path):
        scripts = platform_installer.install_helper_scripts()
        _advance(origin, "scripts/a.sh")

        platform_installer.install_helper_scripts()

        assert (scripts / "a.sh").read_text() == (origin / "scripts" / "a.sh").read_text()

    def test_build_leaves_the_scripts_worktree_alone(self, origin: Path):
        platform_installer.install_helper_scripts()
        worktree = platform_installer._worktree_path_for("scripts--main")
        before = _head(worktree)
        _advance(origin, "scripts/a.sh")

        platform_installer._ensure_worktree("main")

        _assert_untouched(worktree, before)


class TestInstallTip:
    def test_branch_gone_from_origin_is_an_error_not_a_traceback(self, origin: Path):
        _check_out("sdk", origin, "main")
        _git("branch", "-D", "other", cwd=origin)

        result = CliRunner().invoke(install_app, ["tip", "--ref", "other", "js"])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert "Error: branch 'other' is not on origin" in result.output
