---
name: scenario-matrix
description: This skill should be used when the user asks to "run the same suite across multiple versions", "bisect a regression across releases", "validate a fix across PRs", "generate a scenario matrix", or wants the same test suite exercised at N different platform / SDK refs. Generates scenario files only; does not run them — hand the output to `scenario-up` / `scenario-run` per cell.
allowed-tools: Bash, Read, Write, Grep, Glob
---

# scenario-matrix

Produce N scenario files from one base scenario, where N is the number of refs the user wants exercised. Each output scenario differs only in `instance.platform` (and optionally any KAS pins the user says should track the same ref). SDK pins are preserved unless explicitly told to vary.

## Inputs

- A **base**, either:
  - Path to an existing `xtest/scenarios/<id>.yaml`, OR
  - A Jira ticket key — invoke `scenario-from-ticket` first to produce the base, then proceed.
- A **ref list** — any combination of:
  - Released versions: `v0.9.0`, `v0.8.5`
  - Branch names: `main`, `feature/ecdsa-binding`
  - PR numbers: `1234`, `1235` (resolved to head SHAs for reproducibility)
- (Optional) which KAS instances should track the same ref as `platform`. Default: every KAS instance in the base also tracks the ref.

## Process

### Step 1 — Resolve the base scenario

- If given a path: `Read` it.
- If given a ticket key: invoke `scenario-from-ticket` against the ticket first, then `Read` the produced file.

The base scenario provides everything except `instance.platform` (and tracked KAS pins): `metadata.title` becomes the title prefix, `suite` is shared across all cells, `sdks` is preserved.

### Step 2 — Resolve each ref to a concrete value

- Released version → use verbatim under `dist:`. Example: `v0.9.0` → `platform: { dist: v0.9.0 }`.
- Branch name → use under `source.ref:`. Example: `main` → `platform: { source: { ref: main } }`.
- PR number `N` → fetch:

  ```bash
  gh pr view <N> --json number,headRefName,headRefOid
  ```

  …and pin under `source.ref:` to the **`headRefOid`** (40-char SHA), **not** `headRefName`. Reason: branch names move on every push, SHAs don't. Record `headRefName` in the scenario title for human readability.

### Step 3 — Emit one scenario file per ref

Naming: `xtest/scenarios/<base-id>-<short-token>.yaml`. Tokens:

- Released version: strip `v` and dots — `v0.9.0` → `v090`.
- Branch: replace `/` with `-` — `feature/ecdsa-binding` → `feature-ecdsa-binding`.
- PR: `pr<N>` — `1234` → `pr1234`. The SHA still lives inside the file.

Each cell scenario gets:

- A unique `metadata.id` (`<base-id>-<token>`) matching the file basename.
- A unique `instance.metadata.name` (same as `metadata.id`).
- A unique `instance.ports.base` — start from the base's value and add `+1000` per additional cell. `scenario-up` rejects overlapping port bases between concurrent instances.
- `metadata.title` gets a ` [<token>]` suffix for at-a-glance identification.
- `instance.platform` rewritten to the resolved ref. For KAS pins that should track the same ref (default: all of them), rewrite their pin too. Pins the user explicitly excluded keep the base's value.
- `suite`, `sdks`, `expected`, `actual` — unchanged from the base.

### Step 4 — Validate every file

```bash
for f in xtest/scenarios/<base-id>-*.yaml; do
  uv run python -m otdf_sdk_mgr.schema validate "$f"
done
```

Bail (delete the just-written files) if any cell fails validation — partial matrices are confusing.

### Step 5 — Report

- The list of files written.
- The exact `scenario-up` / `scenario-run` chain the user can run per cell (or in a loop):

  ```bash
  for f in xtest/scenarios/<base-id>-*.yaml; do
    name="$(basename "$f" .yaml)"
    uv run otdf-sdk-mgr install scenario "$f"
    uv run otdf-local instance init "$name" --from-scenario "$f"
    uv run otdf-local --instance "$name" up
    uv run otdf-local scenario run --instance "$name" "$f"
    uv run otdf-local --instance "$name" down
  done
  ```

## Notes

- This skill **writes scenario files only**. It does not install artifacts, scaffold instances, or run pytest. Hand the resulting files to `scenario-up` and `scenario-run` per cell.
- For two PRs that differ in *SDK* (not platform), vary `sdks.<encrypt|decrypt>.<lang>.version` instead of `platform`. Same pattern, different field — `SdkPin.version` accepts the same range of refs (`v0.24.0`, `main`, SHA).
- For a full platform × SDK matrix, generate N×M scenarios. Be prepared for long install times — each new platform ref triggers a `go build` (~30–60s first time per version); subsequent runs reuse the cached binary.
- Don't update `expected:` / `actual:` per cell unless the user specifies that one of the refs is the "known good" or "known broken" baseline.

### Pre-install shared refs (workaround for [DSPX-3417](https://virtru.atlassian.net/browse/DSPX-3417))

`otdf-sdk-mgr install scenario` currently rebuilds the platform once per pin even when N pins share a ref — so an N-cell matrix on the same platform ref triggers N rebuilds, each ~30–60s. Workaround:

```bash
# Build once.
uv run otdf-sdk-mgr install tip --ref <shared-ref> platform
# Then run the per-cell loop in Step 5; each `install scenario` will reuse
# the cached binary instead of rebuilding.
```

When DSPX-3417's dedup ships, the workaround becomes unnecessary.
