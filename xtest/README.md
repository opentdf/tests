# X-Test

> Compatibility tests for opentdf client libraries and tools.

## Requirements

- `go 1.24` (For the Go SDK, otcfctl tool, and platform services)
- `node 22` (For the JavaScript SDK)
- `python 3.12`
- `jdk 11` (For the Java SDK)
- `maven` (For the Java SDK)
- `docker` (For the platform backend)

```shell
brew install maven
```

## Platform Setup

### Install SDKs

#### Download the main branch of each SDK

First, download the latest head version of each test repo by running the helper script, 
This works by aliasing or checking out the source code for the different client libraries in the xtest/sdk folder.
To check out the current head versions of the sdks under test, run:

```sh
  ./sdk/scripts/checkout-all.sh
```

#### Download another tag of a specific sdk

```sh
  ./sdk/scripts/checkout-sdk-branch.sh go v0.19.0
```


#### Using locally checked out SDKs

If you are developing a new feature or fix for a local SDK
and have one or more them checked out as peers to the test working directory,
use a symbolic link to pull in your working tree:

```shell
mkdir -p sdk/{go,java,js}/src
GH_ORG_DIR=$(cd ../..; pwd)
ln -s "$GH_ORG_DIR/otcfctl" sdk/go/src/local
ln -s "$GH_ORG_DIR/java-sdk" sdk/java/src/local
ln -s "$GH_ORG_DIR/web-sdk" sdk/js/src/local
```

#### Using the latest `platform` (go SDK code) in `otdfctl`

Use replace directives in the `otdfctl/go.mod` to point to the version of the SDK (or other libraries) you wish to test.

```shell
cd sdk/go/src/local
go mod edit -replace github.com/opentdf/platform/lib/flattening=$GH_ORG_DIR/platform/lib/flattening
go mod edit -replace github.com/opentdf/platform/lib/ocrypto=$GH_ORG_DIR/platform/lib/ocrypto
go mod edit -replace github.com/opentdf/platform/protocol/go=$GH_ORG_DIR/platform/protocol/go
go mod edit -replace github.com/opentdf/platform/sdk=$GH_ORG_DIR/platform/sdk
```

#### Build the SDKs

To build all the checked out SDKs, run `make` from the `sdk` folder.

### Platform Backend

1. **Initialize Platform Configuration**
   ```shell
   cp opentdf-dev.yaml opentdf.yaml
   sed -i '' 's/e1/ec1/g' opentdf.yaml
   yq eval '.services.kas.ec_tdf_enabled = true' -i opentdf.yaml
   .github/scripts/init-temp-keys.sh
   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ./keys/localhost.crt
   ```
   - To remove the certificate, run:
     ```shell
     sudo security delete-certificate -c "localhost"
     ```
2. **Start Background Services**
   ```shell
   docker compose up
   ```
3. **Provision Keycloak**
   ```shell
   go run ./service provision keycloak
   ```
4. **Add Sample Attributes and Metadata**
   ```shell
   go run ./service provision fixtures
   ```
5. **Start Server in Background**
   ```shell
   go run ./service start
   ```

### Install test harness requirements

```shell
pip install -r requirements.txt
```

### Run Tests

#### Quick Start

Run all tests with parallel execution (recommended):
```shell
pytest -n auto test_tdfs.py test_policytypes.py
```

Run smoke tests only (fastest, ~2 minutes):
```shell
pytest -n auto -m smoke test_tdfs.py test_policytypes.py
```

#### Test Execution Options

**Parallel Execution:**
```shell
# Auto-detect CPU cores
pytest -n auto

# Explicit worker count
pytest -n 8
```

**Test Selection by Markers:**
```shell
# Run smoke tests (critical path)
pytest -m smoke

# Run only ABAC tests
pytest -m abac

# Run integration tests
pytest -m integration

# Run encryption-related tests
pytest -m encryption

# Exclude slow tests
pytest -m "not slow"
```

**SDK Selection:**
```shell
# Test specific SDK(s)
pytest --sdks go

# Test multiple SDKs
pytest --sdks go,js

# Focus tests on specific SDK (skips tests not using it)
pytest --focus go

# Separate encrypt/decrypt SDKs
pytest --sdks-encrypt go --sdks-decrypt js
```

**Container Format Selection:**
```shell
# Test specific container formats
pytest --containers nano,ztdf

# Test only nano format
pytest --containers nano
```

**Other Options:**
```shell
# Run tests with large files (> 4GB)
pytest --large

# Show test durations
pytest --durations=10

# Collect only (no execution)
pytest --collect-only
```

**Combined Examples:**
```shell
# Fast smoke test on Go SDK only
pytest -n auto -m smoke --focus go

# Full test suite with 8 workers
pytest -n 8 test_tdfs.py test_policytypes.py

# ABAC tests on nano container only
pytest -m abac --containers nano
```

#### Legacy Commands

Run all TDF tests (sequential, slow):
```shell
rm -rf tmp
pytest test_tdfs.py
```
