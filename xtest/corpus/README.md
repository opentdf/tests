# TDF corpus

A flat directory of static TDF fixtures. Each fixture `<fixture>` has a sidecar
`<fixture>.expect.toml` beside it. The sidecars are read both by the xtest corpus tests and by
external TDF validators.

## Prefixes

| Prefix | Group |
|--------|-------|
| `golden-` | Files written by released Java SDKs, DSP 2.0.2 to 2.0.6 and DSP Gateway 2.79.0, plus other small Java goldens. Each is decryptable with the KAS key `golden-r1` (`xtest/extra-keys.json`). |
| `sdk-` | Files produced by the current SDK builds under test. |
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

An optional `[sdk]` table records how each SDK is expected to handle the file. Golden sidecars
carry no `[sdk]` table. The table has these keys:

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
