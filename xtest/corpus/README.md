# TDF corpus

A flat directory of static TDF fixtures. Each fixture `<fixture>` has a sidecar
`<fixture>.expect.toml` beside it. The sidecars are read both by the xtest corpus tests and by
external TDF validators.

## Prefixes

| Prefix | Group |
|--------|-------|
| `golden-` | Files written by released Java SDKs, DSP 2.0.2 to 2.0.6 and DSP Gateway 2.79.0, plus other small Java goldens. Each is decryptable with the KAS key `golden-r1` (`xtest/extra-keys.json`). |
| `sdk-` | Files written by the generator's pinned writer builds; each sidecar's comments name the build. |
| `tamper-` | Real SDK files with one deliberate change each (policy, binding, root signature, segment hash, payload bytes, assertion, KAS URL, ZIP compression, ...). |
| `zip-legal-` | Files whose ZIP container takes an unusual but spec-legal shape. |
| `zip-adversarial-` | Files whose ZIP container contradicts itself. |
| `synthetic-` | Hand-built files that no SDK writes. |

## Sidecar schema

Top-level keys, all read by the validator:

- `expect`: the validator's verdict for the file.
- `format`: the container format (for example `"tdf"`).
- `strict`: run the validator with `--strict`.
- `must_contain`: finding codes that must be reported.
- `must_not_contain`: finding codes that must not be reported.
- `note`: one-line description of the fixture.
- `verify_crypto`: run the offline cryptographic checks.
- `key`: path to the DEK file, for example `key = "keys/golden-<name>.dek"`.
- `share_keys`: key shares for split TDFs, for example `["<split-id>=keys/<file>", ...]`.
- `assertion_keys`: public keys for assertion signature checks, each either `"keys/<file>"` or
  `"<id>=keys/<file>"`.

All key paths are relative to this directory. In `share_keys` the id and the path must both be
non-empty. In `assertion_keys` the id is optional, but when present it must be non-empty.

Every sidecar except the goldens ends with an `[sdk]` table recording how each SDK is expected
to handle the file; golden sidecars carry none. The units check enforces both. The table has
these keys:

- `go`, `java`, `js` (all three required): the expected outcome, `"decrypt"` or `"reject"`, or a
  list of entries `{ verdict = ..., since = ..., before = ..., platform_since = ...,
  platform_before = ... }` where the bounds are optional semver strings of the exact form
  `X.Y.Z` or `vX.Y.Z`. The first matching entry wins, `since` is inclusive and `before` is
  exclusive. Only the last entry may be unbounded, and it must be.
- `plaintext_sha256`: SHA-256 of the expected plaintext, as 64 lowercase hex characters. Required
  when any entry for any SDK is `"decrypt"`, whether given as a bare verdict or inside a list.
- `note`: free text.

`[sdk]` is the only table a sidecar may contain, and it must come last, after all top-level keys.
Any other table, and any unknown key, is rejected by `corpus.load_sidecar`.

## keys/

`keys/` holds validator inputs: the DEK files that `key` points at (hex text, one line), and any
other key material a sidecar names.

## kas-keys.json

`kas-keys.json` holds the 8 KAS key pairs the `sdk-`, `tamper-` and `zip-` fixtures are
encrypted to. Each entry has a `kid`, an `alg`, the `privateKey`, the public `cert`, and a `kas`
field naming the KAS instance that serves it (`km1` or `km2`).

The private keys are published on purpose. They exist only for these tests and protect nothing
else; never reuse them.

Regenerating them (`go -C corpus_gen/dek run . keygen --alg …`, from `xtest/`) invalidates every
fixture: each would have to be written again.

`-m corpus` imports these keys into whatever platform `PLATFORMURL` names, so run it only
against a local or CI platform.

## Regenerating

Every file except the goldens, `kas-keys.json` and this README comes from the generator in
`xtest/corpus_gen`. It is run by hand when the corpus needs refreshing, never in CI.

Prerequisites:

- The platform with the km1 (`http://localhost:8585`) and km2 (`http://localhost:8686`) KAS
  instances, as `otdf-local up` starts them, and `OT_ROOT_KEY` set to the platform's root key.
- SDK builds in `xtest/sdk/{go,java,js}/dist/main` (`otdf-sdk-mgr install tip`), plus Go, Node
  and a JDK 21 on `JAVA_HOME` for the writers.

From `xtest/`:

```bash
uv run python -m corpus_gen write     # sdk-* fixtures and tamper bases (needs the platform)
uv run python -m corpus_gen deks      # unwrap and verify every DEK; write the key files
uv run python -m corpus_gen derive    # tamper-* and zip-* from the bases
uv run python -m corpus_gen sidecars  # synthetic-* copies and every sidecar
uv run python -m corpus_gen install   # copy the stage into xtest/corpus
# record-mode dry run on each platform (below), then:
uv run python -m corpus_gen verdicts tmp/rec-*.jsonl  # every [sdk] table
```

To check one writer before a full `write`, `uv run python -m corpus_gen.selfcheck --sdk go` (or
`java`, `js`) writes three TDFs to the corpus keys on km1 and decrypts them with the same SDK.

Every step but `install` and `verdicts` writes to a staging directory, `$XT_TMP_DIR/corpus_gen`
(default `xtest/tmp/corpus_gen`). `sidecars` keeps the validator fields of the sidecars already
here, and their `[sdk]` tables unchanged (`--from DIR` reads them from another corpus, which must hold every previous sidecar and the
synthetic-* files). It rebuilds
the key references from the staged key files and writes fresh comments. The Go and Java SDKs pick
random split ids, so share file names change with each `write`.

`install` refuses, changing nothing, if a fixture is missing or has no sidecar, if a referenced key
file is missing or absolute, or if a key file or derived fixture is older than the file it came
from. It replaces the generated files here only once every new file has been copied in, and leaves
everything else alone.

### Recording the `[sdk]` tables

The `[sdk]` tables come from a dry run of the corpus tests in record mode. Run it once for each
platform version that CI tests (today `main` and `v0.31.0`), each time with that platform and
km1/km2 up, and write one record file per platform. Use the SDK builds CI tests: the `main`
builds from the prerequisites, plus the releases, which `otdf-sdk-mgr install release
go:v0.41.0 js:0.23.0` installs. Then run `verdicts` on the record files:

```bash
# Once per platform (here main), from xtest/:
export OTDF_LOCAL_PLATFORM_DIR="$PWD/platform/src/main"  # the checkout otdf-local runs
eval "$(cd ../otdf-local && uv run otdf-local env)"      # log paths, PLATFORM_DIR, OT_ROOT_KEY
set -a; source test.env; set +a
export PLATFORM_VERSION="$(cd "$PLATFORM_DIR" && go run ./service version 2>&1 | tail -n 1)"
export PLATFORM_TAG=main
rm -f tmp/rec-main.jsonl
uv run pytest test_corpus.py -n auto --dist loadscope \
  --sdks-decrypt "go@main go@v0.41.0 java@main js@main js@v0.23.0" \
  --corpus-record tmp/rec-main.jsonl
# Then, offline:
uv run python -m corpus_gen verdicts tmp/rec-*.jsonl
```

`otdf-local env` provides the log paths the audit-log checks read, and `OT_ROOT_KEY`; without
it, set `OT_ROOT_KEY` from `yq e '.services.kas.root_key' "$PLATFORM_DIR/opentdf-dev.yaml"`.
`service version` prints to stderr, hence the `2>&1`. An unset `PLATFORM_VERSION` counts as
0.9.0, which turns off every `mechanism-*` feature: every SDK then skips the ML-KEM and hybrid
fixtures, and `verdicts` refuses.

In record mode each build decrypts every non-golden fixture it has the capabilities for, and each
cell passes whatever the outcome. `verdicts` then writes one `[sdk]` table per sidecar, appended
after its other lines, which stay as they are. An earlier table is replaced. The same table goes
into the sidecar's staged copy too, when there is one, so a later `install` keeps it. For each SDK:

- If every recorded cell agrees, it writes that verdict.
- If the SDK's `main` build differs from its release build on both platforms, it writes a list
  that gives the release outcome `before` the next minor version and the `main` outcome after it.
- If the cells disagree in any other way, it keeps the SDK's entry from the earlier table, as
  written, provided that entry gives every recorded cell. To record such a case, write the list
  by hand under the SDK's key in that sidecar's `[sdk]` table, and re-run `verdicts`.
- An SDK with no cells (a decrypt skipped because the SDK lacks a capability the file needs)
  gets the outcome every other SDK's cells share, and a `note` saying why it was skipped,
  provided it has no cells for any other fixture that needs that capability.

`verdicts` refuses, writing nothing, if cells disagree and no earlier entry gives them all, if
the SDKs that ran disagree about a fixture another SDK skipped, if no SDK has cells for a fixture
(which points at the platform or the env, not the SDKs), if a decrypt's output is not the
generator's plaintext, if a synthetic file decrypts at all, if an SDK has no cells for a fixture
although it has cells for other fixtures needing the same capabilities, or if a staged fixture
differs from the corpus fixture that was recorded. Its output lists the disagreeing cells.

`plaintext_sha256` is the generator's plaintext digest, read from the staging directory's
`manifest.json`. A `tamper-` or `zip-` file takes its base's digest. When that scratch is gone, or
its manifest lacks the fixture, `verdicts` keeps the digest from the sidecar's existing `[sdk]`
table, and refuses if a fixture some SDK decrypts has neither. Synthetic files have no known
plaintext, so it is omitted for them.

The per-fixture records are not committed; only the `[sdk]` tables are.

## When a corpus cell goes red

A failing `test_corpus_fixture` cell means an SDK build handled a fixture differently from what
its sidecar's `[sdk]` table records. The failure names the sidecar and shows the decrypt's stderr.
A cell that decrypts also requires a successful rewrap audit event for the fixture's policy UUID.
If only that check fails, look at KAS audit logging, not at the verdict.

- **A real SDK behaviour change**, such as a fix that now rejects a tampered file: update that
  SDK's entry. Either re-record (the dry run above) and re-run `verdicts`, or edit the entry by
  hand. Where the cells disagree in a way `verdicts` cannot express, it keeps a hand-written list
  that gives every recorded cell, so a later run does not undo it.
- **Bounding by version**: a list keeps older builds on their old outcome, for example
  `js = [{ verdict = "decrypt", before = "0.24.0" }, { verdict = "reject" }]`. `since` and
  `before` bound the SDK's version, `platform_since` and `platform_before` the platform's.
  A build with no release version counts as newer than every bound: it matches `since` but never
  `before`.
- **Branch builds**: SDK `main` and an SDK PR branch are both branch builds, so both resolve to
  the same entry and no bound tells them apart. A PR that changes behaviour therefore updates
  the sidecar in the same change, or the opentdf/tests side lands first. Once a release carries
  the change, bound the old outcome `before` that release.

## Golden notice

The goldens are distributed under the Clear BSD License:

> Copyright (c) 2021-2022 Virtru Corporation. All rights reserved.
>
> Redistribution and use in source and binary forms, with or without modification, are permitted
> (subject to the limitations in the disclaimer below) provided that the following conditions are
> met:
>
> - Redistributions of source code must retain the above copyright notice, this list of
>   conditions and the following disclaimer.
> - Redistributions in binary form must reproduce the above copyright notice, this list of
>   conditions and the following disclaimer in the documentation and/or other materials provided
>   with the distribution.
> - Neither the name of Virtru Corporation nor the names of its contributors may be used to
>   endorse or promote products derived from this software without specific prior written
>   permission.
>
> NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS LICENSE. THIS
> SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
> WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
> FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
> LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
> (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
> PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
> CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
> THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
