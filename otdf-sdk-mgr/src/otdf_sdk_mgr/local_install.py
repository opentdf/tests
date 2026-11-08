"""Build an SDK CLI from a commit in a local checkout: `install local`.

`install tip` builds only what origin has. This builds a commit that may exist
nowhere but the developer's checkout, such as an unpushed fix, or one of
several changes across repos that should be tested together before any is
published.

The checkout is only read. The commit is cloned into the directory a source
build uses (`src/<name>`; for go, `platform-src/<name>` plus the `src/<name>`
symlink, as `install tip` lays it out), and the SDK's own Makefile builds it
there. Building in place would write `target/` and `node_modules/` into the
checkout, and a worktree would add to its refs and worktree list.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from otdf_sdk_mgr.config import get_sdk_dirs
from otdf_sdk_mgr.installers import InstallError
from otdf_sdk_mgr.semver import SEMVER_RE

DEFAULT_NAME = "local"

# What the commit has to contain to be built as each SDK, and the repo that
# is. Checked in the commit, not the working copy, since that is what builds.
_REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    # The go Makefile builds otdfctl/ against the platform's go.work.
    "go": ("go.work", "otdfctl/go.mod"),
    # It copies cmdline/target/cmdline.jar out of a full reactor build.
    "java": ("pom.xml", "cmdline/pom.xml"),
    # It runs `make cli`, which packs lib/ and then cli/.
    "js": ("Makefile", "lib/package.json", "cli/package.json"),
}
_REPOS = {"go": "opentdf/platform", "java": "opentdf/java-sdk", "js": "opentdf/web-sdk"}

# Marks a clone as made by `install local`, and names the checkout it copies.
# It lives in the clone's own config. A clone without it may be a tip worktree
# or a checkout placed by hand, maybe with uncommitted work, so it is never
# deleted to make room.
_SOURCE_KEY = "otdf-sdk-mgr.source"

# A dist/ name: one path component, one word for make's VERSIONS and for
# xtest's whitespace-separated --sdks.
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# A commit as `install tip` names one: full SHAs, abbreviations, `v`-prefixed.
_SHA_LIKE_RE = re.compile(r"v?[0-9a-f]{7,64}")
# jj change ids are spelled with k-z only. git can't resolve them.
_JJ_CHANGE_ID_RE = re.compile(r"[k-z]+")


class LocalInstallError(InstallError):
    """A local checkout can't be built, or its build has nowhere safe to go."""


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git, capturing its output; the caller checks the exit status."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise LocalInstallError(f"executable not found: git ({e})") from e


@dataclass(frozen=True, slots=True)
class _Layout:
    """Where one named local build lives under `xtest/sdk/<sdk>/`."""

    sdk_dir: Path
    # The clone. For go it holds the whole platform, not just otdfctl/.
    clone_dir: Path
    # What make builds, `src/<name>`: the clone itself, or for go a symlink to
    # its otdfctl/.
    src_entry: Path
    dist_dir: Path

    @classmethod
    def of(cls, sdk: str, name: str) -> _Layout:
        sdk_dir = get_sdk_dirs()[sdk]
        src_entry = sdk_dir / "src" / name
        clone_dir = sdk_dir / "platform-src" / name if sdk == "go" else src_entry
        return cls(sdk_dir, clone_dir, src_entry, sdk_dir / "dist" / name)


@dataclass(frozen=True, slots=True)
class LocalRecord:
    """What `dist/<name>/.version` says a local build was built from."""

    source: str | None
    sha: str | None


def check_name(name: str) -> str:
    """Return `name` if a local build may use it as its dist/ name.

    Refuses the names release and tip installs give their builds, so neither
    replaces the other's: `main`, `HEAD`, versions, and SHAs. They are
    compared casefolded, since on a case-insensitive disk (macOS's default)
    `Main` is `main`. A branch slug can't be refused here, since any word can
    be a branch; `install_local` refuses to replace a build it didn't make.
    """
    if not _NAME_RE.fullmatch(name) or name.endswith(".git"):
        # The Makefiles skip `*.git` entries, which are tip's bare repos.
        raise LocalInstallError(
            f"--name {name!r} must be letters, digits, '.', '_' and '-', start with "
            "a letter or digit, and not end in .git"
        )
    folded = name.casefold()
    if (
        folded in ("main", "head")
        or SEMVER_RE.match(folded)
        or _SHA_LIKE_RE.fullmatch(folded)
        or folded.startswith("refs--")
    ):
        raise LocalInstallError(
            f"--name {name!r} is a name release and tip installs use; choose another"
        )
    return name


def find_repo_root(sdk: str, path: Path) -> Path:
    """The root of the git checkout at `path`, which must be that root.

    For go, `path` may also be the platform's otdfctl/ directory. Any other
    subdirectory is refused rather than built from its root: `web-sdk/lib`
    names a package that this would not build on its own.
    """
    path = path.expanduser()
    if not path.is_dir():
        raise LocalInstallError(f"{path} is not a directory")
    path = path.resolve()
    result = _git("-C", str(path), "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise LocalInstallError(
            f"{path} is not a git checkout (a jj repo must be colocated): {result.stderr.strip()}"
        )
    root = Path(result.stdout.strip()).resolve()
    if path == root or (sdk == "go" and path == root / "otdfctl"):
        return root
    raise LocalInstallError(
        f"{path} is inside the git checkout {root}; pass the repository root"
        + (" or its otdfctl/ directory" if sdk == "go" else "")
    )


def resolve_commit(repo: Path, rev: str) -> str:
    """The full SHA of the commit `rev` names in `repo`.

    Any revision git resolves will do, including a commit no ref points at,
    such as a jj working-copy commit. `--end-of-options` keeps a rev that
    starts with `-` from being read as an option.
    """
    result = _git(
        "-C", str(repo), "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"
    )
    sha = result.stdout.strip()
    if result.returncode == 0 and sha:
        return sha
    hint = ""
    if (repo / ".jj").is_dir() and _JJ_CHANGE_ID_RE.fullmatch(rev):
        hint = (
            f"; a jj change id is not a git revision, so pass its commit id "
            f"(`jj log -r {rev} --no-graph -T commit_id`)"
        )
    raise LocalInstallError(f"--rev {rev!r} names no commit in {repo}{hint}")


def check_tree(sdk: str, repo: Path, sha: str) -> None:
    """Raise unless commit `sha` of `repo` looks like the `sdk` repo."""
    missing = [
        path
        for path in _REQUIRED_FILES[sdk]
        if _git("-C", str(repo), "cat-file", "-e", f"{sha}:{path}").returncode != 0
    ]
    if missing:
        hint = " (otdfctl builds from the platform monorepo since v0.31.0)" if sdk == "go" else ""
        raise LocalInstallError(
            f"{repo} at {sha[:12]} doesn't look like {_REPOS[sdk]}{hint}: "
            f"it has no {', '.join(missing)}"
        )


def read_record(dist_dir: Path) -> LocalRecord:
    """Read the `key=value` `.version` that `_write_record` writes.

    The keys are those `bench_prepare.read_dist_commit` reads too. A record
    with no `source` was written by another installer, or is absent.
    """
    fields: dict[str, str] = {}
    try:
        text = (dist_dir / ".version").read_text()
    except OSError:
        return LocalRecord(None, None)
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
    return LocalRecord(fields.get("source"), fields.get("sha"))


def _write_record(dist_dir: Path, source: Path, rev: str, sha: str) -> None:
    (dist_dir / ".version").write_text(f"source={source}\nrev={rev}\nsha={sha}\n")


def _clone_source(clone_dir: Path) -> str | None:
    """The checkout a clone made by `install local` copies, or None for any other directory.

    `--git-dir` rather than `-C`: from a directory that is no repo, `-C`
    would walk up into the tests repo and read its config.
    """
    git_dir = clone_dir / ".git"
    if not git_dir.is_dir():
        return None
    result = _git(f"--git-dir={git_dir}", "config", "--local", "--get", _SOURCE_KEY)
    return result.stdout.strip() if result.returncode == 0 else None


def _go_link_target(name: str) -> Path:
    """The `src/<name>` symlink target, relative as `checkout_go_from_platform` writes it."""
    return Path("..") / "platform-src" / name / "otdfctl"


def _present(path: Path) -> bool:
    """True for anything at `path`, a dangling symlink included."""
    return path.exists() or path.is_symlink()


def _check_ours(sdk: str, layout: _Layout) -> None:
    """Raise if building would replace something `install local` didn't make.

    The name is ours if our clone holds it, or, with the clone deleted (as
    `clean --src-only` does), if the dist records a local source. A dist
    without that record next to our clone is one whose build died before
    recording, so it is ours too.
    """

    def refuse(path: Path, what: str) -> LocalInstallError:
        return LocalInstallError(
            f"{path} exists and is {what}, not a build `install local` made; "
            "remove it or choose another --name"
        )

    ours = False
    if _present(layout.clone_dir):
        if _clone_source(layout.clone_dir) is None:
            raise refuse(layout.clone_dir, "a tip worktree or a checkout placed by hand")
        ours = True
    if sdk == "go" and _present(layout.src_entry):
        target = _go_link_target(layout.src_entry.name)
        if not layout.src_entry.is_symlink() or Path(os.readlink(layout.src_entry)) != target:
            raise refuse(layout.src_entry, "a checkout placed by hand")
    if layout.dist_dir.exists() and not ours and read_record(layout.dist_dir).source is None:
        raise refuse(layout.dist_dir, "a release or tip build")


def _fresh_clone(repo: Path, sha: str, layout: _Layout) -> None:
    """Replace the clone with one of `repo` with `sha` checked out.

    A new clone each time rather than an update: git copies or hard-links the
    whole object store, so any commit `repo` has is there, a jj working-copy
    commit that no ref names included, and nothing is left from the last
    build. The Makefiles' `npm ci` and `mvn clean` discard earlier output
    anyway, and go caches builds outside the tree.
    """
    if _present(layout.clone_dir):
        shutil.rmtree(layout.clone_dir)
    layout.clone_dir.parent.mkdir(parents=True, exist_ok=True)
    clone = str(layout.clone_dir)
    for args in (
        ("clone", "--quiet", "--local", "--no-checkout", str(repo), clone),
        ("-C", clone, "config", "--local", _SOURCE_KEY, str(repo)),
        ("-C", clone, "checkout", "--quiet", "--detach", sha),
    ):
        result = _git(*args)
        if result.returncode != 0:
            raise LocalInstallError(
                f"could not copy {sha[:12]} from {repo}: {result.stderr.strip()}"
            )
    if layout.src_entry != layout.clone_dir:
        if _present(layout.src_entry):
            layout.src_entry.unlink()
        layout.src_entry.parent.mkdir(parents=True, exist_ok=True)
        layout.src_entry.symlink_to(_go_link_target(layout.src_entry.name))


def install_local(sdk: str, path: Path, rev: str = "HEAD", name: str | None = None) -> Path:
    """Build `sdk`'s CLI from commit `rev` of the checkout at `path`; return its dist dir.

    Reuses `dist/<name>` if its `.version` records this checkout and commit,
    and rebuilds it otherwise. Raises LocalInstallError, before building
    anything, if the checkout or commit is unusable or the name is taken by
    another installer's build; and if the build fails.
    """
    if sdk not in _REQUIRED_FILES:
        raise LocalInstallError(
            f"Unsupported SDK '{sdk}'. Must be one of: {', '.join(_REQUIRED_FILES)}"
        )
    name = check_name(DEFAULT_NAME if name is None else name)
    repo = find_repo_root(sdk, path)
    sha = resolve_commit(repo, rev)
    check_tree(sdk, repo, sha)
    layout = _Layout.of(sdk, name)
    _check_ours(sdk, layout)

    if read_record(layout.dist_dir) == LocalRecord(str(repo), sha):
        print(f"  {layout.dist_dir} is already {sha[:12]} from {repo}; reusing.")
        return layout.dist_dir

    # Flushed, or a piped log shows it after make's output.
    print(f"Building {sdk} from {repo} at {sha[:12]} into {layout.dist_dir}...", flush=True)
    if layout.dist_dir.exists():
        shutil.rmtree(layout.dist_dir)
    _fresh_clone(repo, sha, layout)

    env = os.environ.copy()
    env["VERSIONS"] = name
    if sdk == "go":
        # As cmd_tip does. The Makefile would find ../go.work itself, but an
        # inherited GOWORK would win over it.
        env["GOWORK"] = str(layout.clone_dir / "go.work")
    try:
        subprocess.check_call(["make"], cwd=layout.sdk_dir, env=env)
    except BaseException as e:
        # Unrecorded, a partial dist would never be reused, but xtest would
        # still list it as a version, one with no cli.sh.
        shutil.rmtree(layout.dist_dir, ignore_errors=True)
        if isinstance(e, subprocess.CalledProcessError):
            raise LocalInstallError(
                f"make failed building {sdk} from {layout.clone_dir} (exit {e.returncode})"
            ) from e
        if isinstance(e, OSError):
            raise LocalInstallError(f"could not run make in {layout.sdk_dir}: {e}") from e
        raise
    if not layout.dist_dir.is_dir():
        raise LocalInstallError(f"make built {sdk}@{name} but {layout.dist_dir} is missing")
    _write_record(layout.dist_dir, repo, rev, sha)
    print(f"  {sdk} built from {repo} at {sha[:12]}")
    return layout.dist_dir
