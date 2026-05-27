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
| `cli_versions.py` | `versions {list,latest}` | Lists released versions across registries. |
| `installers.py` | (lib) | Per-SDK install logic for go/java/js. |
| `platform_installer.py` | (lib) | Builds the platform `service` binary via git worktrees on a bare clone. |
| `schema.py` | (lib) | Pydantic models for `Scenario` / `Instance` + `load_yaml_mapping`. |

## Platform Install via Git Worktrees

`platform_installer.py` keeps a **bare clone** at `xtest/platform/src/platform.git`
and `git worktree add`s each requested ref into a sibling directory. A few
gotchas worth knowing before editing this module:

- **Worktrees from a bare clone have no `origin` remote.** `git pull` inside
  the worktree will fail. Update by fetching into the bare repo first
  (`_ensure_bare_repo()` already does this), then `git -C <worktree> reset
  --hard <branch>` to move the worktree HEAD to the refreshed ref.
- **Platform tags are namespaced** as `service/vX.Y.Z`. `_resolve_platform_ref`
  prefixes the `service/` infix on plain versions; raw SHAs, refs with a
  `/`, `pr:N` shorthand (expanded to `refs/pull/N/head`), and `main`/`HEAD`
  pass through unchanged.
- **PR refs aren't in the default bare-clone refspec.** `git clone --bare`
  sets `+refs/heads/*:refs/heads/*`, so `fetch --all --tags` never pulls
  `refs/pull/N/head`. `_ensure_worktree` (and the SDK equivalents in
  `checkout.py`) explicitly `fetch origin +refs/...:refs/...` for any
  `refs/...` ref before adding the worktree, otherwise `git worktree add
  refs/pull/N/head` dies with `invalid reference`.
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
