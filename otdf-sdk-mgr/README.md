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

# Build a commit from a local checkout, pushed or not (see Local Checkout Builds)
otdf-sdk-mgr install local go ../platform            # HEAD → dist/local, --sdks go@local
otdf-sdk-mgr install local java ~/src/java-sdk --rev my-fix --name my-fix

# Install a published version with optional dist name (defaults to version tag)
otdf-sdk-mgr install artifact --sdk go --version v0.24.0
otdf-sdk-mgr install artifact --sdk go --version v0.24.0 --dist-name my-tag

# Prepare a benchmark: the first ref is the reference, the rest candidates
otdf-sdk-mgr install benchmark go v0.38.0 main pr:123 --platform main --otdfctl v0.38.1
```

`install benchmark` resolves every ref (and the `--otdfctl` pin) to a commit
before building anything. It rejects an abbreviated SHA that no branch, tag or
PR head points at (give the full commit instead), and two refs that would share
a `dist/` directory at different commits. Then it installs each side by side
under `xtest/sdk/<sdk>/dist/`. A full SHA is not checked to exist, so a typo
in one fails only when that arm checks out.

A source build records the commit it actually built in `dist/<slug>/.version`,
and a later run reuses it only while that record is the ref's commit. The
record is all it checks: `make` in `xtest/sdk` rebuilds into the same directory
without touching `.version`, so after building local edits by hand, delete
`dist/<slug>` before benchmarking that ref. A release directory that already
exists is reused as is.

`pytest --bench` does not read the manifest yet. It picks its own arms from
what is under `dist/`: the newest final release as the baseline, and `main`
over other unreleased builds as the candidate. A release `--otdfctl` pin lands
in `go/dist/` too and competes for the baseline, so name the arms you prepared
with `--bench-baseline` and `--bench-candidate`.

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

- **Go**: Runs `go install <module>@<version>` with `GOBIN` set to the dist directory, so `cli.sh`/`otdfctl.sh` run the `otdfctl` binary directly, as for a source build, rather than paying `go run`'s startup on every call. Your own installed `otdfctl` is untouched. This needs a Go toolchain. A `.version` file records `module-path@version`; the wrappers `go run` that if the binary is missing. A go dist with a `.version` but no `otdfctl` is reinstalled rather than skipped. The build is staged in `sdk/go/.staging/`; `clean` removes what a killed install leaves there. The resolver always targets the opentdf/platform monorepo (`github.com/opentdf/platform/otdfctl`) for v0.31.0 and newer; pre-v0.31.0 tags fall back to the archived standalone repo (`github.com/opentdf/otdfctl`) for artifact install via the Go module proxy. Bare semver inputs like `v0.32.0` are auto-prepended with `otdfctl/` when looking up platform tags.
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

The java build runs `mvn clean install`, so `install tip java` and a hand-run
`make` in `sdk/java` install the branch's modules into `~/.m2/repository`. They
go in under the version in its pom, normally the last release's, and replace
the published artifacts of that version that other builds then resolve.
`install local java` avoids this (see below). After a tip build, delete
`~/.m2/repository/io/opentdf/platform/*/<version>` to restore them.

## Local Checkout Builds

`install tip` builds only what GitHub has. `install local <sdk> <path>` builds
a commit from a git checkout on your machine, so xtest can run a change before
you push it. It also works for a change that spans several repos, which you
can test together before publishing any of them.

```bash
otdf-sdk-mgr install local go ~/work/fix/platform
otdf-sdk-mgr install local java ~/work/fix/java-sdk
otdf-sdk-mgr install local js ~/work/fix/web-sdk
cd xtest
XT_FORCE_SUPPORTS=<feature> uv run pytest test_tdfs.py --sdks "go@local java@local js@local" -v
```

- **`<path>`** is the repository root: opentdf/platform for go (its `otdfctl/`
  directory works too), java-sdk for java, web-sdk for js. Colocated jj repos
  work like any other git checkout. Any other directory fails before anything
  is built, and so does a commit that lacks the files the SDK's build needs.
- **`--rev`** (default `HEAD`) is any revision the checkout resolves: a local
  branch, a tag, or a commit id, including one that no branch points at. Only
  committed changes are built. In a colocated jj repo `HEAD` is `@-`, so run
  `jj new` (or `jj commit`) first, or pass the working-copy commit with
  `--rev "$(jj log -r @ --no-graph -T commit_id)"`. git can't resolve jj
  change ids.
- **The checkout is only read.** The commit is cloned with
  `git clone --local` (which hard-links objects) into the same place a source
  build uses: `sdk/{lang}/src/<name>/`, or for go `sdk/go/platform-src/<name>/`
  plus the `sdk/go/src/<name>` symlink. The SDK's Makefile builds it there into
  `sdk/{lang}/dist/<name>/`. Nothing is written into `<path>`: no build output,
  worktrees, refs, or remotes. Dependencies are still downloaded as usual
  (Go modules, npm, Maven, and the java build's `buf generate`).
- **`--name`** defaults to `local`, and xtest selects the build with
  `--sdks <sdk>@<name>`. The names release and tip builds use (`main`, `HEAD`,
  versions, and SHAs) are refused. So is an existing `src/<name>` or
  `dist/<name>` that `install local` didn't create, such as a tip build of a
  branch that has the same name.
- **`dist/<name>/.version`** records `source=` (the checkout's absolute path),
  `rev=` and `sha=`. A re-run reuses the build while the path and commit both
  match. Otherwise it rebuilds from a fresh clone, for example after a new
  commit or from another checkout.
- **Java builds keep out of `~/.m2/repository`.** They install into
  `${XDG_CACHE_HOME:-~/.cache}/otdf-sdk-mgr/maven-repository` instead, and
  read `~/.m2/repository` as a read-only tail (`maven.repo.local.tail`,
  Maven 3.9 and later), so what is already downloaded is reused. An older
  Maven downloads everything again into that cache. Delete it to reclaim
  space.
- **Java builds need JDK 11 through 21.** The JDK Maven runs on (per
  `mvn --version`) is checked before anything is copied, and nothing switches
  it for you. On JDK 27 the build fails partway through. Set `JAVA_HOME`, for
  example
  `export JAVA_HOME="$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home"`.
- **Feature gates still need `XT_FORCE_SUPPORTS`.** The build reports the
  version in its source tree, normally the last release, so a version-gated
  `cli.sh supports` check says "no" for the change you are testing. See
  "Evaluating an unreleased fix" in the root `AGENTS.md`.

`install local` builds SDK CLIs only. otdf-local runs the platform service
from a source tree: a sibling `platform/` checkout, or `OTDF_LOCAL_PLATFORM_DIR`
(see `otdf-local/AGENTS.md`). To test a platform change, point it at a
separate checkout of that commit, not the one you are editing. `otdf-local up`
regenerates the tracked `opentdf-dev.yaml` in that directory and writes key
files into it. In a multi-repo workspace it can find the `platform/` beside
`tests/` on its own, so set `OTDF_LOCAL_PLATFORM_DIR`.

## Manual SDK Operations

```bash
sdk/go/dist/main/cli.sh encrypt input.txt output.tdf --attr <fqn>
sdk/go/dist/main/cli.sh decrypt output.tdf decrypted.txt
```
