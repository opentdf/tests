# Agent Guide: Working with OpenTDF Tests and Debugging

This guide provides essential knowledge for AI agents performing updates, refactorings, and debugging of OpenTDF libraries and applications under test.

## Test Framework Overview

### Structure
- **Test Directory**: `xtest/` - pytest-based integration tests
- **SDK Distributions**: `xtest/sdk/{go,java,js}/dist/` - built SDK distributions with CLI wrappers
- **SDK Configuration**: `otdf-sdk-mgr install` - installs SDK CLIs from released artifacts or delegates to source builds
- **SDK Version Lookup**: `otdf-sdk-mgr versions list` - lists released artifacts across registries (Go git tags, npm, Maven Central, GitHub Releases)
- **Platform**: `platform/` - OpenTDF platform service
- **Test Runner**: pytest with custom CLI options

### Configuring SDK Artifacts

Use `otdf-sdk-mgr` (uv-managed CLI in `otdf-sdk-mgr/`) to install SDK CLIs from released artifacts or source. See `otdf-sdk-mgr/README.md` for full command reference.

```bash
cd otdf-sdk-mgr && uv tool install --editable .
otdf-sdk-mgr install stable    # Latest stable releases (recommended)
otdf-sdk-mgr install tip go    # Build from source
```

### Running Tests

```bash
# Generate local environment from otdf-local and configure
cd xtest && uv run ../otdf-local env > local.env && set -a && source local.env && set +a

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

Use `otdf-local` for all environment management (starting/stopping services, viewing logs, restart procedures, troubleshooting).

Quick start: `cd otdf-local && uv run otdf-local up`

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

### Before Making Changes

1. **Always read files first** - use Read tool before Edit/Write
2. **Understand existing patterns** - check similar code in the codebase
3. **Check test coverage** - modifications may affect multiple tests
4. **Review related config** - platform config, KAS config, SDK config

### When Modifying SDK Code

After changes to SDK source, rebuild with `cd xtest/sdk && make`.

### When Modifying Platform Code

Restart the platform service after making changes.

### When Modifying Test Code

- **Test fixtures**: Changes affect all tests using that fixture
- **Helper functions**: Used across multiple test files
- **Conftest.py**: Session-scoped fixtures, careful with modifications

## Test File Organization

### Key Test Files

- `test_tdfs.py` - Core TDF roundtrip, manifest validation, tampering tests
- `test_abac.py` - ABAC policy, autoconfigure, key management tests
- `test_legacy.py` - Backward compatibility with golden TDFs (requires golden-r1 key)
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

## Summary

### Preferred Workflow

1. **Build SDK CLIs**: `cd xtest/sdk && make`
2. **Configure environment**: `cd xtest && uv run ../otdf-local env > local.env && set -a && source local.env && set +a`
3. **Run tests**: `uv run pytest --sdks go -v`
4. **Restart after config changes**: Restart the affected platform/KAS services

### When Debugging Test Failures

1. Read error messages carefully - they guide you to the root cause
2. Check platform configuration matches expected test behavior
3. Verify all KAS instances have consistent keys
4. Ensure services are running and healthy
5. Check service logs for errors
6. Reproduce issues manually when possible
7. Always restart services after config changes
8. Read before writing - understand existing code patterns

The test failures are usually symptoms of configuration mismatches, not SDK bugs. Focus on ensuring the local environment matches what the tests expect.
