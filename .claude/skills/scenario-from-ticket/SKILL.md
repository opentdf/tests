---
name: scenario-from-ticket
description: Pull a Jira ticket of any type (Bug, Story, Task, Spike) into context via `acli jira workitem view` + `acli jira workitem comment list`, then turn it into an xtest/scenarios/<JIRA-KEY>.yaml manifest. Pins platform/KAS/SDKs to a released version (`dist:`), a branch or SHA (`source.ref:`), or the head of a PR — whichever matches the ticket. Optionally drafts xtest/bug_<jira_key>_test.py when no existing pytest covers the behavior. Use when the user mentions a Jira key like DSPX-1234 (or any [PROJECT]-[NUMBER]) and wants a runnable scenario — reproducing a bug, writing a TDD test for a new feature, or validating behavior at a specific ref.
allowed-tools: Bash, Read, Write, Grep, Glob
---

# scenario-from-ticket

You produce a `xtest/scenarios/<jira-key-lowercased>.yaml` manifest from a Jira ticket. The same skill handles bugs, features (TDD), and exploratory work — the *Issue Type* field on the ticket selects which way the rest of this skill behaves.

Two artifacts:

1. `xtest/scenarios/<jira-key-lowercased>.yaml` — validated against `otdf_sdk_mgr.schema.Scenario`.
2. (Optional) `xtest/bug_<jira_key_lowercased>_test.py` — only if no existing xtest pytest already exercises the behavior. The `bug_` prefix is a slug, not a type marker: feature-driven tests use it too.

The Jira key also becomes the working **branch name** (`<JIRA-KEY>-repro` for Bugs, `<JIRA-KEY>-tdd` for Stories/Tasks) and the scenario file's `metadata.id`.

## Step 1 — Pull the Jira ticket into context

**Always run BOTH commands** — exactly as shown; the two subcommands take the key differently (`view` is positional, `comment list` requires `--key`). Don't skip the comment list — comments often carry the most recent reproduction status, "what changed" notes, or "fixed by PR #N" pointers that aren't in the original description:

```bash
acli jira workitem view <JIRA-KEY> --fields '*all' --json
acli jira workitem comment list --key <JIRA-KEY>
```

From the JSON output of the first command, extract:

- **Issue Type** (Bug, Story, Task, Spike) — load-bearing; selects which Step 2 branch to follow.
- **Summary** — becomes scenario `metadata.title`.
- **Description** — version numbers, KAS topology, container types, feature flags, acceptance criteria typically live here.
- **Status** — Backlog / In Progress / Done affects whether the scenario is forward-looking (TDD on Backlog) or retroactive (regression gate on Done).

From the comments, pull any "tested at version X" / "reproduces on platform Y" / "fixed by PR #N" annotations into your mental model.

If the ticket references attached logs, screenshots, or linked PRs, list them via `acli jira workitem attachment list <JIRA-KEY>` and `acli jira workitem link list <JIRA-KEY>` and call them out in your reply.

**Permitted Jira writes**: only `acli jira workitem comment create <JIRA-KEY> ...` (to post a reproduction-status update if the user asks). Everything else — `edit`, `transition`, `assign`, `archive`, `delete`, `link create`, `watcher add` — is explicitly disallowed by the plugin's permissions; if the user wants those actions, instruct them to run the command themselves.

## Step 2 — Branch on Issue Type

### Bug

The ticket describes a behavior that should work but doesn't.

- `expected:` — what should happen (copy from the description's "expected behavior" section or rephrase the summary).
- `actual:` — what actually happens, including the exact error message if the ticket quotes one.
- Pin platform / KAS / SDKs to the **versions where the bug reproduces**. Usually `dist:` against a released version. Mixed-version topologies (e.g. platform `v0.9.0` + km1 `v0.9.0-rc.2`) are common and the schema supports them.

If the description doesn't name versions, ask the user. (A headless agent has no user — in that case default to `dist: lts` everywhere and call out the assumption in `actual:`.)

### Story / Task (feature work, TDD-style)

The ticket describes a behavior the user wants to *add*. The scenario you produce is a forward-looking regression gate, not a bug reproducer.

- `expected:` — the new behavior the feature should provide, paraphrased from acceptance criteria.
- `actual:` — the current state, e.g. "feature not implemented; tests skip via `<SDK>.supports('<feature>')` until the supports entry lands." The scenario's `actual:` is what `scenario-run`'s "expected outcome" classifier compares against: a real failure means progress was made; a uniform skip means the prereq SDK plumbing is still pending.
- Pin platform / KAS / SDKs to the **ref where the feature will land**:
  - HEAD of mainline: `platform: { source: { ref: main } }`, `sdks.<lang>.version: main`.
  - Feature branch: `platform: { source: { ref: feature/ecdsa-binding } }`.
  - Draft PR under review: resolve to its head SHA with `gh pr view <N> --json headRefOid` and pin `platform: { source: { ref: <40-char-SHA> } }`. SHAs are reproducible; branch names move every push.
- Only pin the component(s) the feature actually touches. Leave the rest on `lts` / `stable`.

### Spike / unclear

The ticket asks an open question or lacks enough concrete behavior to encode. Don't fabricate a scenario. Emit:

```
<JIRA-KEY> is a Spike (or has no specific behavior / version pins yet). Add either:
  (a) the version or ref where you want behavior exercised, or
  (b) a concrete pass/fail criterion (what should the test assert?)
…and re-invoke this skill.
```

…and stop.

## Step 3 — Pick the id and (optionally) the branch

- `metadata.id = <jira-key-lowercased>` — e.g. `DSPX-3302` → `dspx-3302`.
- Scenario file path: `xtest/scenarios/<jira-key-lowercased>.yaml`.
- If you need a new git branch, propose `<JIRA-KEY>-repro` for Bugs and `<JIRA-KEY>-tdd` for Stories/Tasks; let the user confirm before switching.

## Step 4 — Search for an existing pytest

```bash
grep -rn "<key_term>" xtest/test_*.py xtest/tdfs.py
```

Likely candidates: `test_tdfs.py` (roundtrip), `test_abac.py` (ABAC), `test_legacy.py` (golden), `test_pqc.py`. If a test already asserts the relevant behavior, reuse it via `suite.select` — no draft test needed.

**Don't grep `xtest/sdk/<lang>/cli.sh`.** Those wrappers are reusable infrastructure (versioned alongside each SDK dist) and their contents have nothing to do with scenario YAML fields. The scenario YAML doesn't need to know HOW a feature is plumbed — only WHICH pytest suite exercises it. Reading the wrappers is a waste of turns. If a feature's `supports("<name>")` gate isn't in `tdfs.py` yet, that's a signal that supporting infrastructure has to land separately from the scenario — note it in `actual:` and move on.

## Step 5 — Write `xtest/scenarios/<id>.yaml`

The canonical field list (titles, types, defaults, `anyOf` branches) lives in `xtest/schema/scenario.schema.json` — `Read` it whenever you need to know what's allowed. Each pin (`PlatformPin`, `KasPin`) requires **exactly one** of `dist:`, `source:`, or `image:`. `image:` is reserved for forward-compat and rejected today — pick `dist:` or `source:`.

Released-version pin (typical Bug scenario):

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

Ref pin (TDD / HEAD / branch / PR):

```yaml
instance:
  platform:
    source: { ref: main }                  # branch, tag, or 40-char SHA
  kas:
    alpha:
      source: { ref: feature/ecdsa-binding }
      mode: standard
sdks:
  encrypt:
    go: { version: main }                  # SdkPin.version accepts the same range of strings
```

Mix-and-match is fine — `platform` on `main`, `kas.alpha` on a released `dist:`, SDKs on different refs.

Validate before reporting success:

```bash
uv run python -m otdf_sdk_mgr.schema validate xtest/scenarios/<id>.yaml
```

## Step 6 — If no existing test fits

Draft `xtest/bug_<id>_test.py` using the `encrypt_sdk` / `decrypt_sdk` fixtures (pattern: `xtest/test_tdfs.py`). The `bug_` prefix is a historical slug applied to every scenario-tied test — feature/TDD ones use it too; don't let the name confuse you. Surface the new file in your reply for the user to review — never silently land assertions.

For TDD tests where the underlying feature isn't yet implemented, gate participation behind `<sdk>.supports("<feature>")` and call `pytest.skip(...)` when the gate fails. The scenario then runs as "all skipped" until the SDK supports entry lands, at which point the test becomes a real assertion.

## Notes

- `sdks.encrypt` and `sdks.decrypt` map to xtest's `--sdks-encrypt` / `--sdks-decrypt`. After PR #446 those pytest options take `sdk@version` specifiers like `go@v0.24.0`, `go@main`, or `go@*`. **Do NOT write those tokens in the YAML** — write a normal `{ version: lts }` (or any version string `otdf-sdk-mgr resolve` accepts: `v0.24.0`, `main`, an SDK-specific SHA, etc.). The `scenario-up` skill runs `otdf-sdk-mgr install scenario`, which records the resolved dist directory names in `xtest/scenarios/<id>.installed.json`; the bridge layers (`otdf-local scenario run` and pytest's `--scenario` default in `xtest/conftest.py`) read that file to emit the right `sdk@<dist>` tokens. If you forget the install step, those commands fail with `<id>.installed.json not found — run otdf-sdk-mgr install scenario first`.
- List the same SDK in both `encrypt` and `decrypt` maps to reproduce xtest's legacy "all pairs" mode. Listing it on only one side keeps the scenario focused (a→b without b→a).
- `instance.platform.dist` / `source.ref` and each `kas.<name>.dist` / `source.ref` need `otdf-sdk-mgr install scenario <path>` to have built the binary first. `scenario-up` handles that downstream.
- For matrix runs (same suite × N refs), don't author N scenarios by hand — invoke the `scenario-matrix` skill against this scenario as the base.
- One-line summary when done: report the scenario path, the new test file (if any), and the Jira link `https://virtru.atlassian.net/browse/<JIRA-KEY>` so the user can cross-reference.
