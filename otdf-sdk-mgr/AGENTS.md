# otdf-sdk-mgr - Agent Guide

Python CLI that installs SDK CLIs (`go`, `java`, `js`) and the OpenTDF
platform service from released artifacts or source. Outputs land in
`xtest/sdk/{go,java,js}/dist/<version>/` and `xtest/platform/dist/<version>/`.

Full command reference: [README.md](README.md).

## Subcommand Layout

| File | Subcommand | Responsibility |
|------|------------|----------------|
| `cli_install.py` | `install {stable,lts,tip,release,scripts,artifact,scenario,benchmark}` | All `install` subcommands; delegates per-SDK work to `installers.py` and platform work to `platform_installer.py`. |
| `cli_scenario.py` | `install scenario <path>` | Reads `scenarios.yaml` / `instance.yaml`, installs every referenced artifact, writes `<name>.installed.json`. |
| `cli_versions.py` | `versions {list,resolve}` | Lists released versions (`--latest N` filters most-recent) and resolves tags to SHAs. |
| `bench_prepare.py` | (lib) | `install benchmark`: resolves the arms, checks collisions and neutrality, installs, and writes `benchmark.installed.json` on every exit path. |
| `manifest.py` | (lib) | The benchmark installation manifest (schema `v1alpha1`): its data model, strict reader and atomic writer, plus the pre-build checks on resolved artifacts (dist slug, collision, neutrality). |
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
- **Platform tags are namespaced** as `service/vX.Y.Z`. `_resolve_platform_ref`
  prefixes the `service/` infix on plain versions; raw SHAs, refs with a
  `/`, `pr:N` shorthand (expanded to `refs/pull/N/head`), and `main`/`HEAD`
  pass through unchanged.
- **PR refs aren't under `refs/heads/`,** so `BARE_REFRESH` never pulls
  `refs/pull/N/head`. `_ensure_worktree` (and the SDK equivalents in
  `checkout.py`) explicitly `fetch origin +refs/...:refs/...` for any
  `refs/...` ref before adding or resetting the worktree. Otherwise `git
  worktree add refs/pull/N/head` dies with `invalid reference`, and a reset
  rebuilds the PR head as it was at the last fetch.
- **Mutable refs auto-refresh; immutable refs cache.** `refs.is_mutable_ref`
  treats full-length hex SHAs and `<infix>/vX.Y.Z` tag forms as immutable
  (reuse existing dist), and everything else as mutable (re-fetch the bare
  repo, `git reset --hard` the worktree, drop the stale binary, rebuild).
  Don't reintroduce an unconditional dist-exists skip — it silently serves
  stale binaries when a user installs the same branch a second time.
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
