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

## Controller Script Library

**NEW**: The test environment uses a modular, well-tested shell script library for all service management.

**Key locations:**
- `scripts/` - Main controller scripts (local-test.sh, cleanup.sh, etc.)
- `scripts/lib/` - Modular library with 55 unit tests
- `scripts/lib/README.md` - Full API reference and documentation
- `scripts/lib/QUICK_REFERENCE.md` - Quick command lookup

**Important for agents:**
- All library code is tested with BATS (55 passing tests)
- Library files never set shell options (no `set -e`)
- Functions have explicit error checking and return codes
- Works in both bash and zsh
- Comprehensive documentation available in `scripts/lib/README.md`

**When modifying scripts:**
1. Read `scripts/lib/README.md` first for API reference
2. Follow existing patterns (check return codes explicitly)
3. Use logging functions (`log_info`, `log_error`) not echo
4. Test changes with `bats scripts/lib/**/*.bats`

## Local Test Environment

The local test environment uses a modular tmux-based controller system for managing all services.

### Quick Start

```bash
# Start all services
./scripts/local-test.sh start

# View service status
./scripts/local-test.sh status

# Attach to tmux session to view logs
./scripts/local-test.sh attach

# Stop all services and cleanup
./scripts/local-test.sh stop
```

### Tmux Session Layout

Session name: `xtest`

Window layout:
- **0: control** - Status and commands
- **1: platform** - Main OpenTDF platform (port 8080)
- **2: kas-alpha** - KAS instance (port 8181)
- **3: kas-beta** - KAS instance (port 8282)
- **4: kas-gamma** - KAS instance (port 8383)
- **5: kas-delta** - KAS instance (port 8484)
- **6: kas-km1** - Key management KAS (port 8585)
- **7: kas-km2** - Key management KAS (port 8686)
- **8: docker** - Docker logs (keycloak, postgres)
- **9: tests** - Test execution window

### Available Commands

**Main Controller** (`scripts/local-test.sh`):
```bash
./scripts/local-test.sh start    # Start all services (docker, platform, KAS instances)
./scripts/local-test.sh stop     # Stop everything and clean up
./scripts/local-test.sh status   # Show service health status
./scripts/local-test.sh attach   # Attach to tmux session
./scripts/local-test.sh logs     # View combined logs
./scripts/local-test.sh help     # Show help message
```

**Individual Service Scripts**:
```bash
# Start Docker services (keycloak, postgres)
./scripts/services/docker-up.sh start
./scripts/services/docker-up.sh stop

# Start main platform
./scripts/services/platform-start.sh [config-file]

# Start individual KAS instance
./scripts/services/kas-start.sh <name> <port> [--key-management]
# Examples:
./scripts/services/kas-start.sh alpha 8181
./scripts/services/kas-start.sh km1 8585 --key-management

# Provision Keycloak and fixtures
./scripts/services/provision.sh [all|keycloak|fixtures]

# Initialize cryptographic keys
./scripts/setup/init-keys.sh [--force]

# Trust certificates (macOS only)
./scripts/setup/trust-cert.sh [add|remove|status]

# Cleanup environment
./scripts/cleanup.sh [--keep-logs]
```

### Viewing Service Logs

**Via tmux session:**
```bash
# Attach to session
tmux attach -t xtest

# Navigate between windows
Ctrl-B then number (0-9)  # Switch to window by number
Ctrl-B w                   # Show window list
Ctrl-B n                   # Next window
Ctrl-B p                   # Previous window

# Scroll through logs
Ctrl-B [                   # Enter scroll mode
q                          # Exit scroll mode

# Detach from session
Ctrl-B d
```

**Via log files:**
```bash
# All services log to xtest/logs/
tail -f xtest/logs/platform.log
tail -f xtest/logs/kas-alpha.log
tail -f xtest/logs/kas-km1.log
```

### Script Library Structure

All controller scripts use a modular library located in `scripts/lib/`:

**Core Modules:**
- `core/logging.sh` - Enhanced logging with levels (quiet/error/warning/info/debug/trace)
- `core/platform.sh` - Platform detection (macOS/Linux/WSL)
- `core/paths.sh` - Path resolution utilities

**Health Modules:**
- `health/checks.sh` - Prerequisites and health checks
- `health/waits.sh` - Port waiting and availability

**Service Modules:**
- `services/tmux.sh` - Tmux session management
- `services/kas-utils.sh` - KAS configuration utilities
- `config/yaml.sh` - YAML manipulation with yq

**Task-Specific Bundles:**
- `bundles/service-manager.sh` - For service start/stop scripts
- `bundles/test-runner.sh` - For test execution scripts
- `bundles/dev-setup.sh` - For setup scripts

**Documentation:**
- `lib/README.md` - Full API reference
- `lib/QUICK_REFERENCE.md` - Quick lookup guide

### Environment Variables

Control logging verbosity:
```bash
# Set log level for scripts
export XTEST_LOGLEVEL=debug    # Show debug messages
export XTEST_LOGLEVEL=trace    # Show all messages including traces
export XTEST_LOGLEVEL=quiet    # Suppress all output

# Default is 'info' (shows info, warnings, and errors)
```

Service ports (auto-configured by scripts):
```bash
KEYCLOAK_PORT=8888
POSTGRES_PORT=5432
PLATFORM_PORT=8080
# KAS ports: alpha=8181, beta=8282, gamma=8383, delta=8484, km1=8585, km2=8686
```

### Understanding the Script Library

The controller scripts use a modular bash/zsh library that follows these principles:

**Key Design Rules:**
1. **No shell options in libraries** - Library files never set `set -e` or `set -o pipefail`
2. **Consumer scripts control error handling** - Each script decides its own error behavior
3. **Explicit error checking** - All functions return meaningful exit codes
4. **Cross-shell compatible** - Works in both bash and zsh

**When modifying scripts:**
- Always source bundles, not individual modules (unless you have specific needs)
- Use `log_info`, `log_warn`, `log_error` instead of echo for output
- Check command availability with `check_command` before using
- Use `wait_for_health` and `wait_for_port` for service readiness
- All paths available via `get_*_dir()` functions

**Example script pattern:**
```bash
#!/usr/bin/env bash
set -euo pipefail  # Consumer controls error handling

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/bundles/service-manager.sh"

# Now you have access to:
# - Logging: log_info, log_warn, log_error, log_success
# - Health: check_prerequisites, wait_for_health, wait_for_port
# - Paths: XTEST_DIR, PLATFORM_DIR, LOGS_DIR
# - Config: KAS_CONFIG array, service ports
# - KAS utils: get_kas_config_path, is_km_kas, generate_root_key
# - YAML: yq_set, yq_get, update_yaml_port

log_info "Starting service..."
check_prerequisites || exit 1
# ... rest of script
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

### When Modifying Controller Scripts

**Before modifying scripts in `scripts/` or `scripts/lib/`:**

1. **Read the library documentation first**:
   ```bash
   cat scripts/lib/README.md          # Full API reference
   cat scripts/lib/QUICK_REFERENCE.md # Quick lookup
   ```

2. **Understand the bundle system**:
   - Service scripts use `bundles/service-manager.sh`
   - Test scripts use `bundles/test-runner.sh`
   - Setup scripts use `bundles/dev-setup.sh`

3. **Follow the design rules**:
   - Never add `set -e` or `set -o pipefail` to library files
   - Always return explicit exit codes from functions
   - Use logging functions instead of echo
   - Check function return codes explicitly

4. **Test your changes**:
   ```bash
   # Syntax check
   bash -n scripts/services/your-script.sh

   # Run library tests
   cd scripts/lib
   bats core/*.bats health/*.bats services/*.bats config/*.bats

   # Test the full workflow
   ./scripts/local-test.sh stop
   ./scripts/local-test.sh start
   ```

5. **Common patterns to use**:
   ```bash
   # Check prerequisites
   check_prerequisites || exit 1

   # Wait for service
   wait_for_health "$PLATFORM_HEALTH" "Platform" 60
   wait_for_port 8080 "Platform" 30

   # Ensure directories exist
   ensure_logs_dir

   # YAML manipulation
   yq_set "$config_file" ".server.port" "8080"

   # KAS utilities
   config_path="$(get_kas_config_path "alpha")"
   is_km_kas "km1" && log_info "Key management enabled"
   ```

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

### Full Environment Restart (Recommended)
```bash
# Stop everything cleanly
./scripts/local-test.sh stop

# Wait a moment for cleanup
sleep 2

# Start everything fresh
./scripts/local-test.sh start
```

### Full Environment Restart (Manual)
```bash
# Kill all services
pkill -9 -f "go.*service.*start"
pkill -9 -f "opentdf-kas"
./scripts/services/docker-up.sh stop

# Kill tmux session
tmux kill-session -t xtest

# Wait for ports to free
sleep 5

# Restart everything
./scripts/local-test.sh start
```

### Platform Only Restart
```bash
# Via tmux session
tmux attach -t xtest
# Navigate to window 1 (platform)
Ctrl-B 1
# Stop: Ctrl-C
# Restart: Up arrow + Enter

# Or manually
pkill -9 -f "go.*service.*start"
./scripts/services/platform-start.sh
```

### Individual KAS Restart
```bash
# Via tmux session
tmux attach -t xtest

# Navigate to KAS window:
# Ctrl-B 2  (kas-alpha)
# Ctrl-B 3  (kas-beta)
# Ctrl-B 4  (kas-gamma)
# Ctrl-B 5  (kas-delta)
# Ctrl-B 6  (kas-km1)
# Ctrl-B 7  (kas-km2)

# Stop: Ctrl-C
# Restart: Up arrow + Enter

# Or manually restart a specific instance
./scripts/services/kas-start.sh alpha 8181
./scripts/services/kas-start.sh km1 8585 --key-management
```

### Docker Services Restart
```bash
# Stop and start
./scripts/services/docker-up.sh stop
./scripts/services/docker-up.sh start

# Or via tmux window 8 (docker logs)
tmux attach -t xtest
Ctrl-B 8  # Navigate to docker window
```

### Cleanup Without Stopping
```bash
# Remove logs and configs but keep services running
./scripts/cleanup.sh --keep-logs   # Keeps logs
rm -rf xtest/logs/*.yaml           # Remove only configs
```

## Common Pitfalls

1. **Forgetting to rebuild SDK** after code changes
2. **Modifying wrong config file** (opentdf.yaml vs opentdf-dev.yaml)
3. **Not restarting services** after config changes
4. **Root key mismatches** between platform and KAS instances
5. **Port conflicts** from old processes still running
6. **Assuming SDK behavior** without checking platform configuration

## Quick Reference Commands

### Service Management
```bash
# Start/stop environment
./scripts/local-test.sh start
./scripts/local-test.sh stop
./scripts/local-test.sh status

# View logs via tmux
./scripts/local-test.sh attach

# Individual services
./scripts/services/docker-up.sh start
./scripts/services/platform-start.sh
./scripts/services/kas-start.sh alpha 8181
./scripts/services/provision.sh

# Cleanup
./scripts/cleanup.sh
./scripts/cleanup.sh --keep-logs
```

### Testing
```bash
# Run all tests with Go SDK
uv run pytest --sdks go -v

# Run specific test file
uv run pytest test_tdfs.py --sdks go -v

# Run with debug output from scripts
export XTEST_LOGLEVEL=debug
./scripts/local-test.sh start
```

### Platform Inspection
```bash
# Check platform config
curl localhost:8080/.well-known/opentdf-configuration | jq

# View KAS registry
curl localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'

# Check platform health
curl localhost:8080/healthz

# Get platform root key
yq e '.services.kas.root_key' platform/opentdf-dev.yaml
```

### Tmux Navigation
```bash
# Attach to session
tmux attach -t xtest

# Navigate windows
Ctrl-B 0-9     # Switch to window by number
Ctrl-B w       # Show window list
Ctrl-B d       # Detach

# View logs in session
Ctrl-B [       # Enter scroll mode
q              # Exit scroll mode
```

### Troubleshooting
```bash
# Kill stuck processes
pkill -9 -f "go.*service.*start"
./scripts/services/docker-up.sh stop

# View service logs
tail -f xtest/logs/platform.log
tail -f xtest/logs/kas-alpha.log

# Check port availability
lsof -i :8080   # Platform
lsof -i :8181   # KAS alpha
lsof -i :8888   # Keycloak
```

### Manual SDK Operations
```bash
# Encrypt/decrypt
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
