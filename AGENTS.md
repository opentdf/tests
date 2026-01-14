# AGENTS.md

This file provides guidance to Claude Code and other AI assistants when working with code in this repository.

## Project Overview

This is the OpenTDF integration testing repository that validates cross-SDK compatibility for the OpenTDF ecosystem.
It tests multiple SDKs (Go/otdfctl, JavaScript/web-sdk, Java) against various versions of the platform backend through automated GitHub workflows and local development.

**Repository Location**: `github.com/opentdf/tests`

**Related Repositories**:
- `github.com/opentdf/platform` - Platform backend services, APIs, and Go SDK
- `github.com/opentdf/otdfctl` - Go CLI tool (referenced as "go" SDK in tests)
- `github.com/opentdf/web-sdk` - JavaScript SDK (referenced as "js" in tests)
- `github.com/opentdf/java-sdk` - Java SDK

## Architecture

### Test Framework (xtest/)

The core testing framework is a pytest-based system in `xtest/` that:

1. **Cross-SDK Testing**: Tests encrypt/decrypt operations across different SDK combinations (e.g., encrypt with Go, decrypt with Java)
2. **Version Matrix**: Tests multiple versions of each SDK against multiple platform versions
3. **Dynamic Fixtures**: Uses pytest fixtures to set up attributes, namespaces, KAS entries, and subject condition sets
4. **Feature Detection**: `tdfs.PlatformFeatureSet` detects platform version and enables/disables tests based on available SDK and platform features via CLI shell script wrappers

**Key Python Modules**:
- `conftest.py` - Pytest configuration and parametrization logic
- `fixtures/` - Domain-specific fixture modules (attributes, namespaces, keys, policies)
- `tdfs.py` - TDF container operations, SDK wrappers, and feature detection
- `abac.py` - Attribute-based access control helpers, otdfctl wrapper
- `assertions.py` - TDF assertion/obligation handling
- `test_*.py` - Test suites for different scenarios

### SDK Management (xtest/sdk/)

SDKs are checked out into `xtest/sdk/{go,java,js}/src/{version}/` and built using version-specific Makefiles.

#### Directory Structure

```
xtest/sdk/
├── go/
│   ├── src/
│   │   ├── otdfctl.git/        # Bare repository
│   │   ├── main/               # Worktree for main branch
│   │   └── v0.19.0/            # Worktree for v0.19.0 tag
│   ├── dist/
│   │   ├── main/               # Built artifacts for main
│   │   └── v0.19.0/            # Built artifacts for v0.19.0
│   └── cli.sh                  # SDK wrapper script
├── java/
│   └── ...                     # Similar structure
└── js/
    └── ...                     # Similar structure
```

#### Management Scripts

**Query SDK State:**
```bash
# List all checked-out SDK versions (JSON format)
./sdk/scripts/list-available.sh

# List in human-readable table format
./sdk/scripts/list-available.sh --format table
```

Output includes:
- SDK type (go/java/js)
- Version/branch name
- Current git SHA
- Build status (whether `dist/{version}/` exists)
- File paths for source and dist directories

**Checkout SDKs:**
```bash
# Check out main branch of all SDKs
./sdk/scripts/checkout-all.sh

# Check out specific version of a single SDK
./sdk/scripts/checkout-sdk-branch.sh go v0.19.0
./sdk/scripts/checkout-sdk-branch.sh js main
```

**Build SDKs:**
```bash
# Build all checked-out SDK versions
cd sdk && make

# Build specific SDK
cd sdk && make go
```

**Update SDKs:**
```bash
# Update main branches only (recommended)
./sdk/scripts/update-all.sh

# Update all checked-out versions
./sdk/scripts/update-all.sh --all
```

What it does:
- Pulls latest commits for main branches (or all versions with `--all`)
- Reports SHA changes for each SDK (e.g., `abc1234 → def5678`)
- Automatically rebuilds only the SDKs that were updated
- Skips SDKs that don't have main checked out

**Cleanup:**
```bash
# Remove all checked-out versions and build artifacts
./sdk/scripts/cleanup-all.sh
```

**Version Resolution:**
- `scripts/resolve-version.py` maps tags/branches/SHAs to concrete commit SHAs
- Used in CI to resolve version matrices
- Supports: semantic versions (`v0.19.0`), branches (`main`), SHAs, PRs (`refs/pull/123`), special tags (`latest`, `lts`)

**CLI Wrappers:**
- Each SDK has standardized shell scripts (`cli.sh`, `otdfctl.sh`) that provide uniform interfaces
- Wrappers handle SDK-specific invocation differences (e.g., Java classpath, Node.js module loading)

#### When to Use `list-available.sh`

Use this script when you need to:
- Understand what SDK versions are currently checked out before running tests
- Verify that required SDK versions are built before starting test execution
- Debug why tests aren't finding a particular SDK version
- Clean up specific versions (first list, then selectively remove)
- Quickly assess the current SDK environment state

The JSON output is particularly useful for scripting and automation, while the table format is better for quick visual inspection.

### GitHub Workflows

**`.github/workflows/xtest.yml`** (Primary Integration Tests):
- Triggered on: PRs, workflow_dispatch, schedule (daily/bi-weekly/weekly)
- Job `resolve-versions`: Resolves version matrices for each SDK
- Job `xct`: Matrix build testing each SDK against each platform version
- Steps:
  1. Spin up platform backend with containers
  2. Check out and build SDK versions
  3. Run pytest suites (test_legacy.py, test_tdfs.py, test_policytypes.py, test_abac.py)
  4. Start additional KAS instances for multi-KAS tests
  5. Upload HTML test reports

**`.github/workflows/check.yml`** (Lint/Static Analysis):
- Runs shellcheck on shell scripts
- Runs ruff, black, and pyright on Python code

**`.github/workflows/vulnerability.yml`** (Vulnerability Tests):
- Currently disabled (temporarily)
- Playwright-based tests in `vulnerability/` directory

### Test Parametrization

Tests are heavily parametrized via pytest fixtures:

```python
# conftest.py defines:
@pytest.fixture
def encrypt_sdk(request):
    # Parametrized to test all SDK versions for encryption

@pytest.fixture
def decrypt_sdk(request):
    # Parametrized to test all SDK versions for decryption

@pytest.fixture
def container(request):
    # Parametrized for nano, ztdf, etc.
```

The `--focus` flag filters which SDK combinations run (used in CI to split jobs by SDK).

## Development Commands

### Local Setup

1. **Install dependencies**:
```bash
cd xtest
pip install -r requirements.txt
```

2. **Check out SDKs**:
```bash
cd xtest
./sdk/scripts/checkout-all.sh  # Checks out main branch of all SDKs
# OR for specific version:
./sdk/scripts/checkout-sdk-branch.sh go v0.19.0
```

3. **Build SDKs**:
```bash
cd xtest/sdk
make  # Builds all checked-out SDK versions
```

4. **Start platform backend** (from platform repo):
```bash
# Clone platform repo as sibling to tests repo
cd ../../platform
docker compose up  # Start dependencies
go run ./service provision keycloak
go run ./service provision fixtures
go run ./service start
```

### Running Tests

**All tests**:
```bash
cd xtest
pytest
```

**Specific test file**:
```bash
pytest test_tdfs.py
```

**Single SDK focus**:
```bash
pytest --focus go test_tdfs.py
```

**Specific SDK versions for encrypt/decrypt**:
```bash
pytest --sdks-encrypt go --sdks-decrypt "go java js" test_tdfs.py
```

**Generate HTML report**:
```bash
pytest --html=test-results/report.html --self-contained-html test_tdfs.py
```

**Verbose output with test duration**:
```bash
pytest -v -ra --durations=10
```

### Linting

**Python**:
```bash
cd xtest
ruff check          # Linting
black --check .     # Code formatting check
pyright             # Type checking
```

**Shell scripts**:
```bash
docker run --rm -v "$PWD:/mnt" --workdir "/mnt" "koalaman/shellcheck:v0.8.0" \
    $(find . -type f -exec grep -m1 -l -E '^#!.*sh.*' {} \; | grep -v '/.git/')
```

## Key Testing Concepts

### Feature Detection

Platform features are detected via `PLATFORM_VERSION` environment variable:
```python
pfs = tdfs.PlatformFeatureSet()
if "key_management" not in pfs.features:
    pytest.skip("Key management not supported")
```

Feature flags in `tdfs.py`:
- `assertions`, `assertion_verification` - TDF assertion support
- `autoconfigure` - Auto-configuration support
- `ecwrap` - Elliptic curve key wrapping (0.4.40+)
- `key_management` - Explicit KAS key management
- `nano_ecdsa` - ECDSA support in Nano TDF
- `obligations` - Policy obligations

### Multi-KAS Testing

Tests in `test_abac.py` verify attribute-based access with multiple KAS instances:
- Default KAS: `localhost:8080`
- Additional KAS: `localhost:8181`, `8282`, `8383`, `8484`
- Key management KAS: `localhost:8585`, `8686`

### Test Structure Pattern

Most tests follow this pattern:
```python
def test_scenario(encrypt_sdk, decrypt_sdk, attribute_fixture, pt_file, tmp_dir):
    # 1. Encrypt with first SDK using attribute
    ct_file = encrypt_sdk.encrypt(pt_file, [attribute])

    # 2. Decrypt with second SDK
    result = decrypt_sdk.decrypt(ct_file, tmp_dir / "output.txt")

    # 3. Verify content matches
    assert_files_equal(pt_file, result)
```

## Adding Features

### Adding a New Test

1. Add test function to appropriate `test_*.py` file
2. Use existing fixtures for setup (attributes, namespaces, etc.)
3. Parametrize with `encrypt_sdk`, `decrypt_sdk`, `container` as needed
4. Use `in_focus` fixture to filter by SDK when needed:
```python
def test_new_feature(encrypt_sdk, decrypt_sdk, in_focus):
    if encrypt_sdk not in in_focus:
        pytest.skip("Not in focus")
```

### Adding a New Platform Feature

1. Add feature flag to `feature_type` Literal in `tdfs.py`
2. Add version detection in `PlatformFeatureSet.__init__`:
```python
if self.semver >= (0, 5, 0):
    self.features.add("new_feature")
```
3. Use feature detection in tests:
```python
pfs = tdfs.PlatformFeatureSet()
if "new_feature" not in pfs.features:
    pytest.skip("Platform doesn't support new_feature")
```

### Adding a New SDK Version

1. Ensure version is tagged in SDK repo
2. CI will automatically discover it via `resolve-version.py`
3. For local testing:
```bash
./sdk/scripts/checkout-sdk-branch.sh <sdk> <version>
cd sdk
make
```

## Workflow Integration

The test repository is designed to be triggered by other repos:

**From platform repo**:
```yaml
- uses: opentdf/tests/.github/workflows/xtest.yml@main
  with:
    platform-ref: ${{ github.sha }}
```

**From SDK repos**:
```yaml
- uses: opentdf/tests/.github/workflows/xtest.yml@main
  with:
    js-ref: ${{ github.sha }}
    focus-sdk: js
```

This validates PRs against the current main of other components.

## Environment Variables

Key environment variables used in tests:

- `PLATFORM_VERSION` - Detected platform version (e.g., "0.4.40")
- `PLATFORM_DIR` - Path to platform working directory (default: `../../platform`)
- `PLATFORM_TAG` - Git tag/branch of platform being tested
- `OTDFCTL_HEADS` - JSON array of otdfctl head versions
- `KASURL`, `KASURL1-6` - URLs for KAS instances
- `OT_ROOT_KEY` - Root key for key management features
- `KEY_MANAGEMENT_SUPPORTED` - Whether key management is enabled
- `FOCUS_SDK` - Which SDK to focus on (go/java/js/all)
- `ENCRYPT_SDK` - Which SDK is being tested for encryption

## Common Pitfalls

1. **Missing SDK builds**: Always run `make` in `sdk/` after checking out new versions
2. **Platform not running**: Tests require platform backend; check `docker compose` status
3. **Version skew**: Ensure `PLATFORM_VERSION` env var is set correctly
4. **Focus filtering**: When adding tests, consider `--focus` flag behavior for CI matrix
5. **Fixture scope**: Most fixtures are module-scoped to avoid recreating attributes/namespaces

## Performance Considerations

From `TESTING.md`:
- Tests are I/O bound (file encryption/decryption)
- Serial execution is slow (~28 minutes for full suite)
- CI uses matrix parallelization by SDK to reduce time (~2 minutes per job)
- Consider using `pytest-xdist` for local parallelization (requires refactoring)

## Tmux Development Environment

The repository includes tmux-based tools for managing the multi-service development environment. These tools simplify running and monitoring the platform backend, multiple KAS instances, and tests simultaneously.

### Prerequisites

**macOS users**: The `watch` command is not installed by default on macOS but is required for the control panel dashboard. Install it with Homebrew:
```bash
brew install watch
```

### Tmux Scripts

**`tmux-dev.sh`** - Main development environment launcher:
- Creates a tmux session named `opentdf-dev` with multiple windows
- Supports three modes:
  - `--minimal`: Docker + platform only
  - `--standard`: Docker + platform + 2 KAS instances (alpha, beta)
  - `--full`: All services including 6 KAS instances (alpha, beta, gamma, delta, km1, km2)
- Windows created:
  - `control`: Status dashboard showing service health (updates every 2 seconds)
  - `docker`: Docker Compose logs
  - `platform`: Platform main service on port 8080
  - `kas-*`: Individual KAS instance windows with logs
  - `tests`: Test runner shell
- Key features:
  - Automatically starts Docker Compose services
  - **Provisions Keycloak and fixtures on startup** (can be skipped with `--skip-provision`)
  - Automatically starts services if not running
  - Reattaches to existing services if already running
  - Exports environment variables to tmux session
  - Handles nested tmux detection and prompts user appropriately

**Usage:**
```bash
# Start full environment (includes provisioning)
./tmux-dev.sh

# Start minimal environment
./tmux-dev.sh --minimal

# Skip provisioning if already done (faster startup)
./tmux-dev.sh --skip-provision

# Attach to existing session
./tmux-dev.sh --attach-only

# Stop and cleanup
./tmux-dev.sh --stop
```

**Note on Provisioning:**
The script automatically provisions Keycloak and fixtures on first startup, which takes 30-60 seconds. On subsequent runs, use `--skip-provision` to skip this step if you haven't torn down the Docker Compose services. The provisioning commands are generally idempotent but can be slow.

**`tmux-control-panel.sh`** - Status dashboard script:
- Displays real-time service status (running/stopped)
- Shows log file paths for all services
- Lists quick commands and tmux navigation shortcuts
- Designed to be run with `watch` (updates every 2 seconds)
- Shows different services based on the MODE environment variable

**`run-local.sh`** - Test runner wrapper:
- Ensures platform is running before tests
- Starts additional KAS instances if needed
- Exports log file paths as environment variables for audit log collection
- Supports running in tmux sessions (exports vars to tmux environment)
- Cleanup handler for KAS instances on exit
- Usage: `./run-local.sh [pytest-args]`

### Workflow for Using Tmux Tools

1. **Start the environment:**
   ```bash
   cd xtest
   ./tmux-dev.sh --full
   ```

2. **Navigate between windows:**
   - `Ctrl-b '` - Switch to window by name (type "tests", "platform", etc.)
   - `Ctrl-b w` - Show window list (interactive)
   - `Ctrl-b n/p` - Next/previous window

3. **Run tests in the tests window:**
   ```bash
   # Switch to tests window (Ctrl-b ')
   pytest test_tdfs.py -v
   ./run-local.sh test_abac.py
   ```

4. **Monitor logs:**
   - Platform logs: Switch to `platform` window or check `${PLATFORM_DIR}/logs/kas-main.log`
   - KAS logs: Switch to `kas-alpha`, `kas-beta`, etc., or check `${PLATFORM_DIR}/logs/kas-*.log`

5. **Detach/reattach:**
   - Detach: `Ctrl-b d` (keeps all services running)
   - Reattach: `./tmux-dev.sh --attach-only`

6. **Stop everything:**
   ```bash
   ./tmux-dev.sh --stop
   ```

### Debugging with Tmux

When debugging test failures:

1. **Check service status** - Look at the `control` window for service health
2. **Review logs** - Switch to the relevant service window to see real-time logs
3. **Run tests interactively** - Use the `tests` window to run specific tests with verbose output
4. **Monitor audit logs** - Audit log paths are exported by `run-local.sh` and available in test fixtures
5. **Restart individual services** - Switch to a service window, `Ctrl-c` to stop, up-arrow + Enter to restart

## Pytest 9.x Test Execution Order Changes

### Current Environment

- **Python**: 3.14.0
- **pytest**: 9.0.2

### Test Execution Order Behavior

Pytest 9.x has changed how it orders parametrized tests. This affects how module-scoped fixtures interact with test execution.

**Previous behavior (pytest < 9.x):**
- Tests were grouped by test function
- All parametrizations of one test function ran together
- Example order:
  ```
  test_tdf_assertions_with_keys[go-go]
  test_tdf_assertions_with_keys[go-js]
  test_tdf_assertions_with_keys[js-go]
  test_tdf_assertions_with_keys[js-js]
  test_other_test[go-go]
  test_other_test[go-js]
  ...
  ```

**Current behavior (pytest 9.x):**
- Tests are grouped by parametrization values
- One parametrization of each test runs, then cycles to the next parametrization
- Example order:
  ```
  test_tdf_assertions_with_keys[go-go]
  test_other_test[go-go]
  test_another_test[go-go]
  ...
  test_tdf_assertions_with_keys[go-js]
  test_other_test[go-js]
  test_another_test[go-js]
  ...
  ```

### Impact on Module-Scoped Fixtures

**Module-scoped fixtures** (like `assertion_file_rs_and_hs_keys`, `hs256_key`, `rs256_keys`) are still created once per module and reused across all tests. However, the order in which tests access these fixtures has changed.

**Key observations:**
- Module fixtures are set up before ANY test runs
- Module fixtures are torn down after ALL tests complete
- Function fixtures (like `encrypt_sdk`, `decrypt_sdk`) are set up/torn down for each test variant
- The new ordering groups tests by SDK combination, which can be more efficient for shared resources

### Debugging Test Order Issues

If you suspect test failures are due to execution order:

1. **Run tests in isolation:**
   ```bash
   pytest test_tdfs.py::test_tdf_assertions_with_keys -v
   ```

2. **Use `--setup-show` to see fixture execution:**
   ```bash
   pytest test_tdfs.py::test_tdf_assertions_with_keys -v --setup-show
   ```

3. **Check for test interdependencies:**
   - Module-scoped fixtures should be stateless or idempotent
   - Tests should not modify shared fixture state
   - Use function-scoped fixtures for test-specific setup

4. **Force old test ordering (if needed):**
   ```bash
   # Note: This may not fully replicate old behavior but can help debug
   pytest test_tdfs.py -v --tb=short --capture=no
   ```

5. **Identify fixture scope issues:**
   ```python
   # Check fixture scopes in conftest.py and fixtures/*.py
   grep -r "@pytest.fixture" xtest/
   ```

### Common Issues and Solutions

1. **Shared state in module fixtures:**
   - Problem: Module fixture creates mutable state that tests modify
   - Solution: Make fixtures stateless or use function scope

2. **Resource conflicts:**
   - Problem: Tests create conflicting resources (files, database entries)
   - Solution: Use unique identifiers per test (e.g., include test name in file paths)

3. **Setup/teardown order dependencies:**
   - Problem: Test assumes specific setup from previous test
   - Solution: Make each test fully independent with its own setup

4. **Fixture caching issues:**
   - Problem: Fixture returns cached value that should be fresh
   - Solution: Check fixture scope and consider using function scope

## Contributing

All commits must include DCO sign-off:
```bash
git commit -s -m "Your commit message"
```

This adds a `Signed-off-by` line certifying you have rights to submit the contribution.
