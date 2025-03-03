# X-Test

> Compatibility tests for opentdf client libraries and tools.

## Requirements

- `go 1.22.3`
- `node 20`
- `python 3.12`
- `jdk 11`
- `maven`

```shell
brew install maven
```

## Platform Setup

### Install SDKs

#### Java SDK

```shell
git clone https://github.com/opentdf/java-sdk.git
cd java-sdk
mvn --batch-mode clean install -DskipTests
mv cmdline/target/cmdline.jar ../sdk/java/cmdline.jar
```

#### Go SDK wrapped by otdfctl

```shell
git clone https://github.com/opentdf/platform
git clone https://github.com/opentdf/otdfctl.git
cd otdfctl
go mod edit -replace github.com/opentdf/platform/protocol/go=../platform/protocol/go
go mod edit -replace github.com/opentdf/platform/sdk=../platform/sdk
go mod tidy
go build .
mv otdfctl ../sdk/go/otdfctl
```

### Platform Backend

1. **Initialize Platform Configuration**
   ```shell
   cp opentdf-dev.yaml opentdf.yaml
   sed -i '' 's/e1/ec1/g' opentdf.yaml
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

### Setup SDK CLIs
Set the paths to the local repos in env variables
```shell
JS_DIR=../../../web-sdk
PLATFORM_DIR=../../../platform
OTDFCTL_DIR=../../../otdfctl
JAVA_DIR=../../../java-sdk
```
Build all the clis and setup within xtest
```shell
cd sdk
make all
```

### Install requirements

```shell
pip install -r requirements.txt
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
