# Scenario YAML templates

The canonical field list (titles, types, defaults, `anyOf` branches) lives in `xtest/schema/scenario.schema.json`. Read it whenever a question about an allowed field arises. Each pin (`PlatformPin`, `KasPin`) requires **exactly one** of `dist:`, `source:`, or `image:`. `image:` is reserved for forward-compat and is rejected today — pick `dist:` or `source:`.

## Released-version pin (typical Bug scenario)

Use when reproducing a bug on a published release.

```yaml
apiVersion: opentdf.io/v1alpha1
kind: Scenario
metadata:
  id: <jira-key-lowercased>
  title: "<Jira summary>"
  created: <YYYY-MM-DD>
instance:
  metadata: { name: <jira-key-lowercased> }
  platform: { dist: v0.9.0 }
  ports: { base: <free base; 8080 if first, +1000 per concurrent scenario> }
  kas:
    alpha: { dist: v0.9.0, mode: standard }
sdks:
  encrypt:
    go: { version: lts }
  decrypt:
    java: { version: "0.7.8" }
suite:
  select: "xtest/test_tdfs.py::test_tdf_roundtrip"
  containers: ztdf
expected: "..."
actual:   "..."
```

## Ref pin (TDD / HEAD / branch / PR)

Use when the behavior under test lives on an unreleased branch, an in-flight PR, or HEAD. For PRs, prefer the 40-char `headRefOid` from `gh pr view <N> --json headRefOid` over the branch name — SHAs are immutable, branches move.

```yaml
instance:
  platform:
    source: { ref: main }                  # branch, tag, 40-char SHA, or pr:N
  kas:
    alpha:
      source: { ref: feature/ecdsa-binding }
      mode: standard
sdks:
  encrypt:
    go: { version: main }                  # SdkPin.version accepts the same range of strings
```

## Mixed-mode (platform on a ref, KAS on a release)

Use when validating that an unreleased platform interoperates with shipped KAS deployments (or vice versa).

```yaml
instance:
  platform:
    source: { ref: pr:3537 }               # in-flight PR
  kas:
    alpha: { dist: v0.9.0, mode: standard } # shipped KAS
    km1:
      source: { ref: pr:3537 }              # KAS that needs PR changes
      mode: key_management
sdks:
  encrypt: { go: { version: main } }
  decrypt: { go: { version: lts } }        # old client decrypting new platform output
```

## PR pin via Jira link (recommended for Story/Task tickets)

When `acli jira workitem link list <KEY>` returned a linked PR (URL like `github.com/opentdf/platform/pull/<N>`), resolve and pin to the head SHA:

```bash
gh pr view <N> --repo opentdf/platform --json number,headRefName,headRefOid
# → { "number": 3537, "headRefName": "DSPX-3383-post-quantum-kem", "headRefOid": "08ab3a0a…" }
```

Then in the scenario:

```yaml
metadata:
  title: "<Jira summary> [opentdf/platform#3537 @ DSPX-3383-post-quantum-kem]"
instance:
  platform:
    source: { ref: 08ab3a0a... }            # immutable 40-char SHA
```

Record the branch name in `metadata.title` for human readability; the SHA is what `otdf-sdk-mgr install` uses.

## Validation

Always validate before reporting success:

```bash
uv run python -m otdf_sdk_mgr.schema validate xtest/scenarios/<id>.yaml
```
