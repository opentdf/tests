"""`install local` against real git, with temporary checkouts, a fake make, and no network."""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from otdf_sdk_mgr import config, local_install
from otdf_sdk_mgr.cli_install import install_app
from otdf_sdk_mgr.local_install import LocalInstallError, install_local, read_record

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

SDKS = ["go", "java", "js"]

# The files each SDK's tree is recognised by.
FILES = {
    "go": ("go.work", "otdfctl/go.mod", "sdk/go.mod"),
    "java": ("pom.xml", "cmdline/pom.xml", "sdk/pom.xml"),
    "js": ("Makefile", "lib/package.json", "cli/package.json"),
    # The archived standalone opentdf/otdfctl repo.
    "otdfctl": ("go.mod", "main.go"),
}
# The file the fake make "builds": its contents land in dist, so the dist says
# which commit it was built from. Relative to the repo root.
BUILT = {"go": "otdfctl/go.mod", "java": "cmdline/pom.xml", "js": "cli/package.json"}

CheckoutFactory = Callable[..., Path]


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _head(repo: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=repo)


def _commit(repo: Path, sdk: str) -> str:
    """Change the built file and commit it; return the new commit."""
    with (repo / BUILT[sdk]).open("a") as f:
        f.write("next\n")
    _git("commit", "-q", "-am", "next", cwd=repo)
    return _head(repo)


def _built(dist: Path) -> str:
    return (dist / "built").read_text()


def _snapshot(repo: Path) -> dict[str, tuple[int, int]]:
    """Every path under `repo`, `.git` included, with its size and mtime.

    Covers the work tree's files, and git's refs, worktree list, remotes and
    config, which all live under `.git/`.
    """
    return {
        str(p.relative_to(repo)): (p.lstat().st_size, p.lstat().st_mtime_ns)
        for p in repo.rglob("*")
    }


@pytest.fixture
def sdk_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_git: None) -> Path:
    """An empty xtest/sdk; git can't walk up out of tmp_path into a real repo."""
    root = tmp_path / "sdk"
    for sdk in SDKS:
        (root / sdk).mkdir(parents=True)
    monkeypatch.setenv("OTDF_SDK_DIR", str(root))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return root


@pytest.fixture
def checkout(tmp_path: Path, sdk_root: Path) -> CheckoutFactory:
    """Make a one-commit checkout shaped like an SDK's repo."""

    def make(sdk: str, name: str = "checkout") -> Path:
        repo = tmp_path / name
        repo.mkdir()
        _git("init", "-q", "-b", "main", cwd=repo)
        for path in FILES[sdk]:
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text(f"{path}\n")
        _git("add", ".", cwd=repo)
        _git("commit", "-q", "-m", "first", cwd=repo)
        return repo

    return make


@pytest.fixture
def make(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """Stand in for the SDK Makefiles: build `src/$VERSIONS` into `dist/$VERSIONS`.

    Returns the environment of each call. Like the go Makefile, it reads go's
    `src/<name>` through the symlink, so a link to the wrong place fails here.
    """
    calls: list[dict[str, str]] = []

    def fake_make(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
        assert cmd == ["make"]
        sdk = Path(cwd).name
        name = env["VERSIONS"]
        src = Path(cwd) / "src" / name
        built = BUILT[sdk].removeprefix("otdfctl/") if sdk == "go" else BUILT[sdk]
        dist = Path(cwd) / "dist" / name
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "cli.sh").write_text("#!/bin/sh\n")
        (dist / "built").write_text((src / built).read_text())
        calls.append(env)
        return 0

    monkeypatch.setattr(local_install.subprocess, "check_call", fake_make)
    return calls


def _install(*args: str) -> Result:
    return CliRunner().invoke(install_app, ["local", *args])


@pytest.mark.parametrize("sdk", SDKS)
class TestEverySdk:
    def test_builds_the_checked_out_commit(
        self, sdk: str, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        repo = checkout(sdk)

        result = _install(sdk, str(repo))

        assert result.exit_code == 0, result.output
        assert f"--sdks {sdk}@local" in result.output
        dist = sdk_root / sdk / "dist" / "local"
        assert _built(dist) == (repo / BUILT[sdk]).read_text()
        assert make[0]["VERSIONS"] == "local"
        record = (dist / ".version").read_text()
        assert record == f"source={repo.resolve()}\nrev=HEAD\nsha={_head(repo)}\n"

    def test_same_commit_reuses_the_build(self, sdk: str, checkout: CheckoutFactory, make: list):
        repo = checkout(sdk)
        install_local(sdk, repo)

        install_local(sdk, repo)

        assert len(make) == 1

    def test_new_commit_rebuilds(self, sdk: str, checkout: CheckoutFactory, make: list):
        repo = checkout(sdk)
        dist = install_local(sdk, repo)
        tip = _commit(repo, sdk)

        install_local(sdk, repo)

        assert len(make) == 2
        assert _built(dist) == (repo / BUILT[sdk]).read_text()
        assert read_record(dist).sha == tip

    def test_checkout_is_unchanged_and_only_its_commit_is_built(
        self, sdk: str, checkout: CheckoutFactory, make: list
    ):
        """No build output, worktrees, refs or remotes land in the checkout,
        and its uncommitted edits stay out of the build."""
        repo = checkout(sdk)
        committed = (repo / BUILT[sdk]).read_text()
        (repo / BUILT[sdk]).write_text("uncommitted\n")
        (repo / "untracked").write_text("untracked\n")
        before = _snapshot(repo)

        dist = install_local(sdk, repo)

        assert _snapshot(repo) == before
        assert _built(dist) == committed

    def test_another_sdks_tree_is_refused_before_building(
        self, sdk: str, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        other = SDKS[(SDKS.index(sdk) + 1) % len(SDKS)]
        repo = checkout(other)

        with pytest.raises(LocalInstallError, match="doesn't look like opentdf/"):
            install_local(sdk, repo)

        assert make == []
        assert not (sdk_root / sdk / "src").exists()


class TestCheckoutPath:
    def test_missing_directory(self, tmp_path: Path, sdk_root: Path):
        with pytest.raises(LocalInstallError, match="is not a directory"):
            install_local("js", tmp_path / "nowhere")

    def test_directory_that_is_not_a_git_checkout(self, tmp_path: Path, sdk_root: Path):
        (tmp_path / "plain").mkdir()

        with pytest.raises(LocalInstallError, match="is not a git checkout"):
            install_local("js", tmp_path / "plain")

    def test_subdirectory_is_refused(self, checkout: CheckoutFactory, make: list):
        """`web-sdk/lib` is a package this would not build on its own."""
        repo = checkout("js")

        with pytest.raises(LocalInstallError, match="pass the repository root$"):
            install_local("js", repo / "lib")

    def test_go_accepts_the_platforms_otdfctl_directory(
        self, checkout: CheckoutFactory, make: list
    ):
        repo = checkout("go")

        dist = install_local("go", repo / "otdfctl")

        assert read_record(dist).source == str(repo.resolve())

    def test_go_refuses_other_platform_subdirectories(self, checkout: CheckoutFactory, make: list):
        repo = checkout("go")

        with pytest.raises(LocalInstallError, match="or its otdfctl/ directory"):
            install_local("go", repo / "sdk")

    def test_tree_is_checked_at_the_commit_not_the_working_copy(
        self, checkout: CheckoutFactory, make: list
    ):
        """Only the commit is built, so files that aren't committed don't count."""
        repo = checkout("js")
        for path in FILES["java"]:
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text("uncommitted\n")

        with pytest.raises(LocalInstallError, match="it has no pom.xml, cmdline/pom.xml"):
            install_local("java", repo)

    def test_standalone_otdfctl_repo_is_pointed_at_the_platform(self, checkout: CheckoutFactory):
        repo = checkout("otdfctl")

        with pytest.raises(LocalInstallError, match="platform monorepo"):
            install_local("go", repo)


class TestRev:
    def test_unpushed_branch(self, checkout: CheckoutFactory, make: list):
        """Any branch the checkout has, including one not checked out."""
        repo = checkout("js")
        _git("checkout", "-q", "-b", "feature", cwd=repo)
        feature = _commit(repo, "js")
        _git("checkout", "-q", "main", cwd=repo)

        dist = install_local("js", repo, rev="feature")

        assert read_record(dist).sha == feature
        assert _built(dist) == "cli/package.json\nnext\n"

    def test_commit_no_ref_points_at(self, checkout: CheckoutFactory, make: list):
        """As a jj working-copy commit is: git's object store has it, and no ref names it."""
        repo = checkout("js")
        dangling = _commit(repo, "js")
        _git("reset", "-q", "--hard", "HEAD~1", cwd=repo)

        dist = install_local("js", repo, rev=dangling[:10])

        assert read_record(dist).sha == dangling

    def test_unknown_rev(self, checkout: CheckoutFactory, make: list):
        repo = checkout("js")

        with pytest.raises(LocalInstallError, match="--rev 'nope' names no commit"):
            install_local("js", repo, rev="nope")
        assert make == []

    def test_jj_change_id_gets_a_hint(self, checkout: CheckoutFactory, make: list):
        repo = checkout("js")
        (repo / ".jj").mkdir()

        with pytest.raises(LocalInstallError, match="jj log -r kxqz --no-graph -T commit_id"):
            install_local("js", repo, rev="kxqz")


class TestName:
    @pytest.mark.parametrize(
        "name",
        [
            "main",
            "Main",
            "HEAD",
            "v1.2.3",
            "1.2.3",
            "V0.9.0-rc.1",
            "a" * 40,
            "v" + "a" * 40,
            "abc1234",
            "refs--pull--1--head",
        ],
    )
    def test_release_and_tip_names_are_refused(
        self, name: str, checkout: CheckoutFactory, make: list
    ):
        repo = checkout("js")

        with pytest.raises(LocalInstallError, match="a name release and tip installs use"):
            install_local("js", repo, name=name)
        assert make == []

    @pytest.mark.parametrize("name", ["", "a/b", "a b", ".", "..", "-x", "x.git", "go@x"])
    def test_names_that_are_no_single_word_or_directory_are_refused(
        self, name: str, checkout: CheckoutFactory, make: list
    ):
        repo = checkout("js")

        with pytest.raises(LocalInstallError, match="must be letters, digits"):
            install_local("js", repo, name=name)

    @pytest.mark.parametrize("sdk", SDKS)
    def test_explicit_name(self, sdk: str, checkout: CheckoutFactory, make: list, sdk_root: Path):
        repo = checkout(sdk)

        result = _install(sdk, str(repo), "--name", "my-fix.2")

        assert result.exit_code == 0, result.output
        assert f"--sdks {sdk}@my-fix.2" in result.output
        assert (sdk_root / sdk / "dist" / "my-fix.2" / "built").exists()

    @pytest.mark.parametrize("sdk", ["java", "js"])
    def test_tip_worktree_under_the_name_is_not_replaced(
        self, sdk: str, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        """A checkout there may hold someone's uncommitted work."""
        repo = checkout(sdk)
        theirs = checkout(sdk, name="theirs")
        _git(
            "worktree", "add", "-q", "--detach", str(sdk_root / sdk / "src" / "feature"), cwd=theirs
        )

        with pytest.raises(LocalInstallError, match="a tip worktree or a checkout placed by hand"):
            install_local(sdk, repo, name="feature")
        assert make == []
        assert (sdk_root / sdk / "src" / "feature" / ".git").is_file()

    def test_go_checkout_placed_by_hand_is_not_replaced(
        self, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        repo = checkout("go")
        (sdk_root / "go" / "src" / "local").mkdir(parents=True)

        with pytest.raises(LocalInstallError, match="a checkout placed by hand"):
            install_local("go", repo)
        assert make == []

    @pytest.mark.parametrize("version_file", [None, "ref=feature\nsha=" + "a" * 40 + "\n"])
    def test_another_installers_dist_is_not_replaced(
        self, version_file: str | None, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        """A tip build of a branch slugs to any name; this one is `feature`."""
        repo = checkout("js")
        dist = sdk_root / "js" / "dist" / "feature"
        dist.mkdir(parents=True)
        if version_file is not None:
            (dist / ".version").write_text(version_file)

        with pytest.raises(LocalInstallError, match="a release or tip build"):
            install_local("js", repo, name="feature")
        assert make == []
        assert dist.is_dir()


class TestRecord:
    def test_build_from_another_checkout_at_the_same_commit_is_rebuilt(
        self, tmp_path: Path, checkout: CheckoutFactory, make: list
    ):
        """The record names the checkout as well as the commit."""
        repo = checkout("js")
        copy = tmp_path / "copy"
        _git("clone", "-q", str(repo), str(copy), cwd=tmp_path)
        install_local("js", repo)

        dist = install_local("js", copy)

        assert len(make) == 2
        assert read_record(dist).source == str(copy.resolve())

    def test_dist_is_reused_after_its_source_copy_is_removed(
        self, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        """`clean --src-only` deletes the java and js clones but leaves the dists."""
        repo = checkout("js")
        install_local("js", repo)
        shutil.rmtree(sdk_root / "js" / "src" / "local")

        install_local("js", repo)

        assert len(make) == 1

    def test_unrecorded_dist_beside_its_clone_is_rebuilt(
        self, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        """A build killed after make made the dist but before it was recorded."""
        repo = checkout("js")
        dist = install_local("js", repo)
        (dist / ".version").unlink()

        install_local("js", repo)

        assert len(make) == 2
        assert read_record(dist).sha == _head(repo)


class TestFailedBuild:
    def test_partial_dist_is_removed_and_the_next_run_rebuilds(
        self, checkout: CheckoutFactory, monkeypatch: pytest.MonkeyPatch, sdk_root: Path
    ):
        repo = checkout("js")
        dist = sdk_root / "js" / "dist" / "local"

        def failing_make(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
            dist.mkdir(parents=True)
            raise subprocess.CalledProcessError(2, cmd)

        monkeypatch.setattr(local_install.subprocess, "check_call", failing_make)
        result = _install("js", str(repo))

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert "Error: make failed building js" in result.output
        assert not dist.exists()

        monkeypatch.setattr(
            local_install.subprocess, "check_call", lambda cmd, cwd, env: dist.mkdir()
        )
        install_local("js", repo)
        assert read_record(dist).sha == _head(repo)


class TestGoLayout:
    def test_platform_is_cloned_beside_tips_and_linked_into_src(
        self, checkout: CheckoutFactory, make: list, sdk_root: Path
    ):
        """As `install tip` lays go out, so the Makefile builds otdfctl/ against
        the clone's go.work."""
        repo = checkout("go")

        install_local("go", repo)

        clone = sdk_root / "go" / "platform-src" / "local"
        link = sdk_root / "go" / "src" / "local"
        assert _head(clone) == _head(repo)
        assert os.readlink(link) == os.path.join("..", "platform-src", "local", "otdfctl")
        assert make[0]["GOWORK"] == str(clone / "go.work")


class TestInstallTipUnchanged:
    def test_unpushed_branch_built_locally_is_still_refused_by_tip(
        self,
        tmp_path: Path,
        checkout: CheckoutFactory,
        make: list,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """`install local` reads the checkout; `install tip` still reads only origin."""
        origin = checkout("js", name="origin")
        monkeypatch.setitem(config.SDK_GIT_URLS, "js", str(origin))
        dev = tmp_path / "dev"
        _git("clone", "-q", str(origin), str(dev), cwd=tmp_path)
        _git("checkout", "-q", "-b", "feature", cwd=dev)
        _commit(dev, "js")
        install_local("js", dev, rev="feature")

        result = CliRunner().invoke(install_app, ["tip", "--ref", "feature", "js"])

        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert "invalid reference: feature" in result.output
        assert len(make) == 1
