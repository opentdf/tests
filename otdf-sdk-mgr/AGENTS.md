# otdf-sdk-mgr - Agent Guide

Python CLI that installs SDK CLIs (`go`, `java`, `js`) and the OpenTDF
platform service from released artifacts or source. Outputs land in
`xtest/sdk/{go,java,js}/dist/<version>/` and `xtest/platform/dist/<version>/`.

Full command reference: [README.md](README.md).

## Subcommand Layout

| File | Subcommand | Responsibility |
|------|------------|----------------|
| `cli_install.py` | `install {stable,lts,tip,release,scripts,artifact,scenario}` | All `install` subcommands; delegates per-SDK work to `installers.py` and platform work to `platform_installer.py`. |
| `cli_scenario.py` | `install scenario <path>` | Reads `scenarios.yaml` / `instance.yaml`, installs every referenced artifact, writes `<name>.installed.json`. |
| `cli_versions.py` | `versions {list,resolve}` | Lists released versions (`--latest N` filters most-recent) and resolves tags to SHAs. |
| `installers.py` | (lib) | Per-SDK install logic for go/java/js. |
| `platform_installer.py` | (lib) | Builds the platform `service` binary via git worktrees on a bare clone. |
| `schema.py` | (lib) | Pydantic models for `Scenario` / `Instance` + `load_yaml_mapping`. |

## Platform Install via Git Worktrees

`platform_installer.py` keeps a **bare clone** at `xtest/platform/src/platform.git`
and `git worktree add`s each requested ref into a sibling directory.
`checkout.py` does the same for SDK sources. A few gotchas worth knowing
before editing either module:

- **A bare clone records no fetch refspec.** `git clone --bare` copies the
  branches once and sets no `remote.origin.fetch`. `git fetch` alone then
  updates no refs and `--tags` adds only tags, so the bare repo's own branches
  stay at clone time. `checkout.BARE_REFRESH` fetches origin's branches into
  `refs/remotes/origin/*` with `--prune`, and `checkout.upstream_ref` maps a
  branch name onto them. Don't check out the bare repo's local branches.
- **Worktrees are detached.** Add them with `worktree add --detach <path>
  <upstream_ref>` and refresh them with `git -C <worktree> reset --hard
  <upstream_ref>`. Don't `git pull` in one: with no fetch refspec or upstream,
  pull fetches origin's HEAD and integrates it into whatever is checked out,
  silently fast-forwarding a worktree onto the default branch when it can. Nor
  check out `FETCH_HEAD` after a `--git-dir=<bare>` fetch: `FETCH_HEAD` is per
  worktree, so the worktree would see a missing or stale one. Worktrees made
  by older versions may still have a branch checked out; the reset moves it,
  which is harmless.
- **Worktrees sit inside this repo's checkout,** gitignored. In one that has
  lost its `.git` file (an interrupted `clean` or `git worktree add`), `git -C
  <worktree>` climbs to opentdf/tests itself, and `reset --hard` there throws
  away the developer's uncommitted work. Call `checkout.require_worktree`
  before resetting an existing worktree; it refuses anything that isn't a
  worktree of the expected bare repo. The refresh runs `git worktree prune`,
  so a worktree directory that was removed can be added again.
- **Platform tags are namespaced** as `service/vX.Y.Z`. `_resolve_platform_ref`
  prefixes the `service/` infix on plain versions (`v0.9.0`, `0.9.0`) and
  nothing else. Branches, `HEAD`, SHAs, refs with a `/`, and `pr:N`
  shorthand (expanded to `refs/pull/N/head`) pass through unchanged.
  Prefixing every name that isn't obviously a ref would look up
  `install tip --ref my-branch platform` as the tag `service/vmy-branch`.
- **PR refs aren't under `refs/heads/`,** so `BARE_REFRESH` never pulls
  `refs/pull/N/head`. `_ensure_worktree` (and the SDK equivalents in
  `checkout.py`) explicitly `fetch origin +refs/...:refs/...` for any
  `refs/...` ref before adding or resetting the worktree. Otherwise `git
  worktree add refs/pull/N/head` dies with `invalid reference`, and a reset
  rebuilds the PR head as it was at the last fetch.
- **Mutable refs auto-refresh; immutable refs cache.** Ask origin, not the
  name: a branch can look like a version (web-sdk cuts `release/1.3.1`).
  After the bare-repo refresh, `refs.is_mutable_target` takes what
  `upstream_ref` resolved to a branch on origin (`refs/remotes/origin/*`),
  or any other `refs/...` ref but a tag, as mutable; only names it passed
  through fall back on the name heuristic `refs.is_mutable_ref`. Mutable
  means `git reset --hard` the worktree, and for the platform drop the stale
  binary and rebuild. `install_platform_source` looks for a cached dist
  before the refresh, so it reuses one only for a full SHA or a
  `service/vX.Y.Z` release (`_is_pinned`) and sends anything else through
  `_ensure_worktree` and a rebuild. Don't reintroduce an unconditional
  dist-exists skip — it silently serves stale binaries when a user installs
  the same branch a second time.
- Subprocess output is **not captured** — long-running `go build` / `git
  clone` streams to the terminal so users can see progress. On failure the
  error message just reports the command and exit code.

## Before Committing

Run from this directory:

```bash
uv run ruff check .    # lint — must pass
uv run ruff format .   # auto-format — re-stage rewritten files
uv run pyright         # type-check — must pass
uv run pytest -q       # unit tests
```

Use `uv run`, **not `uvx`** — `uvx` strips the project venv, so pyright
reports every project import as unresolved. See the root `AGENTS.md`
("Before Committing Python Changes") for the rationale.

## Adding a New Subcommand

1. Create or extend a `cli_<area>.py` module.
2. Register it in `cli.py` (the Typer app entry point), or — for `install`
   subcommands — under `install_app` in `cli_install.py`.
3. Wrap any library exceptions (`InstallError`, `PlatformInstallError`) at
   the CLI boundary and exit with `typer.Exit(1)`. The
   `_install_platform_or_exit` helper in `cli_install.py` shows the
   pattern for platform installers.
