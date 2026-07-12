# Community SDK Conformance

This fork (`arkavo-org/opentdf-tests`) extends official OpenTDF `xtest` with **community SDKs**:

| SDK | Repo | Stage-1 (↔ go) | Stage-2 (community × community) |
|-----|------|----------------|----------------------------------|
| **Python** | [b-long/opentdf-python-sdk](https://github.com/b-long/opentdf-python-sdk) | ubuntu ↔ go@latest | ubuntu ↔ rust; macos ↔ rust/swift |
| **Rust** | [arkavo-org/opentdf-rs](https://github.com/arkavo-org/opentdf-rs) | ubuntu ↔ go@latest (`0.14.0+`) | ubuntu ↔ python; macos ↔ python/swift |
| **Swift** | [arkavo-org/OpenTDFKit](https://github.com/arkavo-org/OpenTDFKit) | macos ↔ go@latest (`4.0.0+`) | macos ↔ python/rust |

Pins default to floating **`latest`** GitHub releases.  
Full design: [community-xtest-design.md](./community-xtest-design.md).  
**Format naming:** [FORMATS.md](./FORMATS.md) (Base TDF vs ZTDF vs NanoTDF).

## What Stage-1 proves

For each **kas-ready** community SDK:

1. **Community encrypt → Go decrypt** (interop)
2. **Go encrypt → Community decrypt** (interop)
3. Container: **Base TDF (`tdf`) only** — not NATO ZTDF, not NanoTDF, not full ABAC/PQC
4. Feature honesty: `cli.sh supports <feature>` must not advertise features that fail tests

## What Stage-2 proves

When ≥2 community SDKs are kas-ready (criterion met for python + rust + swift):

1. **Community A encrypt → Community B decrypt** (and reverse), live KAS
2. Same Base TDF / `stage1` roundtrip cell as Stage-1 — go is fixture-only (otdfctl attributes), not an encrypt/decrypt peer
3. Jobs:
   - `python × rust` on ubuntu
   - `python × rust × swift` on macos (CryptoKit)

## Local setup (Python)

```bash
# Prerequisites: go, python 3.14, uv, docker + running platform (or CI)

cd opentdf-tests

# Link or checkout python SDK
mkdir -p xtest/sdk/python/src
ln -sfn "$(pwd)/../opentdf-python-sdk" xtest/sdk/python/src/main

# Build dist/cli
make -C xtest/sdk/python VERSIONS=main

# Also need go for attribute fixtures (see official xtest README)
# Then Stage-1:
cd xtest
uv sync
set -a && source test.env && set +a
uv run pytest -m stage1 --containers tdf \
  --sdks-encrypt "python@main go@main" \
  --sdks-decrypt "python@main go@main" \
  --focus python \
  test_tdfs.py

# Stage-2 (python × rust) — also build rust CLI first:
# make -C sdk/rust VERSIONS=main
uv run pytest -m stage1 --containers tdf \
  --sdks-encrypt "python@main rust@main" \
  --sdks-decrypt "python@main rust@main" \
  --focus "python rust" \
  test_tdfs.py
```

## CI

Workflow: `.github/workflows/community-xtest.yml`

- Runs on PRs that touch xtest / otdf-sdk-mgr / the workflow / docs
- Spins up platform via `opentdf/platform` composite (ubuntu) or native macOS action (swift)
- Builds go@latest (fixtures) + community CLI(s)
- Stage-1 + Stage-2 by default; `workflow_dispatch` input `stage` = `all` | `1` | `2`
- Publishes HTML + junit + `supports.json` artifacts
- Human report: https://arkavo-org.github.io/opentdf-tests/ (branch Pages)
## Badge ownership

| Failure class | Owner |
|---------------|--------|
| Harness / workflow / report bugs | `arkavo-org/opentdf-tests` |
| Encrypt/decrypt/supports lies or crypto bugs | respective community SDK maintainers |

## Offline probes (Rust / Swift)

```bash
./sdk/rust/dist/main/cli.sh supports tdf   # or legacy: supports ztdf
```
