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
# Configure environment for pytest (recommended)
cd tests/lmgmt
eval $(uv run lmgmt env)
cd ../xtest

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

## Environment Management Tools

**RECOMMENDED**: Use `lmgmt` Python CLI for all environment management tasks.

### lmgmt - Python CLI

The `lmgmt` tool provides a type-safe interface for managing the test environment with error handling and health checks.

**Location**: `tests/lmgmt/`

**Quick Start**:
```bash
cd tests/lmgmt
uv sync  # First time only

# Start all services
uv run lmgmt up

# Check status
uv run lmgmt status

# View logs
uv run lmgmt logs -f

# Stop all services
uv run lmgmt down
```

**Key Features**:
- Rich terminal output with tables and progress indicators
- Comprehensive health checks and wait utilities
- Structured log aggregation with filtering
- JSON output for scripting
- Type-safe configuration with Pydantic

**Available Commands**:
- `lmgmt up` - Start environment with automatic health checks
- `lmgmt down` - Stop all services
- `lmgmt ls` - List services with status (table or JSON)
- `lmgmt status` - Show detailed health status (supports `--watch`)
- `lmgmt logs [service]` - View/tail/filter logs (`-f` to follow)
- `lmgmt restart <service>` - Restart specific service
- `lmgmt provision` - Run provisioning
- `lmgmt clean` - Clean generated files

See `tests/lmgmt/README.md` for full documentation.

## Local Test Environment

The local test environment can be managed using `lmgmt`

### Quick Start with lmgmt (Recommended)

```bash
cd tests/lmgmt

# Start all services
uv run lmgmt up

# View service status
uv run lmgmt status

# View logs
uv run lmgmt logs -f

# Stop all services and cleanup
uv run lmgmt down --clean
```


### Available Commands

Use `lmgmt` for all environment management:

```bash
cd tests/lmgmt

# Start/stop environment
uv run lmgmt up                    # Start all services
uv run lmgmt down                  # Stop all services
uv run lmgmt down --clean          # Stop and clean logs

# Check status
uv run lmgmt status                # Show health status
uv run lmgmt status --watch        # Live status updates
uv run lmgmt ls                    # List running services

# View logs
uv run lmgmt logs -f               # Follow all logs
uv run lmgmt logs platform -f      # Follow specific service
uv run lmgmt logs --grep error     # Filter logs

# Restart services
uv run lmgmt restart platform      # Restart specific service
uv run lmgmt restart kas-alpha

# Provisioning
uv run lmgmt provision             # Run all provisioning
uv run lmgmt provision keycloak    # Provision keycloak only

# Cleanup
uv run lmgmt clean                 # Clean logs and configs
uv run lmgmt clean --keep-logs     # Clean only configs

# Attach to tmux session (if using tmux)
tmux attach -t xtest
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

### Environment Variables

Service ports (auto-configured):
```bash
KEYCLOAK_PORT=8888
POSTGRES_PORT=5432
PLATFORM_PORT=8080
# KAS ports: alpha=8181, beta=8282, gamma=8383, delta=8484, km1=8585, km2=8686
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
# Update config
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf.yaml
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf-dev.yaml

# Restart platform using lmgmt (recommended)
cd tests/lmgmt
uv run lmgmt restart platform

# Or restart manually
pkill -9 -f "go.*service.*start"
sleep 2
cd platform && go run ./service start
```

### ABAC Test Failures: Decrypt Errors

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

**Fix**: Ensure all KAS instances are properly registered in the platform during startup (this is handled by `lmgmt up`)

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
# Using lmgmt (recommended)
cd tests/lmgmt
uv run lmgmt logs platform -f          # Follow platform logs
uv run lmgmt logs kas-alpha -f         # Follow KAS logs
uv run lmgmt logs --grep "error" -f    # Filter for errors

# Using tmux (if environment was started with scripts)
tmux attach -t local-test
# Navigate to the KAS window mentioned in the error

# Using log files directly
tail -f tests/xtest/logs/platform.log
tail -f tests/xtest/logs/kas-alpha.log
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
# Restart platform after changes using lmgmt (recommended)
cd tests/lmgmt
uv run lmgmt restart platform

# Or manually
pkill -9 -f "go.*service.*start"
sleep 2  # Wait a moment for port to free
cd platform
go run ./service start
```

### When Modifying Test Code

- **Test fixtures**: Changes affect all tests using that fixture
- **Helper functions**: Used across multiple test files
- **Conftest.py**: Session-scoped fixtures, careful with modifications

### When Modifying Controller Scripts

**DEPRECATED**: The shell scripts in `scripts/lib/` are being phased out. Use `lmgmt` for all environment management instead.

**For new automation**:
- Extend the `lmgmt` Python CLI tool instead of creating new shell scripts
- See `tests/lmgmt/README.md` for architecture and development guide
- The lmgmt codebase uses Python with Pydantic for type safety and better error handling

**For testing changes**:
```bash
# Test the full workflow with lmgmt
cd tests/lmgmt
uv run lmgmt down
uv run lmgmt up

# Check service status
uv run lmgmt status

# View logs
uv run lmgmt logs -f
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

### Full Environment Restart with lmgmt (Recommended)
```bash
cd tests/lmgmt

# Stop and restart everything
uv run lmgmt down
uv run lmgmt up

# Or with cleanup
uv run lmgmt down --clean
uv run lmgmt up
```

### Service-Specific Restart with lmgmt
```bash
cd tests/lmgmt

# Restart platform
uv run lmgmt restart platform

# Restart specific KAS instance
uv run lmgmt restart kas-alpha
uv run lmgmt restart kas-km1

# Restart Docker services
uv run lmgmt restart docker
```

### Manual Restart (Emergency)
```bash
# Kill all services
pkill -9 -f "go.*service.*start"
pkill -9 -f "opentdf-kas"

# Kill tmux session if it exists
tmux kill-session -t xtest 2>/dev/null || true

# Kill docker containers
cd platform && docker compose down 2>/dev/null || true

# Wait for ports to free
sleep 5

# Restart everything
cd tests/lmgmt && uv run lmgmt up
```

### Platform Only Restart
```bash
# Using lmgmt (recommended)
cd tests/lmgmt && uv run lmgmt restart platform

# Via tmux session (if using scripts)
tmux attach -t xtest
# Navigate to window 1 (platform)
Ctrl-B 1
# Stop: Ctrl-C
# Restart: Up arrow + Enter

# Or manually
pkill -9 -f "go.*service.*start"
sleep 2  # Wait a moment for port to free
cd platform
go run ./service start
```

### Individual KAS Restart
```bash
# Using lmgmt (recommended)
cd tests/lmgmt
uv run lmgmt restart kas-alpha
uv run lmgmt restart kas-km1

# Via tmux session (if using scripts)
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
```

### Docker Services Restart
```bash
# Using lmgmt (recommended)
cd tests/lmgmt && uv run lmgmt restart docker

# Or via tmux window 8 (docker logs)
tmux attach -t xtest
Ctrl-B 8  # Navigate to docker window
```

### Cleanup
```bash
cd tests/lmgmt
uv run lmgmt clean              # Clean logs and configs
uv run lmgmt clean --keep-logs  # Clean only configs
```

## Common Pitfalls

1. **Forgetting to rebuild SDK** after code changes
2. **Modifying wrong config file** (opentdf.yaml vs opentdf-dev.yaml)
3. **Not restarting services** after config changes
4. **Root key mismatches** between platform and KAS instances
5. **Port conflicts** from old processes still running
6. **Assuming SDK behavior** without checking platform configuration

## Quick Reference Commands

### Service Management with lmgmt (Recommended)
```bash
cd tests/lmgmt

# Start/stop environment
uv run lmgmt up
uv run lmgmt down
uv run lmgmt down --clean

# Configure environment for pytest
eval $(uv run lmgmt env)         # Sets PLATFORM_LOG_FILE, KAS_*_LOG_FILE, etc.
uv run lmgmt env --format json   # Output as JSON

# View status
uv run lmgmt status
uv run lmgmt status --watch  # Live updates
uv run lmgmt ls              # List running services
uv run lmgmt ls --all        # List all services

# View logs
uv run lmgmt logs -f                    # Follow all logs
uv run lmgmt logs platform              # Platform logs
uv run lmgmt logs kas-alpha -f          # Follow KAS logs
uv run lmgmt logs --grep error          # Filter logs

# Restart services
uv run lmgmt restart platform
uv run lmgmt restart kas-alpha
uv run lmgmt restart docker

# Provisioning
uv run lmgmt provision          # All
uv run lmgmt provision keycloak
uv run lmgmt provision fixtures

# Cleanup
uv run lmgmt clean
uv run lmgmt clean --keep-logs
```

### Testing
```bash
# Configure environment (from tests/lmgmt directory)
cd tests/lmgmt
eval $(uv run lmgmt env)
cd ../xtest

# Run all tests with Go SDK
uv run pytest --sdks go -v

# Run specific test file
uv run pytest test_tdfs.py --sdks go -v
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
# Check service status
cd tests/lmgmt
uv run lmgmt status         # See what's running
uv run lmgmt ls --all       # List all services

# View service logs
uv run lmgmt logs platform -f
uv run lmgmt logs kas-alpha -f
uv run lmgmt logs --grep error    # Find errors

# Or check log files directly
tail -f tests/xtest/logs/platform.log
tail -f tests/xtest/logs/kas-alpha.log

# Kill stuck processes
pkill -9 -f "go.*service.*start"

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

### Preferred Workflow

1. **Use lmgmt for environment management** - It provides better error handling, health checks, and logs
2. **Start environment**: `cd tests/lmgmt && uv run lmgmt up`
3. **Check status**: `uv run lmgmt status`
4. **Configure shell environment**: `eval $(uv run lmgmt env)` - Sets up environment variables for pytest
5. **View logs**: `uv run lmgmt logs -f`
6. **Run tests**: `cd ../xtest && uv run pytest --sdks go -v`
7. **Restart services**: `cd ../lmgmt && uv run lmgmt restart <service>` after config changes

### When Debugging Test Failures

1. Read error messages carefully - they guide you to the root cause
2. Check platform configuration matches expected test behavior
3. Verify all KAS instances have consistent keys
4. Ensure services are running and healthy (`lmgmt status`)
5. Check service logs (`lmgmt logs <service> -f`)
6. Reproduce issues manually when possible
7. Always restart services after config changes (`lmgmt restart <service>`)
8. Read before writing - understand existing code patterns

The test failures are usually symptoms of configuration mismatches, not SDK bugs. Focus on ensuring the local environment matches what the tests expect.
