"""Bare-repo checkouts against real git, with a local origin and no network."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from otdf_sdk_mgr import checkout, config, platform_installer
from otdf_sdk_mgr.checkout import CheckoutError
from otdf_sdk_mgr.cli import app
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
    """A one-commit repo standing in for the js, java and platform remotes
    (go builds come from platform)."""
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

    for name in ("js", "java", "platform"):
        monkeypatch.setitem(config.SDK_GIT_URLS, name, str(repo))
    monkeypatch.setattr(
        checkout, "get_sdk_dirs", lambda: {s: tmp_path / s for s in ("go", "js", "java")}
    )
    monkeypatch.setenv("OTDF_PLATFORM_DIR", str(tmp_path / "platform"))
    return repo


@pytest.fixture
def enclosing(tmp_path: Path, origin: Path) -> Path:
    """Make the directory holding the bare repos and worktrees a repo too, as
    the opentdf/tests checkout is, with uncommitted work. Like any clone it has
    `refs/remotes/origin/main`, so a reset meant for a worktree would succeed
    here."""
    _git("init", "-q", "-b", "main", cwd=tmp_path)
    (tmp_path / "work").write_text("committed\n")
    _git("add", "work", cwd=tmp_path)
    _git("commit", "-q", "-m", "first", cwd=tmp_path)
    _git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "local", cwd=tmp_path)
    (tmp_path / "work").write_text("uncommitted\n")
    return tmp_path


def _assert_enclosing_untouched(enclosing: Path) -> None:
    assert _git("log", "-1", "--format=%s", cwd=enclosing) == "local"
    assert (enclosing / "work").read_text() == "uncommitted\n"


def _not_a_worktree(path: Path) -> str:
    return f"{re.escape(str(path))} is not a git worktree"


ENTRY_POINTS = ["sdk", "go", "platform"]


def _check_out(entry: str, origin: Path, ref: str) -> Path:
    """Check out `ref` through one of the bare-repo entry points; return the worktree."""
    if entry == "sdk":
        return origin.parent / "js" / "src" / checkout.checkout_sdk_branch("js", ref)
    if entry == "go":
        return checkout.checkout_go_from_platform(ref)
    # install_platform_source expands `pr:N` before it gets here.
    return platform_installer._ensure_worktree(expand_pr_shorthand(ref))


def _bare_repo(entry: str, origin: Path) -> Path:
    if entry == "sdk":
        return origin.parent / "js" / "src" / config.SDK_BARE_REPOS["js"]
    if entry == "go":
        return origin.parent / "go" / "platform-src" / "platform.git"
    return platform_installer._platform_bare_repo()


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

    @pytest.mark.parametrize("ref", ["main", "v1.2.3"])
    def test_directory_that_lost_its_git_file_is_refused(
        self, entry: str, ref: str, origin: Path, enclosing: Path
    ):
        """As an interrupted `clean` or `git worktree add` can leave it. git
        would climb past it to the enclosing repo and reset that instead. A
        tag's worktree is checked too, since it is reset if the tag moved."""
        _git("tag", "v1.2.3", cwd=origin)
        worktree = _check_out(entry, origin, ref)
        (worktree / ".git").unlink()

        error = PlatformInstallError if entry == "platform" else CheckoutError
        with pytest.raises(error, match=_not_a_worktree(worktree)):
            _check_out(entry, origin, ref)

        _assert_enclosing_untouched(enclosing)

    def test_removed_worktree_is_added_again(self, entry: str, origin: Path):
        """The way out of the refusal above, and how `clean` leaves SDK
        worktrees: the bare repo still lists the directory, and `worktree add`
        refuses a listed path."""
        worktree = _check_out(entry, origin, "main")
        shutil.rmtree(worktree)

        assert _head(_check_out(entry, origin, "main")) == _head(origin)

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

    @pytest.mark.parametrize("annotated", [False, True], ids=["lightweight", "annotated"])
    def test_existing_worktree_follows_a_moved_tag(self, entry: str, annotated: bool, origin: Path):
        """As upstream does after a botched release. git won't clobber a tag on
        fetch without force, and a tag's worktree is otherwise reused, so it
        would build the old commit under the tag's name."""
        tag = ["tag", "-a", "-m", "release"] if annotated else ["tag"]
        _git(*tag, "v1.2.2", cwd=origin)
        _git(*tag, "v1.2.3", cwd=origin)
        released = _head(origin)
        unmoved = _check_out(entry, origin, "v1.2.2")
        worktree = _check_out(entry, origin, "v1.2.3")
        moved = _advance(origin)
        _git(*tag, "-f", "v1.2.3", moved, cwd=origin)

        _check_out(entry, origin, "v1.2.3")
        _check_out(entry, origin, "v1.2.2")

        bare = _bare_repo(entry, origin)
        assert _git(f"--git-dir={bare}", "rev-parse", "v1.2.3^{commit}", cwd=origin) == moved
        assert _head(worktree) == moved
        _assert_untouched(unmoved, released)

    def test_unmoved_tag_keeps_local_edits(self, entry: str, origin: Path):
        """Only a moved tag is reset. An annotated tag names a tag object, not
        the commit the worktree has checked out."""
        _git("tag", "-a", "-m", "release", "v1.2.3", cwd=origin)
        worktree = _check_out(entry, origin, "v1.2.3")
        (worktree / "scripts" / "a.sh").write_text("debugging\n")
        _advance(origin)

        _check_out(entry, origin, "v1.2.3")

        assert (worktree / "scripts" / "a.sh").read_text() == "debugging\n"

    def test_version_named_branch_gone_from_origin_fails(self, entry: str, origin: Path):
        """Made after the clone, so there's no local copy for upstream_ref to
        refuse, and the name passes through looking like a tag. It names no
        commit now, so it can't match the worktree; reuse would build a branch
        origin deleted."""
        _check_out(entry, origin, "main")
        _git("branch", "release/v1.2.3", cwd=origin)
        _check_out(entry, origin, "release/v1.2.3")
        _git("branch", "-D", "release/v1.2.3", cwd=origin)

        error = PlatformInstallError if entry == "platform" else subprocess.CalledProcessError
        with pytest.raises(error, match="reset"):
            _check_out(entry, origin, "release/v1.2.3")

    @pytest.mark.parametrize("branch", ["release/v1.2.3", "release/1.3.1"])
    def test_version_named_branch_follows_origin(self, entry: str, branch: str, origin: Path):
        """A branch whatever its name looks like; web-sdk cuts `release/1.3.1`.
        Reused like a tag's, its worktree would keep the first commit."""
        _git("branch", branch, cwd=origin)
        worktree = _check_out(entry, origin, branch)
        _git("update-ref", f"refs/heads/{branch}", _advance(origin), cwd=origin)

        _check_out(entry, origin, branch)

        assert _head(worktree) == _head(origin)

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

    def test_clone_in_place_of_the_worktree_is_refused(self, origin: Path):
        """Say one made by hand to work on the SDK; a reset would discard the
        work."""
        worktree = _check_out("sdk", origin, "main")
        shutil.rmtree(worktree)
        _git("clone", "-q", str(origin), str(worktree), cwd=origin)
        (worktree / "scripts" / "a.sh").write_text("work in progress\n")

        with pytest.raises(CheckoutError, match=_not_a_worktree(worktree)):
            _check_out("sdk", origin, "main")

        assert (worktree / "scripts" / "a.sh").read_text() == "work in progress\n"

    def test_worktree_of_a_recloned_bare_repo_is_refused(self, origin: Path):
        """Its `.git` names an entry the new clone doesn't have."""
        worktree = _check_out("sdk", origin, "main")
        shutil.rmtree(origin.parent / "js" / "src" / config.SDK_BARE_REPOS["js"])

        with pytest.raises(CheckoutError, match=_not_a_worktree(worktree)):
            _check_out("sdk", origin, "main")


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

    def test_scripts_directory_that_lost_its_git_file_is_refused(
        self, origin: Path, enclosing: Path
    ):
        platform_installer.install_helper_scripts()
        worktree = platform_installer._worktree_path_for("scripts--main")
        (worktree / ".git").unlink()

        with pytest.raises(PlatformInstallError, match=_not_a_worktree(worktree)):
            platform_installer.install_helper_scripts()

        _assert_enclosing_untouched(enclosing)


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub out the platform's `go build`; record the commit each build compiles."""
    built: list[str] = []

    def build(worktree: Path, dist_dir: Path) -> Path:
        built.append(_head(worktree))
        dist_dir.mkdir(parents=True, exist_ok=True)
        (dist_dir / ".complete").write_text("")
        binary = dist_dir / "service"
        binary.write_text("")
        return binary

    monkeypatch.setattr(platform_installer, "_build_service", build)
    return built


class TestPlatformInstall:
    def test_version_named_branch_is_rebuilt(self, origin: Path, builds: list[str]):
        """Not served from the first build's dist as if it were a release."""
        _git("branch", "release/v1.2.3", cwd=origin)
        platform_installer.install_platform_source("release/v1.2.3")
        tip = _advance(origin)
        _git("update-ref", "refs/heads/release/v1.2.3", tip, cwd=origin)

        dist = platform_installer.install_platform_source("release/v1.2.3")

        assert builds[1:] == [tip]
        assert dist.name == "release--v1.2.3"

    @pytest.mark.parametrize("kind", ["release", "sha"])
    def test_pinned_build_is_reused_without_origin(
        self, kind: str, origin: Path, builds: list[str]
    ):
        """Neither can move, so a finished dist needs no fetch: `install lts`
        and `install release` work offline once built."""
        _git("tag", "service/v1.2.3", cwd=origin)
        ref = "v1.2.3" if kind == "release" else _head(origin)
        dist = platform_installer.install_platform_source(ref)
        shutil.rmtree(origin)

        assert platform_installer.install_platform_source(ref) == dist
        assert len(builds) == 1

    def test_moved_release_is_rebuilt_once_its_dist_is_removed(
        self, origin: Path, builds: list[str]
    ):
        """The cached dist is served without a fetch, so it keeps the old
        commit; AGENTS.md says to remove it."""
        _git("tag", "service/v1.2.3", cwd=origin)
        dist = platform_installer.install_platform_source("v1.2.3")
        moved = _advance(origin)
        _git("tag", "-f", "service/v1.2.3", moved, cwd=origin)
        platform_installer.install_platform_source("v1.2.3")
        assert len(builds) == 1

        shutil.rmtree(dist)
        platform_installer.install_platform_source("v1.2.3")

        assert builds[1:] == [moved]


class TestInstallTip:
    def test_branch_gone_from_origin_is_an_error_not_a_traceback(self, origin: Path):
        _check_out("sdk", origin, "main")
        _git("branch", "-D", "other", cwd=origin)

        result = CliRunner().invoke(install_app, ["tip", "--ref", "other", "js"])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert "Error: branch 'other' is not on origin" in result.output

    def test_platform_branch_without_a_slash(self, origin: Path, builds: list[str]):
        """The `tip` docstring's own example. Not a version, so not looked up
        as the tag `service/vmy-branch`."""
        _git("branch", "my-branch", cwd=origin)

        result = CliRunner().invoke(install_app, ["tip", "--ref", "my-branch", "platform"])

        assert result.exit_code == 0, result.output
        assert builds == [_head(origin)]
        assert (origin.parent / "platform" / "dist" / "my-branch" / "service").exists()


class TestCheckoutCommand:
    def test_go_comes_from_the_platform_monorepo(self, origin: Path):
        result = CliRunner().invoke(app, ["checkout", "go", "main"])

        assert result.exit_code == 0, result.output
        link = origin.parent / "go" / "src" / "main"
        assert link.is_symlink()
        assert link.resolve() == origin.parent / "go" / "platform-src" / "main" / "otdfctl"
        assert _head(link) == _head(origin)

    def test_all_checks_out_every_sdk(self, origin: Path):
        """go is first in the list, so its failure used to stop js and java
        being checked out at all."""
        result = CliRunner().invoke(app, ["checkout", "--all", "main"])

        assert result.exit_code == 0, result.output
        for sdk in ("go", "js", "java"):
            assert _head(origin.parent / sdk / "src" / "main") == _head(origin), sdk

    def test_failed_git_command_shows_gits_stderr(self, origin: Path):
        """checkout._run captures it; without it the error is just an exit status."""
        result = CliRunner().invoke(app, ["checkout", "js", "no-such-ref"])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert "returned non-zero exit status" in result.output
        assert "invalid reference: no-such-ref" in result.output

    def test_go_ref_without_otdfctl_is_an_error_not_a_traceback(self, origin: Path):
        """A platform ref from before otdfctl moved into the monorepo."""
        _git("switch", "-q", "-c", "old", cwd=origin)
        _git("rm", "-q", "-r", "otdfctl", cwd=origin)
        _git("commit", "-q", "-m", "before otdfctl", cwd=origin)

        result = CliRunner().invoke(app, ["checkout", "go", "old"])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert "has no otdfctl/ directory" in result.output

    @pytest.mark.parametrize("args", [[], ["rust"]], ids=["no-sdk", "unknown-sdk"])
    def test_usage_error_is_reported_once(self, args: list[str], origin: Path):
        """The missing-SDK exit is a typer.Exit, which is a RuntimeError, so the
        handler could report it twice. An unknown SDK raises a plain ValueError,
        not a CheckoutError, so a narrower handler would let it through."""
        result = CliRunner().invoke(app, ["checkout", *args])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert result.output.count("Error:") == 1, result.output
