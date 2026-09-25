# ZIP conformance comparison

The structural cases in `xtest/test_zip_conformance.py` compare SDK readers
using small, authenticated TDFs whose ZIP metadata is rewritten after
JS encryption. Payload and local-header bytes are preserved. Ordinary
rebuilt entries declare extraction version 2.0; entries using ZIP64 declare
4.5. The separate `test_zip64.py` exercises actual writer size thresholds.

## Coverage and assertions

- Independent ZIP64 EOCD count, size, and offset sentinels, with all other
  values truthful: require byte-identical decryption. The size-only case is
  compatibility coverage, since a reader ignoring directory size can pass it.
- All seven combinations of per-entry compressed-size, uncompressed-size,
  and local-header-offset sentinels, under both ZIP32 and ZIP64 EOCDs:
  require byte-identical decryption. A foreign extra-field TLV precedes ZIP64.
- A comment on the first directory entry: require decryption of the complete
  TDF, including the following manifest entry.
- Truncated ZIP64 values, oversized extra-field declarations, invalid stored
  sizes, invalid local-header/locator/directory offsets, and impossible entry
  counts: require a recognized parser rejection. Each case first decrypts
  an unmodified control. Panics, signals, allocation/runtime failures,
  timeouts, unrelated errors, and successful decryption fail the assertion.
- Directory records of 65,535 and 65,536 bytes, using ordinary filenames and
  a large foreign extra field: require decryption at the first boundary;
  permit either faithful decryption or recognized rejection above it.
  APPNOTE 4.4.10-12 recommends keeping the combined record length within
  65,535 bytes, so universal acceptance above that limit is not required.

Malformed decrypts have a 30-second deadline, with process-group cleanup so
CLI shim children cannot survive a timeout. Positive out-of-range values
are only a few KiB beyond the fixture; the signed-conversion case uses
`2**63`, and the impossible count uses `2**64 - 1`.

A successful decrypt of malformed metadata demonstrates a missing check
under this rejection contract; it does not establish plaintext corruption.
Similarly, a generic rejection may predate a fix and does not prove that
one particular internal guard ran.

## Revisions tested on 2026-09-24

The SDKs were built with `otdf-sdk-mgr`. The main platform, Keycloak, and
Postgres were run by `otdf-local`; extra KAS instances were unnecessary.
Java used JDK 21. SDK changes were isolated from the unchanged platform.

| Component | Ref | Commit |
| --- | --- | --- |
| Platform and Go control | main | `e5ee6991dca1efa13bdb972f030090d638dffca9` |
| Go pre-3981 control | otdfctl/v0.37.0 | `b78901a38c0d23af78e25b87d1a489b20bc1c926` |
| Go 3981 fix | refs/pull/3981/head | `38472ff71868f04d23db8b23ff0c7535555b0cd5` |
| Go 4043 fix | refs/pull/4043/head | `109c270e830837291726c751b25954080c9a9f07` |
| Java control | main | `6486b3f9056f2058fb0f994f874035d0a4bf8a57` |
| JS control / small-fixture producer | main | `d1859afd0da91a8840799ee7eb4ee7f3c78fa641` |
| JS 1017 fix | refs/pull/1017/head | `d9342191f8bf3f5818fd1bef3e66d5b8bfffdcd7` |

## Results

The full mutation matrix ran **266 cells: 213 passed, 53 failed, zero skipped**.
Failures are intentionally visible: no expected-failure markers or feature
skips hide the control regressions or other SDK validation gaps. Counts below
are **passed / failed**.

| Decryptor | Added valid layouts (18) | Added malformed inputs (12) | Added record boundaries (2) | Original cases (6) |
| --- | --- | --- | --- | --- |
| Go v0.37.0 | 4 / 14 | 11 / 1 | 2 / 0 | 2 / 4 |
| Go PR 3981 | 18 / 0 | 9 / 3 | 2 / 0 | 3 / 3 |
| Go main | 18 / 0 | 10 / 2 | 2 / 0 | 3 / 3 |
| Go PR 4043 | 18 / 0 | 12 / 0 | 2 / 0 | 3 / 3 |
| Java main | 18 / 0 | 6 / 6 | 2 / 0 | 6 / 0 |
| JS main | 18 / 0 | 4 / 8 | 1 / 1 | 4 / 2 |
| JS PR 1017 | 18 / 0 | 9 / 3 | 2 / 0 | 6 / 0 |

The committed code was also rerun against Go PR 4043 alone: **all 32 added
cases passed**. The offline suites (`test_zip_conformance_units.py` and
`test_zip64_units.py`) passed **112 tests**, including real child-process
cleanup on timeout. Ruff lint/format and Pyright passed.

### Evidence distinguishing the fixes

- [Platform PR 3981](https://github.com/opentdf/platform/pull/3981): the old
  release fails count-only EOCD detection, 12 per-entry sentinel combinations,
  and traversal past a directory-entry comment. The PR passes all 18 layouts.
  The existing 2.1 GiB writer test adds **3 control failures / 3 fixed passes**:
  the old writer leaves raw values in the 2–4 GiB band; the PR emits ZIP64 and
  its output decrypts byte-for-byte with Go PR 4043, Java main, and JS main.
- [Platform PR 4043](https://github.com/opentdf/platform/pull/4043): main
  panics on the `2**63` manifest stored size and successfully decrypts despite
  the payload's declared range extending into the central directory. The PR
  rejects both with format errors. The remaining malformed cases mostly
  already reject on main, and provide robustness coverage rather than proof
  of each new internal guard.
- [Web SDK PR 1017](https://github.com/opentdf/web-sdk/pull/1017): resolves
  JS main's failure on the valid 65,535-byte directory record and its acceptance
  of invalid ZIP64 locator/directory offsets and the impossible entry count.
  It also passes all six original cases, including archive comments.

### Remaining failures

Go PR 3981 also panics on the signed-size fixture, accepts directory overlap,
and reports a downstream JSON parse error for a manifest size past EOF.
The latter does not meet the test's requirement for a recognizable ZIP
rejection. Main already improves that third behavior; PR 4043 passes all
three. The old release avoids the signed-size panic because it does not
resolve the per-entry ZIP64 field under the ordinary EOCD and rejects the
raw size sentinel via its manifest-size cap instead.

Java main accepts an oversized extra-field declaration, both invalid manifest
sizes, and payload overlap. The signed locator and directory offsets produce
opaque `IllegalArgumentException` failures, rather than recognized ZIP errors.

JS main and PR 1017 both accept the manifest size past EOF and payload overlap.
Both reach `JSON.parse` with an empty manifest for a local-header offset past
EOF, producing `SyntaxError: Unexpected end of JSON input` rather than a ZIP
rejection. These are the **three remaining failures on PR 1017**.

All Go builds retain three original archive-comment failures. The old Go
release additionally fails the original foreign-TLV/offset-only case. JS main
retains two original maximum-comment failures. These are separate from the
newly demonstrated platform fixes.

Raw XML, HTML, and logs are local ignored artifacts under
`xtest/test-results/`: `zip-final.*`, `zip-fixed-current.*`, and
`zip-writer-comparison.*`. `zip-comparison-summary.json` records per-SDK
counts and failing cases. The local platform and database services were
healthy after the runs and remain available for debugging.

## Reproduction

From `otdf-sdk-mgr/`, install source builds with these commands. Set
`JAVA_HOME` to JDK 21 for the Java build and test runs.

```sh
uv run otdf-sdk-mgr install tip --ref main platform go js java
uv run otdf-sdk-mgr install tip --ref otdfctl/v0.37.0 go
uv run otdf-sdk-mgr install tip --ref pr:3981 go
uv run otdf-sdk-mgr install tip --ref pr:4043 go
uv run otdf-sdk-mgr install tip --ref pr:1017 js
```

Refs may move; the table records the exact commits used for this comparison.
With the platform configuration and keys provisioned as described in the
`otdf-local` guide, select the installed main checkout. From the repo root:

```sh
export OTDF_LOCAL_PLATFORM_DIR="$PWD/xtest/platform/src/main"
export OTDF_LOCAL_XTEST_ROOT="$PWD/xtest"
export COMPOSE_PROJECT_NAME=opentdf-zip-conformance
(cd otdf-local && uv run otdf-local up --services docker,platform)
```

Then run from `xtest/` with the environment for that same instance:

```sh
set -a
source test.env
set +a
eval "$(cd ../otdf-local && uv run otdf-local env)"
uv run pytest test_zip_conformance.py --sdks-encrypt js@main \
  --sdks-decrypt 'go@v0.37.0 go@refs--pull--3981--head go@main go@refs--pull--4043--head java@main js@main js@refs--pull--1017--head' \
  --junitxml=test-results/zip-final.xml
```

Every cell passes whether the reader accepted the mutated container or
rejected it cleanly, so read the `zip conformance outcomes` table printed at
the end of the run (also written to `test-results/zip-conformance.json`) for
which refs were conformant and which were merely safe.

To isolate the 32 added cases, append
`-k 'independent_sentinel or entry_comment or malformed_zip or record_length_boundary'`.
The complete module also runs six pre-existing cases, including the known
archive-comment failures.

For the actual 2.1 GiB writer threshold, run:

```sh
XT_FORCE_SUPPORTS=zip64-at-2gib uv run pytest test_zip64.py --sizes medium \
  --sdks-encrypt 'go@v0.37.0 go@refs--pull--3981--head' \
  --sdks-decrypt 'go@refs--pull--4043--head java@main js@main' \
  --junitxml=test-results/zip-writer-comparison.xml
```

The override deliberately enables the writer assertion for both versions:
this repo's Go CLI feature gate still reports the unreleased behavior as
unsupported. The control should fail that assertion, rather than silently
omitting it. No feature override is needed for the small structural tests.

## Coverage kept in SDK unit tests

Distinct compressed/uncompressed values cannot be distinguished with valid
STORED TDF entries, whose sizes are equal. Go's direct parser tests retain
that check, as well as strict directory-cursor overflow assertions, injected
writer thresholds/narrowing guards, hostile `ReadSeeker` behavior, and
caller-supplied negative or out-of-range subreads. The CLI tests do not claim
complete coverage of those internal APIs.
