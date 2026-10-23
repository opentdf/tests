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

# Prepare a benchmark: the first ref is the reference, the rest candidates
otdf-sdk-mgr install benchmark go v0.38.0 main pr:123 --platform main --otdfctl v0.38.1
```

`install benchmark` resolves every ref (and the `--otdfctl` pin) to a commit
before building anything, rejects two refs that would share a `dist/`
directory at different commits, and installs each side by side under
`xtest/sdk/<sdk>/dist/`. A source build records the commit it actually built in
`dist/<slug>/.version` and is reused only while that is still the ref's commit.

It writes `xtest/sdk/benchmark.installed.json` (`--manifest` to override) on
every exit path. Its `status` is one of:

| Status | Meaning | Exit |
|---|---|---|
| `success` | Every arm and pin installed. `status_message` warns if two arms are one build. | 0 |
| `neutral` | Every ref resolved to one build, so nothing was installed or compared. | 0 |
| `partial` | Some installs completed before one failed; the manifest lists them. | 1 |
| `failed` | Nothing completed: a resolve error, a collision, or the first install failed. | 1 |

Each arm records its requested alias, repository, `commit_sha` (`null` for a
js release found on npm but not in git), dist directory, and install method;
`metadata.sdk` names the SDK.

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
- **JS**: Runs `npm install @opentdf/ctl@{version}` into the dist directory if npm has it. web-sdk has released without publishing the CLI (sdk 0.21.0 and 0.22.0 reached npm as `@opentdf/sdk` only), so otherwise, if `@opentdf/sdk` is on npm at that version, shallow-clones the release tag (`sdk-vX.Y.Z`, or `sdk/vX.Y.Z` through 0.4.0) and packs just `cli/` against the published sdk, skipping the lib build. This path needs `git` and Node, and takes about a minute. If neither works, the install fails and CI falls back to a full source build. `latest` and `install stable` mean the newest `sdk-v*` release tag, not the newest CLI on npm. `cli.sh` runs `node_modules/.bin/opentdf` directly, never `npx`, which would fetch and run npm's latest if the local install were missing
- **Java**: Downloads `cmdline.jar` from GitHub Releases if the release has one. Otherwise, if `io.opentdf.platform:sdk` is on Maven Central at that version, shallow-clones the tag and builds only the CLI (`mvn -pl .,cmdline package`) against the published sdk jars, which skips the sdk module's `buf generate` and its buf.build rate limits. That build uses its own local Maven repository (`~/.m2/otdf-sdk-mgr-releases`) so a same-versioned head `mvn install`ed into `~/.m2/repository` can't shadow the release; delete it to reclaim space. This path needs `git`, a JDK, and Maven, and takes a few minutes. If neither works, the install fails and CI falls back to a full source build. `cli.sh` uses `java -jar cmdline.jar`

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
