# X-Test

> Compatibility tests for opentdf client libraries and tools.

## Requirements

- `go 1.24` (For the Go SDK, otcfctl tool, and platform services)
- `node 22` (For the JavaScript SDK)
- `python 3.14`
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
  uv run --project otdf-sdk-mgr otdf-sdk-mgr checkout --all
```

#### Download another tag of a specific sdk

```sh
  uv run --project otdf-sdk-mgr otdf-sdk-mgr checkout go v0.19.0
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

#### Using uv (recommended)

```shell
uv sync
```

#### Development (includes ruff, pyright)

```shell
uv sync --extra dev
```

### Run Tests

```shell
pytest
```

#### Run TDF Tests

```shell
rm -rf tmp
pytest test_tdfs.py
```
