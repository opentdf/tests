# X-Test

> Compatibility tests for opentdf client libraries and tools.

## Requirements

- `go 1.22.3`
- `node 20`
- `python 3.10`
- `jdk 11`
- `maven`

```shell
brew install maven
```

## Platform Setup (macOS)

### Install SDKs

#### Java SDK

```shell
git clone https://github.com/opentdf/java-sdk.git
cd java-sdk
mvn --batch-mode clean install -DskipTests
mv java-sdk/cmdline/target/cmdline.jar sdk/java/cmdline.jar
```

### Bringing up the Platform Backend

1. **Checkout Platform Repository**
   ```shell
   git clone https://github.com/opentdf/platform
   cd platform
   ```
2. **Initialize Platform Configuration**
   ```shell
   cp opentdf-dev.yaml opentdf.yaml
   sed 's/e1/ec1/g' opentdf.yaml
   .github/scripts/init-temp-keys.sh
   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ./keys/localhost.crt
   ```
   - To remove the certificate, run:
     ```shell
     sudo security delete-certificate -c "localhost"
     ```
3. **Start Background Services**
   ```shell
   docker compose up
   ```
4. **Provision Keycloak**
   ```shell
   go run ./service provision keycloak
   ```
5. **Add Sample Attributes and Metadata**
   ```shell
   go run ./service provision fixtures
   ```
6. **Start Server in Background**
   ```shell
   go run ./service start
   ```

## Testing with Released Software

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
