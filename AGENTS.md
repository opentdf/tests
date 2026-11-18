# Agent Guide: Working with OpenTDF Tests and Debugging

This guide provides essential knowledge for AI agents performing updates, refactorings, and debugging of OpenTDF libraries and applications under test.

## Repository Layout

- `platform/` — platform service source, **installed by `otdf-sdk-mgr install platform`**, not committed. Edits here may be wiped by a reinstall.
- `xtest/sdk/{go,java,js}/dist/` — built SDK CLI wrappers, produced by `otdf-sdk-mgr install` (or by `cd xtest/sdk && make` for source builds).

## Test Framework Overview

### Configuring SDK Artifacts

Use `otdf-sdk-mgr` (uv-managed CLI in `otdf-sdk-mgr/`) to install SDK CLIs from released artifacts or source. See `otdf-sdk-mgr/README.md` for full command reference.

```bash
cd otdf-sdk-mgr && uv tool install --editable .
otdf-sdk-mgr install stable    # Latest stable releases (recommended)
otdf-sdk-mgr install tip go    # Build from source
```

### Running Tests

```bash
# Configure environment
cd xtest && set -a && source test.env && set +a

# Run with specific SDK
uv run pytest --sdks go -v

# Run with multiple SDKs (space-separated)
uv run pytest --sdks "go java js" -v
```

### Custom pytest Options and Env Vars

See `xtest/AGENTS.md` for the full table of `--sdks`, `--containers`,
`--no-audit-logs`, etc. Repo-wide environment variables:

- `PLATFORMURL` — platform endpoint (default `http://localhost:8080`)
- `OT_ROOT_KEY` — root key for key-management tests
- `SCHEMA_FILE` — path to manifest schema file
- `DISABLE_AUDIT_ASSERTIONS` — set to `1`/`true`/`yes` to skip audit-log assertions (CI equivalent of `--no-audit-logs`)

`XT_*` variables are documented in `xtest/AGENTS.md`.

**Evaluating an unreleased SDK fix?** Version gates in `xtest/sdk/*/cli.sh`
make the cell skip and the run go green without testing anything. Use
`XT_FORCE_SUPPORTS` — see "Evaluating an unreleased fix" in `xtest/AGENTS.md`.

### Audit Log Assertions

Audit-log assertions are **on by default** and tests fail loudly during
setup if KAS log files aren't reachable. This is deliberate — it catches
audit-event regressions and clock-skew issues that would otherwise hide.

Only disable when running without services (unit-only runs, CI without a
live platform, debugging unrelated failures):

- CI: `DISABLE_AUDIT_ASSERTIONS=1` (survives shell wrappers)
- Local dev: `uv run pytest --sdks go --no-audit-logs -v`

For wiring up the log-file env vars, prefer `eval $(uv run otdf-local env)`
(see Environment Management below). Fixture details and the
auto-discovery fallback under `../platform/logs/` live in
`xtest/AGENTS.md`.

## Environment Management

Use `otdf-local` for all environment management (starting/stopping services, viewing logs, restart procedures, troubleshooting). See `otdf-local/AGENTS.md` for details.

Quick start:
```bash
cd otdf-local && uv run otdf-local up
eval $(uv run otdf-local env)   # sets PLATFORM_LOG_FILE / KAS_*_LOG_FILE — required for the default audit-log assertions
```

## Key Concepts

### TDF Wrapping Algorithms

**RSA Wrapping (wrapped)**:
- KAO type: "wrapped"

**EC Wrapping (ec-wrapped)**:
- KAO type: "ec-wrapped"
- Requires: `ec_tdf_enabled: true` in platform config

**Ensuring Key Consistency**:
```bash
# km instances must use platform's root_key:
PLATFORM_ROOT_KEY=$(yq e '.services.kas.root_key' "$PLATFORM_DIR/opentdf-dev.yaml")
yq e -i ".services.kas.root_key = \"$PLATFORM_ROOT_KEY\"" "$CONFIG_FILE"
```

## Common Test Failures and Debugging

Recipes for known failures (EC wrapping disabled, unregistered KAS instances,
golden-TDF keys, missing `OT_ROOT_KEY`) live in
`.claude/skills/xtest-troubleshooting/SKILL.md`.

## Code Modification Best Practices

### When Modifying SDK Code

After changes to SDK source, rebuild with `cd xtest/sdk && make`.

### When Modifying Platform Code

Restart the platform service after making changes.

### Before Committing Python Changes

**REQUIRED**: Run lint, format, and type-check on any Python package you touched
(`xtest/`, `otdf-sdk-mgr/`, `otdf-local/`, etc.) before `git commit`. `cd` into
the package directory first so the tools see the project's venv:

```bash
cd otdf-sdk-mgr        # or xtest, otdf-local, etc.
uv run ruff check .    # lint — must pass
uv run ruff format .   # auto-format — re-stage any reformatted files
uv run pyright         # type-check — must pass
```

Use `uv run`, not `uvx`. `uvx` runs the tool in an isolated env that can't
see the project's dependencies, so `pyright` will produce dozens of spurious
`Import "foo" could not be resolved` errors. `uv run` uses the project venv
(after `uv sync` has installed the `dev` dependency group), which is what CI
does.

Run all three. Don't skip steps because "it's a small change" — CI runs them
and a failed check round-trips the PR. If `ruff format` rewrites a file you
already staged, `git add` it again before committing.

## Quick Reference

### Platform Inspection
```bash
curl localhost:8080/.well-known/opentdf-configuration | jq
curl localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'
curl localhost:8080/healthz
yq e '.services.kas.root_key' platform/opentdf-dev.yaml
```

## Closing Note

The test failures are usually symptoms of configuration mismatches, not SDK bugs. Focus on ensuring the local environment matches what the tests expect. See the per-package guides in `xtest/`, `otdf-sdk-mgr/`, and `otdf-local/` for sub-system specifics.
