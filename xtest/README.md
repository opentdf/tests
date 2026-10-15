# X-Test

> Compatibility tests for opentdf client libraries and tools.

## Requirements

- `go 1.24` (For the Go SDK, otcfctl tool, and platform services)
- `node 22` (For the JavaScript SDK and the headless-browser `web` flavour)
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
`make web` additionally stages the headless-browser `web` flavour from the
`sdk/js/src` checkouts (see below); it is not part of the default target
because it downloads a Playwright browser.

#### The `web` flavour: web-sdk in a headless browser

`js` exercises web-sdk through its Node CLI (`@opentdf/ctl`). `web` runs the
same library, `@opentdf/sdk`, inside headless Chromium, which is the runtime
web-sdk is built for. Running both separates browser behaviour from Node
behaviour: DSPX-5160 (Node's `fs.openAsBlob` truncating Blob sizes to 32 bits,
so `js` cannot decrypt TDFs of 4 GiB or more) is a Node bug, not an SDK bug,
and `web` shows it.

```sh
cd otdf-sdk-mgr
uv run otdf-sdk-mgr install stable web          # newest @opentdf/sdk release
uv run otdf-sdk-mgr install release web:0.22.0  # a specific release
uv run otdf-sdk-mgr install tip --ref main web  # from source (shares sdk/js/src)
cd ../xtest
uv run pytest test_tdfs.py --sdks "go js web" -v
```

Requires `node` and `jq`. `web` is versioned by the `@opentdf/sdk` version
(recorded in `sdk/web/dist/<version>/features.json`); `cli.sh supports`
answers from that file, mostly with the same gates as the `js` shim.

How a `sdk/web/dist/<version>/cli.sh encrypt|decrypt <src> <dst> <fmt>` call
works (`sdk/web/driver/`):

1. `driver.mjs` starts an HTTP server on an ephemeral `127.0.0.1` port that
   serves a page plus `bundle.js` (`page.js` bundled with the library by
   esbuild at install time).
2. Playwright launches headless Chromium and attaches `<src>` to an
   `<input type=file>` with `setInputFiles`. The browser gets the path, not a
   copy, so a 64 GiB input costs nothing to pass in, and `File.size` is exact.
3. The page authenticates with client credentials (`CLIENTID` /
   `CLIENTSECRET`) and runs `createTDF` or `read`.
4. Output leaves the page as offset-tagged chunked POSTs to a sink on the
   same server, at most four 4 MiB requests in flight. The sink writes them
   positionally to `<dst>`, or discards them for `/dev/null`. This works in
   every engine and keeps memory bounded. Downloads don't under automation:
   Playwright's bundled Firefox keeps every response body in memory, which
   took a CI runner down at 4 GiB (DSPX-5084), and WebKit buffers a download
   that arrives faster than the disk takes it (DSPX-5246). A download also
   can't be discarded, so `/dev/null` would still write to disk.

Cross-origin calls. The driver never disables web security.

- Keycloak is reverse-proxied under `/__kc/` on the page's origin, with
  `Host` rewritten so the token's `iss` is still the real Keycloak URL.
  Keycloak's dev clients send no CORS headers on the token endpoint, and real
  browser apps use an auth-code flow anyway, so the proxy is test scaffolding.
- The platform and KAS are called directly, cross-origin, and rely on the
  platform's own CORS config (`server.cors` in `opentdf-dev.yaml`, which
  allows any origin). They can't be proxied without changing what is tested:
  the KAS URL the SDK talks to is the URL it writes into each Key Access
  Object, so a proxied URL would end up in every web-encrypted TDF, and other
  SDKs could not decrypt it. Decrypt also has to reach whatever KAS URLs a go
  or java TDF carries. Calling direct means a CORS regression in the platform
  shows up as a `web` failure, which is a browser behaviour worth catching.

Driver knobs: `XT_WEB_BROWSER=firefox|webkit` (default `chromium`; only
Chromium is installed and exercised in CI), `XT_WEB_HEADED=1` to watch the
browser, `XT_WEB_DEBUG=1` to echo every page console message. `XT_WITH_DPOP`,
`XT_WITH_ECDSA_BINDING` and `XT_WITH_PLAINTEXT_POLICY` are rejected with an
error instead of being ignored, and `supports dpop` answers no.

Encrypting more than the library's `GLOBAL_BYTE_LIMIT` fails in the browser
just as it does in Node, until DSPX-4652. Decrypting large go/java TDFs works.
Under `--bench`, the measured process tree includes Chromium. Startup costs
about a second, and peak RSS reflects the largest browser process.

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

#### Testing unreleased platform features

Set `XT_FORCE_PLATFORM_SUPPORTS` to a comma-separated list of platform features
to bypass their test gates. In CI, use the `force-platform-supports` input.
SDK overrides use `XT_FORCE_SUPPORTS` separately. These overrides do not enable
service configuration.

Both reject unknown feature names. A few features are platform-only
(`PLATFORM_ONLY_FEATURES` in `tdfs.py`); naming one in `XT_FORCE_SUPPORTS` is
rejected too, because it would force the feature on for every SDK while leaving
the platform gate the tests read untouched — a green run that tested nothing.

#### Run TDF Tests

```shell
rm -rf tmp
pytest test_tdfs.py
```
