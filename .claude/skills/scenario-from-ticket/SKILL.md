---
name: scenario-from-ticket
description: This skill should be used when the user mentions a Jira key (e.g. "DSPX-3302") and asks to "create a scenario", "write a repro from the ticket", "make a TDD scenario", "draft a test for this bug", or otherwise turn a ticket into a `xtest/scenarios/<id>.yaml` manifest plus (optionally) a draft pytest. Handles Bugs, Stories/Tasks (TDD), and Spikes via Issue Type.
allowed-tools: Bash, Read, Write, Grep, Glob
---

# scenario-from-ticket

Produce a `xtest/scenarios/<jira-key-lowercased>.yaml` manifest from a Jira ticket. The same skill handles bugs, features (TDD), and exploratory work — the *Issue Type* field on the ticket selects which way the rest of the skill behaves.

Two artifacts:

1. `xtest/scenarios/<jira-key-lowercased>.yaml` — validated against `otdf_sdk_mgr.schema.Scenario`.
2. (Optional) `xtest/bugs/<jira_key_lowercased>_test.py` — only if no existing xtest pytest already exercises the behavior.

The Jira key also becomes the working **branch name** (`<JIRA-KEY>-repro` for Bugs, `<JIRA-KEY>-tdd` for Stories/Tasks) and the scenario file's `metadata.id`.

## Step 1 — Pull the Jira ticket into context

Run **both** commands — they take the key differently (`view` is positional, `comment list` requires `--key`). Don't skip the comment list; comments often carry the most recent reproduction status, "what changed" notes, or "fixed by PR #N" pointers that aren't in the original description:

```bash
acli jira workitem view <JIRA-KEY> --fields '*all' --json
acli jira workitem comment list --key <JIRA-KEY>
```

From the JSON output of the first command, extract:

- **Issue Type** (Bug, Story, Task, Spike) — load-bearing; selects which Step 2 branch to follow.
- **Summary** — becomes scenario `metadata.title`.
- **Description** — version numbers, KAS topology, container types, feature flags, acceptance criteria typically live here.
- **Status** — Backlog / In Progress / Done affects whether the scenario is forward-looking (TDD on Backlog) or retroactive (regression gate on Done).

From the comments, pull any "tested at version X" / "reproduces on platform Y" / "fixed by PR #N" annotations into context.

If the ticket references attached logs, screenshots, or linked PRs, list them:

```bash
acli jira workitem attachment list <JIRA-KEY>
acli jira workitem link list <JIRA-KEY>
```

**Linked-PR auto-pin.** When `link list` returns a PR URL (e.g. `https://github.com/opentdf/platform/pull/3537`), resolve it immediately and prefer it over the headless default `dist: lts`:

```bash
gh pr view <N> --repo <owner/repo> --json number,headRefName,headRefOid
```

Use the 40-char `headRefOid` as `source.ref:` for the platform/KAS pin. Branch names move on every push; SHAs don't. Record the branch name in `metadata.title` for human readability. See `references/yaml-templates.md` → "PR pin via Jira link" for the full template.

**Permitted Jira writes**: only `acli jira workitem comment create <JIRA-KEY> ...` (to post a reproduction-status update if the user asks). Everything else — `edit`, `transition`, `assign`, `archive`, `delete`, `link create`, `watcher add` — is explicitly disallowed by the plugin's permissions; if the user wants those actions, instruct them to run the command.

## Step 2 — Branch on Issue Type

### Bug

The ticket describes a behavior that should work but doesn't.

- `expected:` — what should happen (copy from the description's "expected behavior" section or rephrase the summary).
- `actual:` — what actually happens, including the exact error message if the ticket quotes one.
- Pin platform / KAS / SDKs to the **versions where the bug reproduces**. Usually `dist:` against a released version. Mixed-version topologies (e.g. platform `v0.9.0` + km1 `v0.9.0-rc.2`) are common and the schema supports them.

If the description doesn't name versions: prefer a linked PR (from Step 1) if any; otherwise ask the user. A headless agent with no PR and no version pin defaults to `dist: lts` and calls out the assumption in `actual:`.

### Story / Task (feature work, TDD-style)

The ticket describes a behavior the user wants to *add*. The scenario is a forward-looking regression gate, not a bug reproducer.

- `expected:` — the new behavior, paraphrased from acceptance criteria.
- `actual:` — current state, e.g. "feature not implemented; tests skip via `<SDK>.supports('<feature>')` until the supports entry lands." `scenario-run`'s "expected outcome" classifier compares against this — a real failure means progress; a uniform skip means the prereq SDK plumbing is still pending.
- Pin platform / KAS / SDKs to the **ref where the feature will land**: linked PR (from Step 1) if any, else HEAD of mainline (`source: { ref: main }`), else a feature branch the user names. Only pin components the feature actually touches; leave the rest on `lts` / `stable`.

### Spike / unclear

The ticket asks an open question or lacks enough concrete behavior to encode. Don't fabricate. Emit:

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
- If a new git branch is needed, propose `<JIRA-KEY>-repro` for Bugs and `<JIRA-KEY>-tdd` for Stories/Tasks; let the user confirm before switching.

## Step 4 — Search for an existing pytest

```bash
grep -rn "<key_term>" xtest/test_*.py xtest/tdfs.py
```

Likely candidates: `test_tdfs.py` (roundtrip), `test_abac.py` (ABAC), `test_legacy.py` (golden), `test_pqc.py`. If a test already asserts the relevant behavior, reuse it via `suite.targets` (list of pytest selectors) — no draft test needed.

**Don't grep `xtest/sdk/<lang>/cli.sh`.** Those wrappers are reusable infrastructure (versioned alongside each SDK dist) and their contents have nothing to do with scenario YAML fields. The scenario doesn't need to know HOW a feature is plumbed — only WHICH pytest suite exercises it. If a feature's `supports("<name>")` gate isn't in `tdfs.py` yet, that's a signal that supporting infrastructure has to land separately from the scenario — note it in `actual:` and move on.

## Step 5 — Write `xtest/scenarios/<id>.yaml`

Templates (released-version, ref-pin, mixed-mode, PR-pin-via-Jira-link) live in **`references/yaml-templates.md`**. Pick the matching shape, copy, and fill in.

Validate before reporting success:

```bash
uv run python -m otdf_sdk_mgr.schema validate xtest/scenarios/<id>.yaml
```

## Step 6 — If no existing test fits

Draft `xtest/bugs/<id>_test.py` using the `encrypt_sdk` / `decrypt_sdk` fixtures (pattern: `xtest/test_tdfs.py`). Surface the new file in the reply for the user to review — never silently land assertions.

For TDD tests where the underlying feature isn't yet implemented, gate participation behind `<sdk>.supports("<feature>")` and call `pytest.skip(...)` when the gate fails. The scenario then runs as "all skipped" until the SDK supports entry lands.

## Notes

- `sdks.encrypt` and `sdks.decrypt` map to xtest's `--sdks-encrypt` / `--sdks-decrypt`. Pytest options take `sdk@version` specifiers (e.g. `go@v0.24.0`). **Do NOT write those tokens in the YAML** — write a normal `{ version: lts }` (or any version string `otdf-sdk-mgr resolve` accepts). `scenario-up` runs `otdf-sdk-mgr install scenario`, which records the resolved dist names in `xtest/scenarios/<id>.installed.json`; the bridge layers read that file to emit the right `sdk@<dist>` tokens.
- List the same SDK in both `encrypt` and `decrypt` maps to reproduce xtest's legacy "all pairs" mode. Listing it on only one side keeps the scenario focused (a→b without b→a).
- For matrix runs (same suite × N refs), don't author N scenarios by hand — invoke the `scenario-matrix` skill against this scenario as the base.
- Hand the resulting scenario to `scenario-up` next.

## Additional Resources

### Reference files

- **`references/yaml-templates.md`** — every scenario YAML shape: released-version (Bug), ref-pin (TDD/HEAD), mixed-mode (new platform + shipped KAS), PR-pin-via-Jira-link (recommended when `acli link list` returned an opentdf PR), plus the validation command. Read this when writing or reviewing a scenario manifest.
