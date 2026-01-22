# Agent Guide: Working with OpenTDF Tests and Debugging

This guide provides essential knowledge for AI agents (particularly Haiku LLM) performing updates, refactorings, and debugging of OpenTDF libraries and applications under test.

## Test Framework Overview

### Structure
- **Test Directory**: `tests/xtest/` - pytest-based integration tests
- **SDK Distributions**: `sdk/{go,java,js}/dist/` - built SDK distributions with CLI wrappers
- **Platform**: `platform/` - OpenTDF platform service
- **Test Runner**: pytest with custom CLI options

### Running Tests

```bash
# Run with specific SDK
uv run pytest --sdks go -v

# Run with multiple SDKs
uv run pytest --sdks go,java,js -v

# Run specific test file
uv run pytest test_tdfs.py --sdks go -v

# Run specific test
uv run pytest test_tdfs.py::test_tdf_roundtrip --sdks go -v
```

### Custom pytest Options
- `--sdks`: Specify which SDKs to test (go, java, js)
- `--containers`: Specify TDF container types (ztdf, ztdf-ecwrap)
- Environment variables:
  - `PLATFORMURL`: Platform endpoint (default: http://localhost:8080)
  - `OT_ROOT_KEY`: Root key for key management tests
  - `SCHEMA_FILE`: Path to manifest schema file

## Local Test Environment

### Starting the Environment

```bash
# Start all services via tmux
./local-test.sh

# This creates tmux session 'local-test' with windows:
# - platform: Main OpenTDF platform (port 8080)
# - alpha: KAS instance (port 8181)
# - beta: KAS instance (port 8282)
# - gamma: KAS instance (port 8383)
# - delta: KAS instance (port 8484)
# - km1: Key management KAS (port 8585)
# - km2: Key management KAS (port 8686)
```

### Viewing Service Logs

```bash
# Attach to tmux session
tmux attach -t local-test

# Navigate windows
# Ctrl-B then number (0-6)
# Or: Ctrl-B w (shows window list)

# Detach from tmux
# Ctrl-B d
```

### Platform Configuration Files

**CRITICAL**: The platform may load different config files depending on how it's started:
- `platform/opentdf.yaml` - Primary config file
- `platform/opentdf-dev.yaml` - Development config (used by local-test.sh)

**Always check which file is actually being used** when debugging configuration issues.

Key configuration sections:
```yaml
services:
  kas:
    root_key: "a8c4824daafcfa38ed0d13002e92b08720e6c4fcee67d52e954c1a6e045907d1"
    preview:
      ec_tdf_enabled: true  # Required for EC wrapping tests
      key_management: true  # For key management KAS instances

configuration:
  base_key:
    public_key: "..." # If set, SDK automatically uses EC wrapping
    kid: "e1"
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

**Base Key Behavior**:
- When platform advertises a `base_key` in `.well-known/opentdf-configuration`
- SDK **automatically** uses EC wrapping, regardless of user's choice
- Tests must check `pfs.has_base_key` to determine expected KAO type

### Key Management and Root Keys

**Critical Rule**: All KAS instances that participate in EC wrapping must share the same root key.

Why:
1. EC wrapping derives keys from root_key + base_key
2. If KAS instances have different root_keys, they derive different keys
3. Encryption with one key, decryption with another = "cipher: message authentication failed"

**Ensuring Key Consistency**:
```bash
# In scripts/services/kas-start.sh
# km instances must use platform's root_key:
PLATFORM_ROOT_KEY=$(yq e '.services.kas.root_key' "$PLATFORM_DIR/opentdf-dev.yaml")
yq e -i ".services.kas.root_key = \"$PLATFORM_ROOT_KEY\"" "$CONFIG_FILE"
```

## Common Test Failures and Debugging

### 1. 'ec-wrapped' vs 'wrapped' Assertion Errors

**Symptom**: Test expects "wrapped" but gets "ec-wrapped" (or vice versa)

**Root Cause**: Platform has `base_key` configured, forcing SDK to use EC wrapping

**Debug**:
```bash
# Check platform configuration
curl http://localhost:8080/.well-known/opentdf-configuration | jq '.configuration.base_key'
```

**Fix**: Update test code to check for base_key:
```python
pfs = tdfs.PlatformFeatureSet()
expect_ec_wrapped = use_ecwrap or pfs.has_base_key
if expect_ec_wrapped:
    assert kao.type == "ec-wrapped"
else:
    assert kao.type == "wrapped"
```

### 2. Decrypt Failures: "cipher: message authentication failed"

**Symptom**: Encryption succeeds, but decrypt fails with GCM authentication error

**Root Cause**: Key mismatch - KAS instances have different root_keys

**Debug**:
```bash
# Check KAS logs for which key was used
tmux attach -t local-test
# Navigate to km1 window, look for root_key in startup logs

# Check platform root_key
yq e '.services.kas.root_key' platform/opentdf-dev.yaml
```

**Fix**: Ensure all KAS instances use the same root_key (see scripts/services/kas-start.sh)

### 3. "ec rewrap not enabled" Errors

**Symptom**: EC rewrap tests fail with "not enabled" message

**Root Cause**: `ec_tdf_enabled: false` in platform config

**Debug**:
```bash
# Check both config files
yq e '.services.kas.preview.ec_tdf_enabled' platform/opentdf.yaml
yq e '.services.kas.preview.ec_tdf_enabled' platform/opentdf-dev.yaml
```

**Fix**:
```bash
# Update config
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf.yaml
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf-dev.yaml

# Restart platform
pkill -9 -f "go.*service.*start"
./local-test.sh
```

### 4. ABAC Test Failures: Decrypt Errors

**Symptom**: ABAC autoconfigure tests fail during decrypt

**Root Cause**: KAS instances (alpha, beta, etc.) not registered in platform's KAS registry

**Debug**:
```bash
# Check registered KAS instances
curl http://localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'

# Expected to see:
# - http://localhost:8181/kas (alpha)
# - http://localhost:8282/kas (beta)
# - http://localhost:8383/kas (gamma)
# - http://localhost:8484/kas (delta)
```

**Fix**: Ensure local-test.sh properly registers all KAS instances during startup

### 5. Legacy Test Failures: "cipher: message authentication failed"

**Symptom**: Legacy golden TDF decrypt tests fail

**Root Cause**: Golden TDFs were created with different keys than current environment

**Solution**: These tests require the exact keys used when creating the golden TDFs. Not a bug, just needs proper key configuration.

### 6. Missing Environment Variables

**Symptom**: Tests error with "OT_ROOT_KEY environment variable is not set"

**Fix**:
```bash
# Set required environment variables
export OT_ROOT_KEY=$(yq e '.services.kas.root_key' platform/opentdf-dev.yaml)
export SCHEMA_FILE=/path/to/schema.json
```

## Debugging Workflow

### Step 1: Run Tests and Capture Output
```bash
uv run pytest --sdks go -v 2>&1 | tee test_output.log
```

### Step 2: Analyze Failures
- Read error messages carefully - they usually point to root cause
- Check which test category is failing (ABAC, legacy, TDF roundtrip, etc.)
- Look for patterns across multiple failures

### Step 3: Inspect Platform State
```bash
# Check platform configuration
curl http://localhost:8080/.well-known/opentdf-configuration | jq

# Check registered KAS instances
curl http://localhost:8080/api/kas/v2/kas/key-access-servers | jq

# Verify platform is healthy
curl http://localhost:8080/healthz
```

### Step 4: Check Service Logs
```bash
# Attach to tmux and navigate to relevant window
tmux attach -t local-test

# For decrypt failures, check KAS logs
# Navigate to the KAS window mentioned in the error
```

### Step 5: Manual Reproduction
```bash
# Try to reproduce with CLI directly
sdk/go/dist/main/cli.sh encrypt test.txt test.tdf --attr https://example.com/attr/foo/value/bar

sdk/go/dist/main/cli.sh decrypt test.tdf test.out.txt
```

### Step 6: Fix and Verify
- Make necessary changes to code or config
- Restart services if config changed
- Re-run the specific failing test
- If passes, run full suite

## Code Modification Best Practices

### Before Making Changes

1. **Always read files first** - use Read tool before Edit/Write
2. **Understand existing patterns** - check similar code in the codebase
3. **Check test coverage** - modifications may affect multiple tests
4. **Review related config** - platform config, KAS config, SDK config

### When Modifying SDK Code

```bash
# After changes, rebuild SDK distribution
cd sdk/go  # or sdk/java, sdk/js
./build.sh  # or appropriate build command

# Verify build worked
ls -la dist/main/cli.sh
```

### When Modifying Platform Code

```bash
# Restart platform after changes
pkill -9 -f "go.*service.*start"

# Wait a moment for port to free
sleep 2

# Restart via local-test.sh or manually
cd platform
go run ./service start
```

### When Modifying Test Code

- **Test fixtures**: Changes affect all tests using that fixture
- **Helper functions**: Used across multiple test files
- **Conftest.py**: Session-scoped fixtures, careful with modifications

## Test File Organization

### Key Test Files

- `test_tdfs.py` - Core TDF roundtrip, manifest validation, tampering tests
- `test_abac.py` - ABAC policy, autoconfigure, key management tests
- `test_legacy.py` - Backward compatibility with golden TDFs
- `test_policytypes.py` - Policy type tests (OR, AND, hierarchy)
- `test_self.py` - Platform API tests (namespaces, attributes, SCS)

### Important Helper Files

- `tdfs.py` - SDK abstraction layer, core test utilities
- `fixtures/` - pytest fixtures (attributes, keys, SDKs, etc.)
- `conftest.py` - pytest configuration and shared fixtures

## Restart Procedures

### Full Environment Restart
```bash
# Kill all services
pkill -9 -f "go.*service.*start"
pkill -9 -f "opentdf-kas"

# Kill tmux session
tmux kill-session -t local-test

# Wait for ports to free
sleep 5

# Restart everything
./local-test.sh
```

### Platform Only Restart
```bash
# Kill platform
pkill -9 -f "go.*service.*start"

# Restart (in platform window or manually)
cd platform
go run ./service start
```

### Individual KAS Restart
```bash
# Attach to tmux
tmux attach -t local-test

# Navigate to KAS window (e.g., Ctrl-B 1 for alpha)
# Ctrl-C to stop
# Up arrow + Enter to restart last command
```

## Common Pitfalls

1. **Forgetting to rebuild SDK** after code changes
2. **Modifying wrong config file** (opentdf.yaml vs opentdf-dev.yaml)
3. **Not restarting services** after config changes
4. **Root key mismatches** between platform and KAS instances
5. **Port conflicts** from old processes still running
6. **Assuming SDK behavior** without checking platform configuration

## Quick Reference Commands

```bash
# Run all tests with Go SDK
uv run pytest --sdks go -v

# Check platform config
curl localhost:8080/.well-known/opentdf-configuration | jq

# View KAS registry
curl localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'

# Check platform health
curl localhost:8080/healthz

# View service logs
tmux attach -t local-test

# Kill stuck processes
pkill -9 -f "go.*service.*start"

# Get platform root key
yq e '.services.kas.root_key' platform/opentdf-dev.yaml

# Manual encrypt/decrypt
sdk/go/dist/main/cli.sh encrypt input.txt output.tdf --attr <fqn>
sdk/go/dist/main/cli.sh decrypt output.tdf decrypted.txt
```

## Summary

When debugging test failures:
1. Read error messages carefully - they guide you to the root cause
2. Check platform configuration matches expected test behavior
3. Verify all KAS instances have consistent keys
4. Ensure services are running and healthy
5. Reproduce issues manually when possible
6. Always restart services after config changes
7. Read before writing - understand existing code patterns

The test failures are usually symptoms of configuration mismatches, not SDK bugs. Focus on ensuring the local environment matches what the tests expect.
