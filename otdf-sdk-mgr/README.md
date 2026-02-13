# otdf-sdk-mgr

SDK artifact management CLI for OpenTDF cross-client tests. Installs SDK CLIs from **released artifacts** (fast, deterministic) or **source** (for branch/PR testing). Both modes produce the same `sdk/{go,java,js}/dist/{version}/` directory structure.

## Installation

```bash
cd tests/otdf-sdk-mgr && uv tool install --editable .
```

## Commands

### install

```bash
# Install latest stable releases for all SDKs (recommended for local testing)
otdf-sdk-mgr install stable

# Install LTS versions
otdf-sdk-mgr install lts

# Install specific released versions
otdf-sdk-mgr install release go:v0.24.0 js:0.4.0 java:v0.9.0

# Install from tip of main branch (source build)
otdf-sdk-mgr install tip
otdf-sdk-mgr install tip go    # Single SDK

# Install a published version with optional dist name (defaults to version tag)
otdf-sdk-mgr install artifact --sdk go --version v0.24.0
otdf-sdk-mgr install artifact --sdk go --version v0.24.0 --dist-name my-tag
```

### versions

```bash
# List available versions
otdf-sdk-mgr versions list go --stable --latest 3 --table

# Resolve version tags to SHAs
otdf-sdk-mgr versions resolve go main latest
```

### Other commands

```bash
# Checkout SDK source
otdf-sdk-mgr checkout go main

# Clean dist and source directories
otdf-sdk-mgr clean

# Fix Java pom.xml after source checkout
otdf-sdk-mgr java-fixup
```

## How Release Installs Work

- **Go**: Writes a `.version` file; `cli.sh`/`otdfctl.sh` use `go run github.com/opentdf/otdfctl@{version}` (no local compilation needed, Go caches the binary)
- **JS**: Runs `npm install @opentdf/ctl@{version}` into the dist directory; `cli.sh` uses `npx` from local `node_modules/`
- **Java**: Downloads `cmdline.jar` from GitHub Releases; `cli.sh` uses `java -jar cmdline.jar`

## Source Builds

Source builds (`tip` mode) delegate to `checkout-sdk-branch.sh` + `make`, which checks out source to `sdk/{lang}/src/` and compiles to `sdk/{lang}/dist/`.

After changes to SDK source, rebuild:
```bash
otdf-sdk-mgr install tip go   # or java, js

# Or manually: checkout + make
cd sdk/go  # or sdk/java, sdk/js
make

# Verify build worked
ls -la dist/main/cli.sh
```

## Manual SDK Operations

```bash
sdk/go/dist/main/cli.sh encrypt input.txt output.tdf --attr <fqn>
sdk/go/dist/main/cli.sh decrypt output.tdf decrypted.txt
```
