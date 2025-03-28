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
ln -s ../../../otcfctl  sdk/go/src/local
ln -s ../../../java-sdk sdk/java/src/local
ln -s ../../../web-sdk  sdk/js/src/local
```

#### Using the latest `platform` (go SDK code) in `otdfctl`

Use replace directives in the `otdfctl/go.mod` to point to the version of the SDK (or other libraries) you wish to test.

#### Build the SDKs

To build all the checked out SDKs, run `make` from the `sdk` folder.

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

### Install test harness requirements

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
