---
ticket: DSPX-5349
title: "xtest: cross-SDK 'is valid TDF' validation suite (go, java, js)"
status: draft
authors: [dmihalcik@virtru.com]
branches: [opentdf/tests:DSPX-5349-xtest-tdf-validity-suite]
prs: [opentdf/tests#677]
created: 2026-10-23
updated: 2026-10-23
---

# TDF validity: one question, every SDK

## Summary

`xtest/test_tdf_validity.py` asks each SDK's `validate` command the same
question about the same bytes: *is this a valid TDF?* The answers are held to
one checked-in baseline, `xtest/tdfvalidity_baseline.json`. Any difference
from it fails the run, in either direction: a validator that grows more
lenient fails, and so does a known divergence that quietly stops reproducing.

It replaces per-SDK copies of the same fixtures (web-sdk#1104 alone carried
48 archives and a Go verifier script). Those copies are how the SDKs drifted
apart; see the divergence table in DSPX-5348.

## What "valid" means

The agreed answer, until the decisions listed below change it, is what Go's
`sdk.IsValidTdf` was meant to check:

1. **Archive.** The file is a ZIP archive whose end records and central
   directory are truthful and lie within the file. Entries are STORED, with
   equal compressed and uncompressed sizes (DSPX-4924 calls this the TDF
   container profile; DSPX-5354 is Go not enforcing it).
2. **Manifest entry.** `manifest.json` (the spec's name) if present,
   otherwise `0.manifest.json`. If `manifest.json` is present and broken,
   there is no fallback. Names are exact and case sensitive.
3. **Manifest bytes.** Exactly one JSON value, an object, with no byte-order
   mark and nothing after it but whitespace.
4. **Manifest content.** The object passes the *lax* manifest schema,
   `xtest/manifest-lax.schema.json`, vendored verbatim from platform/sdk
   v0.35.0 (web-sdk#1104 vendors the same file). One known exception:
   `mlkem-wrapped` key access objects are valid even though the schema omits
   them (DSPX-4388).

Not checked by any validity API, and therefore pinned rather than judged
(`scope/` cases): payload bytes, payload length against the manifest's
segments, and entry CRCs.

Note that "valid" is stricter than "readable": `golden/xstext-java-v0.7.5-*`,
written by java-sdk v0.7.5, omits `method.isStreamable`, so the lax schema
rejects it, while every SDK still decrypts it (`test_legacy.py`).

## The CLI contract

Every SDK exposes a top-level, offline `validate` command, and its `cli.sh`
shim passes stdout and the exit status through unchanged:

| SDK | command | ticket |
| --- | --- | --- |
| go | `otdfctl validate <file>` | DSPX-5350, opentdf/platform#4254 |
| js | `opentdf validate <file>` (`@opentdf/ctl`) | DSPX-5351, opentdf/web-sdk#1119 |
| java | `java -jar cmdline.jar validate <file>` | DSPX-5352 |

- stdout is exactly one JSON line: `{"valid":true}` or
  `{"valid":false,"reason":"..."}`.
- **exit 0**: valid. **exit 3**: the check completed and the file is not a
  valid TDF. **Any other exit, a signal, or a timeout**: the check could not
  run (missing file, usage error, crash).
- No platform connection, profile or credentials.

Why 3 and not 1: cobra, Node and picocli all exit 1 on an unhandled error, and
picocli exits 2 on a usage error. With 1 meaning "invalid", a crash would be
indistinguishable from a verdict. This supersedes the "exit 1 = invalid"
wording in DSPX-5349 to DSPX-5352.

`tdfvalidity.parse_output` is strict: an exit of 0 or 3 is a verdict only if
stdout agrees with it, as exactly one JSON object. Anything else is an
`error`, which fails the cell unless the baseline pins that error with a
ticket. `SDK.validate` runs the shim in its own process group with a timeout
(`XT_VALIDATE_TIMEOUT`, default 60 s) and kills the whole group on expiry,
so a hang is reported rather than wedging the run.

Support is detected per build: `cli.sh supports tdf_validity` looks for the
`validate` command in the CLI's help (`help validate` for go and java, the
command list for js), so released CLIs that predate it skip through the
feature gate. `XT_FORCE_SUPPORTS=tdf_validity` overrides that, as for any
feature.

## The corpus

`xtest/tdfvalidity_corpus.py` builds every static case in Python, once, so
every SDK reads the same bytes. The ZIP writer there is deliberately not
`zipfile`: most cases are archives `zipfile` refuses to write.

| group | cases | what it pins |
| --- | --- | --- |
| `control/` | 2 | unremarkable TDFs |
| `archive/` | 10 | writer layouts (data descriptors, ZIP64) and the archive divergences |
| `truncated/` | 32 | the control archives cut at every structural boundary |
| `zip/` | 14 | malformed archives: empty, random, lying offsets and counts |
| `profile/` | 10 | legal ZIP, questionable TDF: extra, missing, duplicated, reordered entries |
| `name/` | 8 | which manifest entry a reader picks |
| `json/` | 14 | manifest bytes that are not one clean JSON object |
| `manifest/` | 42 | web-sdk#1104's lax-schema cases, ported |
| `schema/` | 84 | one keyword of the lax schema at a time, generated from the schema |
| `writer/` | 5 | realistic go, js, hybrid and ML-KEM manifests |
| `golden/` | 11 | Go's unit-test fixtures and `xtest/golden`'s small java files |
| `scope/` | 4 | payload damage no validity API checks |

**Mutation analysis.** The `schema/` cases exist because web-sdk#1104's 42
cases leave most of the schema undecided: dropping a keyword (for instance
`wrapped` from the key access type enum) changed no verdict. Against the
single-keyword mutants `test_tdf_validity_units.py` generates (171 of them),
the 42 cases leave 105 alive; the full corpus kills all but the 11 that no
input can distinguish (the `required` list beside `keyAccess/items`, which
JSON Schema ignores on an array; `type` under an all-string enum; and the
bare-description `payload.protocol`). The unit test fails if any other
mutant survives.

**Round trips** (`roundtrip/`) come from the SDKs at run time: every encrypt
SDK's output must be valid to every validator, for RSA-wrapped, EC-wrapped,
4.2.2-format, with an assertion, with a duplicated key access object, and with
managed X-Wing, secp256r1+ML-KEM and pure ML-KEM keys. The PQ shapes need the
key-management KAS (km1), so CI runs them (marker `tdf_validity_pqc`) in a
separate step after it starts. ZIP64 is covered structurally by
`archive/zip64` and by every web-sdk-written file, which is ZIP64 whatever
its size; a >4 GiB round trip is not run here.

## Classification

Each case has an **agreed answer** (`Case.expect`):

- `valid` / `invalid`: what every SDK should say.
- `undecided`: a decision ticket is open; each SDK's current answer is pinned.
- `unspecified`: outside what any validity API promises; pinned, no ticket.

Invalid cases also name the **layer** a rejection belongs to (`archive`,
`manifest-missing`, `manifest-json`, `manifest-schema`). A reader can reject at
the wrong layer -- an "entry count is not 2" check never exercises the
directory walk (DSPX-4924) -- so where an SDK reports reasons, the baseline
holds its `reason_patterns` per layer and a mismatch fails the cell.

The **baseline** records only what differs from the agreed answer, and every
such cell carries the ticket that explains it, plus every seeded SDK's answer
to each undecided and unspecified case. A cell may also override the layer
(Go reads a deflated manifest as JSON instead of refusing the compression
method). `tdfvalidity.problems` enforces this, and runs in the offline unit
tests: a divergence without a ticket, a stale row, or a missing answer fails
`check.yml`.

Each judged cell is one of:

| status | meaning | fails? |
| --- | --- | --- |
| `match` | the answer the baseline expects | no |
| `drift` | a different answer, or the check could not run | yes |
| `reason` | the expected rejection, at the wrong layer | yes |
| `pending` | the SDK has no baseline yet (java) | no |

## Current results

Seeded from the libraries the CLIs wrap, run over this corpus:

- **go**: platform/sdk v0.35.0 `IsValidTdf`, which `otdfctl validate`
  (#4254) reports along with `err.Error()`. otdfctl on that branch requires
  sdk v0.35.0, and the validity code has not changed since.
- **js**: `validateTdf` from web-sdk#1119 (d293e509, stacked on #1118, #1117
  and #1104); its verdicts match #1104's `isValidTdf` on every case.
- **java**: pending. There is no `validate` command yet, and java-sdk's only
  API, `SDK.isTDF`, never parses the manifest (DSPX-5352).

Every case not listed here gets the agreed answer from both go and js:

| case | agreed | go | js | ticket |
| --- | --- | --- | --- | --- |
| `archive/comment`, `archive/comment-max` | undecided | invalid | valid | DSPX-5355 |
| `archive/deflated-payload` | invalid | valid | invalid | DSPX-5354 |
| `archive/deflated-manifest` | invalid | invalid (JSON layer) | invalid | DSPX-5354 |
| `archive/method-8-on-stored-bytes` | invalid | valid | invalid | DSPX-5354 |
| `archive/payload-size-mismatch` | invalid | valid | invalid | DSPX-5354 |
| `archive/cd-size-0xfffffff0` | invalid | valid | invalid | DSPX-5354 |
| `json/trailing-garbage`, `json/trailing-object` | invalid | valid | invalid | DSPX-5353 |
| `json/nesting-1000` | undecided | valid | valid | DSPX-5356 |
| `json/nesting-20000` | undecided | invalid | valid | DSPX-5356 |
| `writer/go-mlkem-wrapped`, `writer/js-mlkem-wrapped` | valid | invalid | invalid | DSPX-4388 |
| `roundtrip/mlkem-768` | valid | invalid | invalid | DSPX-4388 |
| `profile/*` (10 cases) | undecided | valid, unless the last duplicate manifest is invalid | same as go | DSPX-4924 |
| `json/duplicate-key` | unspecified | invalid | invalid | |
| `scope/*` (4 cases) | unspecified | valid | valid | |

DSPX-5357 (web-sdk resolving a duplicated manifest and payload to different
records) is a decrypt-path problem: validation never reads the payload, so
`profile/duplicate-pairs` cannot show it. The case is there for when DSPX-4924
decides whether duplicates are rejected outright.

Open decisions this suite is waiting on: archive comments (DSPX-5355), a
maximum JSON nesting depth (DSPX-5356, after which `json/nesting-*` move to
cases just under and over the limit), and the container profile (DSPX-4924).

## Running it

```bash
cd xtest
uv run pytest test_tdf_validity_units.py              # offline: corpus, parser, baseline
uv run pytest test_tdf_validity.py --sdks "go js" -k TestCorpus   # static corpus, no platform
uv run pytest test_tdf_validity.py --sdks "go js"     # plus round trips: needs a platform
```

Each run writes `test-results/tdf-validity.json` (`--tdf-validity-report`
moves it): per-build tallies, a case x build table, and every verdict.

## Refreshing the baseline

After a CLI changes behaviour on purpose, or once a ticket's fix lands:

```bash
cd xtest
uv run python tdfvalidity.py test-results/tdf-validity*.json
uv run pytest test_tdf_validity_units.py -k Baseline
```

`refresh` folds every non-matching verdict into the baseline and deletes cells
that now match the agreed answer, so a fixed divergence disappears. A new
disagreement is written without a ticket on purpose: the unit tests then fail
until someone files one and adds it. Verdicts that are `error`s are never
folded in.

**Seeding java**, once DSPX-5352 ships: run the suite with a java build that
has `validate` (`XT_FORCE_SUPPORTS=tdf_validity` if the gate lags), then

```bash
uv run python tdfvalidity.py test-results/tdf-validity*.json --seed java
```

which flips java from `pending` to `seeded` and records every answer that
differs from the agreed one. Then add tickets, and java `reason_patterns` once
its wording is known.

**Changing the corpus** changes what the baseline describes: add the case with
its agreed answer, run against each SDK, and refresh. Changing the vendored
schema (DSPX-4388 adding `mlkem-wrapped`) updates a digest pinned in the unit
tests, and should drop the DSPX-4388 cells once the CLIs pick it up.

## Known gaps

- java has no baseline until DSPX-5352 ships a `validate` command.
- Cells are keyed by SDK name, not version. Go v0.34.0 and earlier capped the
  manifest at 10 MiB (`json/large-11mib`), but no CLI that old has `validate`.
  A writer-specific round-trip answer can be pinned as `validator:writer`
  (`"go:java"`).
- `xtest/manifest.schema.json`, the strict schema `test_tdfs.py` checks writer
  output against, lists only `wrapped`, `remote` and `ec-wrapped` key access
  types (no `hybrid-wrapped` or `mlkem-wrapped`). Not touched here.
- Once this lands, web-sdk's in-repo parity corpus
  (`lib/tests/mocks/validation/`, `check-go.go`) can shrink to a smoke test
  (DSPX-5358).
