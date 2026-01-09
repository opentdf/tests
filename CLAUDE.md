# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the OpenTDF integration testing repository that validates cross-SDK compatibility for the OpenTDF ecosystem.
It tests multiple SDKs (Go/otdfctl, JavaScript/web-sdk, Java) against various versions of the platform backend through automated GitHub workflows and local development.

**Repository Location**: `github.com/opentdf/tests`

**Related Repositories**:
- `github.com/opentdf/platform` - Platform backend services
- `github.com/opentdf/otdfctl` - Go CLI tool (referenced as "go" SDK in tests)
- `github.com/opentdf/web-sdk` - JavaScript SDK (referenced as "js" in tests)
- `github.com/opentdf/java-sdk` - Java SDK

## Architecture

### Test Framework (xtest/)

The core testing framework is a pytest-based system in `xtest/` that:

1. **Cross-SDK Testing**: Tests encrypt/decrypt operations across different SDK combinations (e.g., encrypt with Go, decrypt with Java)
2. **Version Matrix**: Tests multiple versions of each SDK against multiple platform versions
3. **Dynamic Fixtures**: Uses pytest fixtures in `conftest.py` to set up attributes, namespaces, KAS entries, and subject condition sets
4. **Feature Detection**: `tdfs.PlatformFeatureSet` detects platform version and enables/disables tests based on available features

**Key Python Modules**:
- `conftest.py` - Pytest configuration, fixtures, and parametrization logic
- `tdfs.py` - TDF container operations, SDK wrappers, and feature detection
- `abac.py` - Attribute-based access control helpers, otdfctl wrapper
- `nano.py` - Nano TDF format operations
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

## Contributing

All commits must include DCO sign-off:
```bash
git commit -s -m "Your commit message"
```

This adds a `Signed-off-by` line certifying you have rights to submit the contribution.
