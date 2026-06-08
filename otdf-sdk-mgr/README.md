# otdf-sdk-mgr

SDK artifact management CLI for OpenTDF cross-client tests.
Installs SDK CLIs from **released artifacts** (fast, deterministic) or **source** (for branch/PR testing).
Both modes produce the same `sdk/{go,java,js}/dist/{version}/` directory structure.

## Installation

```bash
cd otdf-sdk-mgr && uv tool install --editable .
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

# Install from a feature branch, PR, tag, or SHA (source build)
otdf-sdk-mgr install tip --ref my-feature-branch platform
otdf-sdk-mgr install tip --ref pr:42 go              # pr:N → refs/pull/N/head
otdf-sdk-mgr install tip --ref abc123f4 platform     # SHA (cached on re-run)
otdf-sdk-mgr install tip --ref refs/pull/42/head go  # raw ref

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

- **Go**: Writes a `.version` file containing `module-path@version`; `cli.sh`/`otdfctl.sh` use `go run <module>@<version>` (no local compilation needed, Go caches the binary). The resolver always targets the opentdf/platform monorepo (`github.com/opentdf/platform/otdfctl`) for v0.31.0 and newer; pre-v0.31.0 tags fall back to the archived standalone repo (`github.com/opentdf/otdfctl`) for artifact install via the Go module proxy. Bare semver inputs like `v0.32.0` are auto-prepended with `otdfctl/` when looking up platform tags.
- **JS**: Runs `npm install @opentdf/ctl@{version}` into the dist directory; `cli.sh` uses `npx` from local `node_modules/`
- **Java**: Downloads `cmdline.jar` from GitHub Releases; `cli.sh` uses `java -jar cmdline.jar`

## Source Builds

Source builds (`tip` mode) check out source to `sdk/{lang}/src/` and compile via `make` to `sdk/{lang}/dist/`. For Go, the platform monorepo is cloned to `sdk/go/platform-src/{ref}/` and `sdk/go/src/{ref}` is a symlink to its `otdfctl/` subdirectory; `make` discovers the platform's top-level `go.work` automatically so `protocol/go`, `sdk`, and `lib/*` resolve to the local checkout.

`--ref` accepts branches, tags, SHAs, the `pr:N` shorthand (expands to
`refs/pull/N/head`), and raw `refs/...` paths. Mutable refs (branches and
PR heads) are re-fetched and rebuilt on every invocation so the dist
matches the latest upstream commit; immutable refs (tags and full-length
SHAs) reuse the cached build for speed.

| Ref form                       | Mutable? | Dist directory name      |
|--------------------------------|----------|--------------------------|
| `--ref main` (default)         | yes      | `dist/tip/` (platform), `dist/main/` (SDK) |
| Other branches, `pr:N`, raw `refs/...` | yes | slug of the ref, e.g. `dist/my-branch/`, `dist/refs--pull--42--head/` |
| `v0.9.0`, `service/v0.9.0`     | no       | `dist/v0.9.0/`           |
| Full 40-char SHA               | no       | `dist/v<sha>/`           |

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
