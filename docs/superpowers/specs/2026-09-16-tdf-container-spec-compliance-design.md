# TDF container spec compliance across SDKs

Date: 2026-09-16
Status: approved design, pending implementation plan
Scope: opentdf-python-sdk, opentdf-rs, OpenTDFKit, opentdf-platform (arkavo fork), opentdf-tests

## Goal

Bring every SDK in this workspace into compliance with the OpenTDF container
rules in `opentdf/spec` (`schema/OpenTDF/README.md`, `manifest.md`,
`payload.md`, `protocol/protocol.md`):

1. The manifest zip entry MUST be named exactly `manifest.json` at the archive root.
2. The payload zip entry name MUST be taken from `manifest.payload.url`. The
   spec calls `0.payload` the common value; we keep it.
3. Readers MUST understand the spec's `tdf_spec_version` field in either
   placement the spec has used (top-level per the prose, `payload.tdf_spec_version`
   per the JSON schema). Writers keep emitting `schemaVersion` only.

Secondary goal: make the conformance harness actually check the container
layout, which it does not today.

## What the audit found

All four SDKs share the same three defects:

| Defect | Python | Rust | Swift | Go (fork) |
|---|---|---|---|---|
| Manifest entry written as `0.manifest.json` | yes | yes | yes | yes |
| Reader does exact-name lookup of `0.manifest.json`, no fallback | yes | yes | yes | yes |
| Reader ignores `payload.url`, hard-codes `0.payload` | yes | yes | yes | yes |
| `payload.url` derived from the same constant as the zip entry | no (two literals) | no (caller-supplied) | no (two literals) | yes |
| Top-level version key | `schemaVersion` | `schemaVersion` = "3.0.0" | `schemaVersion` | `schemaVersion` |
| Reads `tdf_spec_version` (either placement) | no | `payload.` only | no | `payload.` only (schema) |

The harness (`xtest/tdfs.py`) hard-codes `0.manifest.json` and `0.payload` in
four helpers and has no test that inspects entry names. Its golden Java 4.3.0
file also uses `0.manifest.json`, so read-side fallback is permanent.

Per-SDK issues found but deferred to the backlog are listed at the end.

## Decisions

- **Writers switch to `manifest.json` now.** Upstream `opentdf/platform`,
  Java, JS, and released otdfctl cannot read that name today. The community
  CI stage-1 lanes decrypt against upstream otdfctl, so the
  community-encrypt / Go-decrypt cells will go red until upstream merges a
  reader fallback. This was chosen explicitly over gating writers behind a flag.
- **Readers accept both names, permanently.** Try `manifest.json` first, then
  `0.manifest.json`. Existing TDFs and golden files never stop working.
- **Payload entry name comes from `payload.url`.** Readers resolve it from the
  parsed manifest, falling back to `0.payload` only if `url` is empty. Writers
  use one constant for both the zip entry and `payload.url`.
- **Payload entry stays `0.payload`.** The spec allows any name; the user asked
  for derivation, not renaming.
- **Writers emit only `schemaVersion`, value `4.3.0`.** No `tdf_spec_version`
  is written in either placement. Go uses the absence of `schemaVersion` as its
  legacy hash-encoding switch at four sites in `sdk/tdf.go`, and every peer SDK
  and the harness key off it today.
- **Readers resolve the spec version with this priority:** `schemaVersion`,
  then top-level `tdf_spec_version`, then `payload.tdf_spec_version`. The first
  non-empty value wins. `schemaVersion` is first because it is what we and
  upstream write. The spec has placed `tdf_spec_version` top-level (prose, 2025
  overhaul) and under `payload` (JSON schema, 2024), so both are accepted as
  fallbacks. A manifest with none of the three is treated as legacy, as Go
  does today.
- **Spec self-contradictions are not resolved in code.** `sid`/`kid` required in
  the JSON schema but optional in prose; `method.iv` required in prose but
  absent from the JSON schema. Upstream spec PRs are backlog.
- **Out of scope:** Rust `N.manifest.json` multi-entry indexing beyond index 0,
  the Rust gguf profile, TDF-JSON / TDF-CBOR formats, NanoTDF.

## Design

### Phase 1: readers (all SDKs and harness)

Each SDK gets a single resolver with this contract:

```
resolve_manifest_entry(names) -> "manifest.json" if present
                                 else "0.manifest.json" if present
                                 else error
resolve_payload_entry(manifest, names) -> manifest.payload.url if non-empty and present
                                          else "0.payload" if present
                                          else error
```

Reject `payload.url` values containing `..`, a leading `/`, or `\`.

Remove entry-count assumptions: Python `is_tdf` no longer requires exactly two
entries; Rust `TdfArchive::len()` no longer divides by two.

Files:
- Python: `packages/otdf-python/src/otdf_python/tdf_reader.py` (constants, `:35-42`),
  `tdf.py:436,467,490,513`, `sdk.py:373-377`.
- Rust: `src/archive.rs:355-391` (`get_entry`), `:339-342` (`len`), `:364` error text.
- Swift: `OpenTDFKit/TDF/TDFArchive.swift:4-5,29,54,61,76,172,174`.
- Go: `sdk/internal/zipstream/tdf3_reader.go:43-62`; `ReadPayload`/`PayloadSize`
  take the name from the parsed manifest.
- Harness: `xtest/tdfs.py:441-515` (`manifest`, `update_manifest`,
  `update_payload`, `validate_manifest_schema`) go through the same resolver.

### Phase 2: writers (all SDKs)

- One constant per SDK, `TDF_MANIFEST_FILE_NAME = "manifest.json"`, and one
  `TDF_PAYLOAD_FILE_NAME = "0.payload"` that feeds both the zip entry and
  `payload.url`.
- `schemaVersion` stays the only version key written. Rust corrects its value
  from `"3.0.0"` to `"4.3.0"`.
- Each SDK gains a `spec_version()` accessor on the parsed manifest that applies
  the read priority above. Rust adds the top-level `tdf_spec_version` field
  (it already has the `payload` one); Python and Swift add both as optional,
  read-only fields that are never serialized when empty.

Files:
- Python: `tdf_writer.py:11-12`, `tdf.py:402,408`, `manifest.py:115,152-153,231`.
- Rust: `src/archive.rs:427,434,455,462,507,514,533,540`,
  `crates/protocol/src/manifest.rs:19-24,244-254,275-276`, `src/tdf.rs:229`,
  `crates/wasm/src/lib.rs:118`, `examples/xtest_cli.rs:342-343`.
- Swift: `TDFArchive.swift:4-5`, `TDFProcessor.swift:167,279,367`,
  `TDFManifestBuilder.swift:48,88`, `TDFManifest.swift:5,23-63` (optional
  `tdf_spec_version` at top level and on the payload descriptor, decode-only),
  `CLAUDE.md:228`, `MIGRATION_GUIDE.md`.
- Go: `sdk/internal/zipstream/zip_headers.go:19`, `sdk/manifest.go:46-53,67`
  (optional `tdf_spec_version` fields with `omitempty`, never set on write),
  and the four `isLegacyTDF` sites in `sdk/tdf.go` (`:925,1020,1387,1489`) use
  the prioritized accessor instead of `TDFVersion == ""`.

### Phase 3: harness conformance

- New helper `tdfs.entry_names(path) -> list[str]`.
- New test `test_container_layout` in `xtest/test_tdfs.py`, marked `stage1`,
  parametrized on `encrypt_sdk`: asserts `manifest.json` is present at the
  root and `payload.url` names an existing entry. Skipped for SDKs that do not
  claim a new `spec-container` feature in their `cli.sh supports`, so upstream
  Go/Java/JS skip rather than fail.
- `xtest/manifest.schema.json` is unchanged.

### Testing

Each SDK:
- Reader unit tests: open a fixture with `manifest.json` + `payload.url = "0.payload"`;
  open a fixture with `0.manifest.json` (legacy); open a fixture whose
  `payload.url` is `"data.bin"` and the entry is named `data.bin`; reject a
  fixture whose `payload.url` is `../x`.
- Writer unit tests: written archive has entries `manifest.json` and `0.payload`;
  manifest `payload.url` equals the payload entry name; `schemaVersion == "4.3.0"`;
  no `tdf_spec_version` key is present at either placement.
- Version-resolution unit tests: a manifest with all three keys resolves to
  `schemaVersion`; with only the two `tdf_spec_version` placements, resolves to
  the top-level one; with only `payload.tdf_spec_version`, resolves to it; with
  none, resolves to empty (legacy).
- Update existing tests that assert `0.manifest.json` (listed per SDK in the
  audit: Python `tests/test_tdf_writer.py`, `test_tdf.py`, `test_tdf_reader.py`,
  `test_tdf_key_management.py`, `test_manifest*.py`, integration tests; Rust
  `tests/integration.rs:85-106,194`, `src/archive.rs:570-673`,
  `src/manifest.rs:214-262`, `crates/protocol/src/manifest.rs:336-393`; Swift
  `OpenTDFKitTests/TDFTests.swift:305,332,215-216`; Go
  `sdk/internal/zipstream/segment_writer_test.go:69,149,220,280`,
  `sdk/tdf_test.go:1503,1522,1548`).
- Binary fixtures with `0.manifest.json` (Rust `tests/data/sensitive.txt.tdf`,
  harness `xtest/golden/*.tdf`) are kept as legacy-read tests, not regenerated.

Cross-SDK: run the harness stage-1 matrix locally for python, rust, swift
in both directions. Expect green among community SDKs and red only for
community-encrypt / upstream-Go-decrypt cells.

### Error handling

- Missing both manifest names: error message names both candidates.
- `payload.url` names a missing entry: error message quotes the URL.
- Unsafe `payload.url`: reject before any zip lookup.

## Backlog (found by audit, not in this change)

- Integrity verification on decrypt is absent in Swift and Python (spec: MUST abort on failure).
- Rust `KeyAccess` has no `sid`; `TdfManifest` has no `assertions`. Both silently drop on read.
- Python assertion field is `appliesTo_state`; spec is `appliesToState`.
- Swift `StatementFormat.binary` should be `base64binary`; `PayloadProtocol` lacks `zipstream`.
- Go `Statement.value` re-encodes JSON objects as strings on round-trip, changing the JCS hash.
- `method.iv` is `""` in every SDK; needs a spec decision, not an SDK change.
- `policyBinding.hash` is `base64(hex(HMAC))` in every SDK; spec prose says `base64(HMAC)`. Spec doc fix.
- `ec-wrapped`, `keyAccess.schemaVersion`, `keyAccess.ephemeralPublicKey` are unregistered in the spec.
- Upstream spec PRs: reconcile `tdf_spec_version` placement between prose and JSON schema, `sid`/`kid` optionality, `method.iv` in JSON schema.
- Upstream platform PR: reader fallback to `manifest.json` and `payload.url` resolution.
- Fork drift in opentdf-platform: `SupportedFeatures()` removed (harness silently skips dpop/connectrpc tests).
- Untracked `platform` symlink at the harness repo root should be gitignored.
