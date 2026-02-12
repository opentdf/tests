# Agent Guide: Working with OpenTDF Tests and Debugging

This guide provides essential knowledge for AI agents performing updates, refactorings, and debugging of OpenTDF libraries and applications under test.

## Test Framework Overview

### Structure
- **Test Directory**: `xtest/` - pytest-based integration tests
- **SDK Distributions**: `sdk/{go,java,js}/dist/` - built SDK distributions with CLI wrappers
- **SDK Configuration**: `otdf-sdk-mgr install` - installs SDK CLIs from released artifacts or delegates to source builds
- **SDK Version Lookup**: `otdf-sdk-mgr versions list` - lists released artifacts across registries (Go git tags, npm, Maven Central, GitHub Releases)
- **Platform**: `platform/` - OpenTDF platform service
- **Test Runner**: pytest with custom CLI options

### Configuring SDK Artifacts

SDK CLIs can be installed from **released artifacts** (fast, deterministic) or built from **source** (for branch/PR testing). Both modes produce the same `sdk/{go,java,js}/dist/{version}/` directory structure.

**Primary tool**: `otdf-sdk-mgr` (uv-managed CLI in `tests/otdf-sdk-mgr/`)

```bash
cd tests/otdf-sdk-mgr && uv tool install --editable .

# Install latest stable releases for all SDKs (recommended for local testing)
otdf-sdk-mgr install stable

# Install LTS versions
otdf-sdk-mgr install lts

# Install specific released versions
otdf-sdk-mgr install release go:v0.24.0 js:0.4.0 java:v0.9.0

otdf-sdk-mgr install tip
otdf-sdk-mgr install tip go    # Single SDK

# Install a published version with optional dist name (defaults to version tag)
otdf-sdk-mgr install artifact --sdk go --version v0.24.0
otdf-sdk-mgr install artifact --sdk go --version v0.24.0 --dist-name my-tag

# List available versions
otdf-sdk-mgr versions list go --stable --latest 3 --table

# Resolve version tags to SHAs
otdf-sdk-mgr versions resolve go main latest

# Checkout SDK source
otdf-sdk-mgr checkout go main

# Clean dist and source directories
otdf-sdk-mgr clean

# Fix Java pom.xml after source checkout
otdf-sdk-mgr java-fixup
```

**How release installs work per SDK:**
- **Go**: Writes a `.version` file; `cli.sh`/`otdfctl.sh` use `go run github.com/opentdf/otdfctl@{version}` (no local compilation needed, Go caches the binary)
- **JS**: Runs `npm install @opentdf/ctl@{version}` into the dist directory; `cli.sh` uses `npx` from local `node_modules/`
- **Java**: Downloads `cmdline.jar` from GitHub Releases; `cli.sh` uses `java -jar cmdline.jar`

**Source builds** (`tip` mode) delegate to `checkout-sdk-branch.sh` + `make`, which checks out source to `sdk/{lang}/src/` and compiles to `sdk/{lang}/dist/`.

### Running Tests

```bash
# Configure environment for pytest (recommended)
cd tests/lmgmt
eval $(uv run lmgmt env)
cd ../xtest

# Run with specific SDK
uv run pytest --sdks go -v

# Run with multiple SDKs (space-separated)
uv run pytest --sdks "go java js" -v

# Run specific test file
uv run pytest test_tdfs.py --sdks go -v

# Run specific test
uv run pytest test_tdfs.py::test_tdf_roundtrip --sdks go -v
```

### Custom pytest Options
- `--sdks`: Specify which SDKs to test (go, java, js)
- `--containers`: Specify TDF container types (ztdf, ztdf-ecwrap)
- `--no-audit-logs`: Disable audit log assertions globally
- Environment variables:
  - `PLATFORMURL`: Platform endpoint (default: http://localhost:8080)
  - `OT_ROOT_KEY`: Root key for key management tests
  - `SCHEMA_FILE`: Path to manifest schema file
  - `DISABLE_AUDIT_ASSERTIONS`: Set to `1`, `true`, or `yes` to disable audit log assertions

### Audit Log Assertions

**IMPORTANT**: Audit log assertions are **REQUIRED by default**. Tests will fail during setup if KAS log files are not available.

**Why Required by Default:**
- Ensures comprehensive test coverage of audit logging functionality
- Catches regressions in audit event generation
- Validates clock skew handling between test machine and services

**Disabling Audit Assertions:**

Only disable when:
- Running tests without services (unit tests only)
- Debugging non-audit-related issues
- CI environments where audit logs aren't available

To disable, use either:
```bash
# Environment variable (preferred for CI)
DISABLE_AUDIT_ASSERTIONS=1 uv run pytest --sdks go -v

# CLI flag (preferred for local dev)
uv run pytest --sdks go --no-audit-logs -v
```

**Setting Up Log Files:**

Audit log collection requires KAS log files. Set paths via environment variables:
```bash
export PLATFORM_LOG_FILE=/path/to/platform.log
export KAS_ALPHA_LOG_FILE=/path/to/kas-alpha.log
export KAS_BETA_LOG_FILE=/path/to/kas-beta.log
# ... etc for kas-gamma, kas-delta, kas-km1, kas-km2
```

Or ensure services are running with logs in `../../platform/logs/` (auto-discovered).

## Environment Management

Use `lmgmt` for all environment management (starting/stopping services, viewing logs, restart procedures, troubleshooting). See:
- `lmgmt/README.md` - command reference and installation
- `lmgmt/CLAUDE.md` - operational procedures (restarts, tmux navigation, golden key config, troubleshooting)

Quick start: `cd tests/lmgmt && uv run lmgmt up`

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

**Base Key Behavior**:
- When platform advertises a `base_key` in `.well-known/opentdf-configuration`

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
cd tests/lmgmt && uv run lmgmt restart platform
```

### ABAC Test Failures: Decrypt Errors

**Symptom**: ABAC autoconfigure tests fail during decrypt

**Root Cause**: KAS instances (alpha, beta, etc.) not registered in platform's KAS registry

**Debug**:
```bash
curl http://localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'
# Expected: alpha=8181, beta=8282, gamma=8383, delta=8484
```

**Fix**: Ensure all KAS instances are properly registered during startup (`lmgmt up` handles this).

### Legacy/Golden TDF Test Failures

**Symptom**: "cipher: message authentication failed"

**Root Cause**: Golden TDFs require specific keys loaded by the platform. `lmgmt up` auto-configures these. See `lmgmt/CLAUDE.md` for manual configuration details.

```bash
cd tests/lmgmt
uv run lmgmt up  # or restart platform
eval $(uv run lmgmt env)
cd ../xtest
uv run pytest test_legacy.py --sdks go -v --no-audit-logs
```

### Missing Environment Variables

**Symptom**: "OT_ROOT_KEY environment variable is not set"

**Fix**:
```bash
export OT_ROOT_KEY=$(yq e '.services.kas.root_key' platform/opentdf-dev.yaml)
export SCHEMA_FILE=/path/to/schema.json
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
4. **Check service logs**: `cd tests/lmgmt && uv run lmgmt logs --grep "error" -f`
5. **Manual reproduction**:
   ```bash
   sdk/go/dist/main/cli.sh encrypt test.txt test.tdf --attr https://example.com/attr/foo/value/bar
   sdk/go/dist/main/cli.sh decrypt test.tdf test.out.txt
   ```
6. **Fix and verify**: Make changes, restart services if needed (`lmgmt restart <service>`), re-run failing test, then run full suite

## Code Modification Best Practices

### Before Making Changes

1. **Always read files first** - use Read tool before Edit/Write
2. **Understand existing patterns** - check similar code in the codebase
3. **Check test coverage** - modifications may affect multiple tests
4. **Review related config** - platform config, KAS config, SDK config

### When Modifying SDK Code

```bash
# After changes to SDK source, rebuild from source
cd tests/otdf-sdk-mgr
uv run otdf-sdk-mgr install tip go   # or java, js

# Or manually: checkout + make
cd sdk/go  # or sdk/java, sdk/js
make

# Verify build worked
ls -la dist/main/cli.sh
```

For testing against a released SDK version (no source changes needed):
```bash
cd tests/otdf-sdk-mgr && uv run otdf-sdk-mgr install release go:v0.24.0
```

### When Modifying Platform Code

```bash
cd tests/lmgmt && uv run lmgmt restart platform
```

### When Modifying Test Code

- **Test fixtures**: Changes affect all tests using that fixture
- **Helper functions**: Used across multiple test files
- **Conftest.py**: Session-scoped fixtures, careful with modifications

## Test File Organization

### Key Test Files

- `test_tdfs.py` - Core TDF roundtrip, manifest validation, tampering tests
- `test_abac.py` - ABAC policy, autoconfigure, key management tests
- `test_legacy.py` - Backward compatibility with golden TDFs (requires golden-r1 key, auto-configured by lmgmt)
- `test_policytypes.py` - Policy type tests (OR, AND, hierarchy)
- `test_self.py` - Platform API tests (namespaces, attributes, SCS)

### Important Helper Files

- `tdfs.py` - SDK abstraction layer, core test utilities
- `fixtures/` - pytest fixtures (attributes, keys, SDKs, etc.)
- `conftest.py` - pytest configuration and shared fixtures

## Common Pitfalls

1. **Forgetting to rebuild SDK** after code changes
2. **Modifying wrong config file** (opentdf.yaml vs opentdf-dev.yaml)
3. **Not restarting services** after config changes
4. **Root key mismatches** between platform and KAS instances
5. **Port conflicts** from old processes still running
6. **Assuming SDK behavior** without checking platform configuration

## Quick Reference

### Platform Inspection
```bash
curl localhost:8080/.well-known/opentdf-configuration | jq
curl localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'
curl localhost:8080/healthz
yq e '.services.kas.root_key' platform/opentdf-dev.yaml
```

### SDK Configuration
```bash
cd tests/otdf-sdk-mgr

otdf-sdk-mgr install stable                              # Latest stable for all SDKs
otdf-sdk-mgr install lts                                 # LTS versions
otdf-sdk-mgr install release go:v0.24.0 js:0.4.0        # Specific versions
otdf-sdk-mgr install tip                                 # All SDKs from main
otdf-sdk-mgr install tip go                              # Single SDK from main
otdf-sdk-mgr versions list go --stable --latest 3 --table
otdf-sdk-mgr versions resolve go main latest
otdf-sdk-mgr checkout go main
otdf-sdk-mgr clean
```

### Manual SDK Operations
```bash
sdk/go/dist/main/cli.sh encrypt input.txt output.tdf --attr <fqn>
sdk/go/dist/main/cli.sh decrypt output.tdf decrypted.txt
```

## Summary

### Preferred Workflow

1. **Configure SDK artifacts**: `cd tests/otdf-sdk-mgr && otdf-sdk-mgr install stable`
2. **Start environment**: `cd tests/lmgmt && uv run lmgmt up`
3. **Configure shell**: `eval $(uv run lmgmt env)`
4. **Run tests**: `cd ../xtest && uv run pytest --sdks go -v`
5. **Restart after config changes**: `cd ../lmgmt && uv run lmgmt restart <service>`

### When Debugging Test Failures

1. Read error messages carefully - they guide you to the root cause
2. Check platform configuration matches expected test behavior
3. Verify all KAS instances have consistent keys
4. Ensure services are running and healthy (`lmgmt status`)
5. Check service logs (`lmgmt logs <service> -f`)
6. Reproduce issues manually when possible
7. Always restart services after config changes
8. Read before writing - understand existing code patterns

The test failures are usually symptoms of configuration mismatches, not SDK bugs. Focus on ensuring the local environment matches what the tests expect.
