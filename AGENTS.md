# Agent Guide: Working with OpenTDF Tests and Debugging

This guide provides essential knowledge for AI agents performing updates, refactorings, and debugging of OpenTDF libraries and applications under test.

## Repository Layout

| Path | Purpose | Has its own AGENTS.md? |
|------|---------|------------------------|
| `xtest/` | pytest integration tests (the main test suite) | yes |
| `otdf-sdk-mgr/` | Python CLI that installs SDK CLIs from releases or source (see `otdf-sdk-mgr/README.md`) | no |
| `otdf-local/` | Python CLI that runs/stops the platform + KAS instances locally | yes |
| `vulnerability/` | Playwright UI test suite (run with `npx playwright test`) | no |
| `xtest/sdk/{go,java,js}/dist/` | Built SDK CLI wrappers, produced by `otdf-sdk-mgr install` (or by `cd xtest/sdk && make` for source builds) | n/a |

## Test Framework Overview

### Test Runner
pytest with custom CLI options. Most work happens in `xtest/`.

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

# Run specific test file
uv run pytest test_tdfs.py --sdks go -v

# Run specific test
uv run pytest test_tdfs.py::test_tdf_roundtrip --sdks go -v
```

### Custom pytest Options and Env Vars

See `xtest/AGENTS.md` for the full table of `--sdks`, `--containers`,
`--no-audit-logs`, etc. Repo-wide environment variables:

- `PLATFORMURL` — platform endpoint (default `http://localhost:8080`)
- `OT_ROOT_KEY` — root key for key-management tests
- `SCHEMA_FILE` — path to manifest schema file
- `DISABLE_AUDIT_ASSERTIONS` — set to `1`/`true`/`yes` to skip audit-log assertions (CI equivalent of `--no-audit-logs`)

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
- Traditional approach
- Uses RSA public key to wrap symmetric key
- KAO type: "wrapped"

**EC Wrapping (ec-wrapped)**:
- Elliptic curve based wrapping
- Uses ephemeral key pair + key derivation
- KAO type: "ec-wrapped"
- Requires: `ec_tdf_enabled: true` in platform config

**Ensuring Key Consistency**:
```bash
# km instances must use platform's root_key:
PLATFORM_ROOT_KEY=$(yq e '.services.kas.root_key' "$PLATFORM_DIR/opentdf-dev.yaml")
yq e -i ".services.kas.root_key = \"$PLATFORM_ROOT_KEY\"" "$CONFIG_FILE"
```

## Common Test Failures and Debugging

### EC Wrapping Test Failures: "EC wrapping not supported"

**Fix**:
```bash
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf.yaml
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf-dev.yaml
# Restart the platform service
```

### ABAC Test Failures: Decrypt Errors

**Symptom**: ABAC autoconfigure tests fail during decrypt

**Root Cause**: KAS instances (alpha, beta, etc.) not registered in platform's KAS registry

**Debug**:
```bash
curl http://localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'
# Expected: alpha=8181, beta=8282, gamma=8383, delta=8484
```

**Fix**: Ensure all KAS instances are properly registered during startup.

### Legacy/Golden TDF Test Failures

**Symptom**: "cipher: message authentication failed"

**Root Cause**: Golden TDFs require specific keys loaded by the platform. Ensure the platform is configured with the correct golden keys.

```bash
cd xtest
uv run pytest test_legacy.py --sdks go -v --no-audit-logs
```

### Missing Environment Variables

**Symptom**: "OT_ROOT_KEY environment variable is not set"

**Fix**:
```bash
export OT_ROOT_KEY=$(yq e '.services.kas.root_key' platform/opentdf-dev.yaml)
export SCHEMA_FILE=manifest.schema.json
```

## Debugging Workflow

1. **Run tests**: `uv run pytest --sdks go -v 2>&1 | tee test_output.log`
2. **Analyze failures**: Read error messages, check which test category is failing, look for patterns
3. **Inspect platform state**:
   ```bash
   curl http://localhost:8080/.well-known/opentdf-configuration | jq
   curl http://localhost:8080/api/kas/v2/kas/key-access-servers | jq
   curl http://localhost:8080/healthz
   ```
4. **Check service logs**: Look at platform and KAS log files for errors
5. **Manual reproduction**:
   ```bash
   echo "hello tdf" > test.txt
   sdk/go/dist/main/cli.sh encrypt test.txt test.tdf --attr https://example.com/attr/foo/value/bar
   sdk/go/dist/main/cli.sh decrypt test.tdf test.out.txt
   ```
6. **Fix and verify**: Make changes, restart services if needed, re-run failing test, then run full suite

## Code Modification Best Practices

### When Modifying SDK Code

After changes to SDK source, rebuild with `cd xtest/sdk && make`.

### When Modifying Platform Code

Restart the platform service after making changes.

### When Modifying Test Code

- **Test fixtures**: Changes affect all tests using that fixture
- **Helper functions**: Used across multiple test files
- **Conftest.py**: Session-scoped fixtures, careful with modifications

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

## Test File Organization

For the canonical list of test modules, fixtures, and the SDK abstraction
layer, see `xtest/AGENTS.md`. The short version:

- Tests are grouped by concern, not by SDK (`test_tdfs.py`, `test_abac.py`,
  `test_legacy.py`, `test_audit_logs.py`, `test_pqc.py`, etc.).
- `xtest/tdfs.py` is the SDK abstraction layer — when a test passes for one
  SDK and fails for another, suspect the CLI shim or manifest emission, not
  the test.
- `xtest/conftest.py` defines the `--sdks` / `--containers` parametrization.
  Session-scoped fixtures live in `xtest/fixtures/`.

## Quick Reference

### Platform Inspection
```bash
curl localhost:8080/.well-known/opentdf-configuration | jq
curl localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'
curl localhost:8080/healthz
yq e '.services.kas.root_key' platform/opentdf-dev.yaml
```

## Closing Note

Test failures are usually configuration mismatches, not SDK bugs. Check
the local environment against what the tests expect before suspecting the
code. Per-subsystem details live in `xtest/AGENTS.md`,
`otdf-local/AGENTS.md`, and `otdf-sdk-mgr/README.md`.
