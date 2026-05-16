---
name: feature-design
description: Turn a multi-repo feature (or cross-repo bug fix) into a concrete spec at xtest/features/<name>.yaml plus the tests-side artifacts that have to land first (scenario, draft pytest, feature_type entry in tdfs.py). Pulls Jira context, drafts a complete spec from the ticket, then iterates with the user. Use when a feature touches more than one repo (e.g. platform + Go SDK + Java SDK + JS SDK) and you want to set up the cross-repo work in one go without manually authoring each piece.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Skill
---

# feature-design

You turn a fuzzy "let's build X across the OpenTDF repos" into a concrete bundle of artifacts that pin down the tests-side work first and stage the cross-repo work for handoff to `feature-orchestrate`.

Two ideas to internalize before reading the steps:

1. **Tests-side artifacts land first, dormant.** The scenario + draft test + `feature_type` entry merge to `tests/main` as a regular PR. They stay "all skipped" until each SDK opens its own PR adding a `supports <feature>` case to its `cli.sh` source — that PR's CI activates the test for that SDK. This means no cross-PR lockstep coordination; per-repo PRs land async, in any order.
2. **Propose, don't ask.** Draft a complete spec from the Jira ticket on the first pass and let the user redirect what's wrong in a single revision. Only ask one composite question. If you're missing information you can't fill in (no Jira ticket, ambiguous scope, unclear feature name), bail — don't fabricate.

## Inputs

- Jira key (Story/Task usually; Bug works the same way), OR a free-text description of the feature.
- (Optional) explicit list of repos to scope to, if the user wants something tighter than the default.

## Steps

### Step 1 — Pull the Jira context

If a Jira key was given, run both — comments often carry scope refinements that aren't in the description:

```bash
acli jira workitem view <JIRA-KEY> --fields '*all' --json
acli jira workitem comment list <JIRA-KEY>
```

Extract Issue Type, summary, description, status, and any comments about scope or implementation notes. If no Jira key, the user's description IS the spec input.

### Step 2 — Propose a complete draft

Draft the full spec body and the per-repo todo lists inline in your reply. Don't ask the user one field at a time — produce a complete first draft they can react to:

- **Feature flag name** — snake_case identifier derived from the Jira summary. Becomes the `supports("<name>")` gate string AND the `feature_type` entry in `xtest/tdfs.py`. Validate it's a valid Python identifier and doesn't collide with an existing `feature_type` member.
- **Touched repos** — default set is `tests, platform, sdk-go, sdk-java, sdk-web`. Trim or expand based on what the ticket says. Pure platform features skip the SDK repos; pure SDK-only features skip platform; `tests` is always present (the dormant scenario + tdfs.py entry has to live there).
- **Per-repo todo lists** — 2-4 bullets per repo, derived from the description plus each repo's known role:
  - `tests` — register the feature in `feature_type`, author the scenario, draft the test gated on `supports("<feature>")`.
  - `platform` — service-side implementation (KAS path, policy plumbing, etc.) and any env-var handling in the dev harness (e.g. honoring `XT_WITH_<FEATURE>`).
  - `sdk-go` / `sdk-java` / `sdk-web` — encrypt/decrypt path implementation, plus a `supports <feature>` case in that SDK's `cli.sh` source. **Don't pin the version bound in the spec** — the implementing engineer sets the `awk` predicate at PR time, since the bound depends on which release will ship the impl.
- **Branch name** — `<JIRA-KEY>-<feature-slug>`, the same string across every touched repo so `feature-orchestrate` (and the user) can find each repo's PR by branch alone.

Present the draft, then ask exactly one composite question: "Anything to redirect — feature name, touched repos, todo items, branch?" Apply edits in a single revision rather than turn-by-turn. The user can always drop into plain chat if they want to think out loud — just answer them and re-invoke this skill once the design firms up.

If no Jira key was given AND the user's description doesn't pin down a clear scope (feature flag name, touched repos, intended behavior), bail rather than fabricate:

```
I need either (a) a Jira Story/Task/Bug key, or (b) a description that names
the feature flag, the repos it touches, and the intended behavior. Add either
and re-invoke this skill.
```

### Step 3 — Write the spec

Write `xtest/features/<feature-name>.yaml`. Shape (still informal — no Pydantic model yet):

```yaml
apiVersion: opentdf.io/v1alpha1
kind: Feature
metadata:
  name: <feature-name>                     # supports() string + feature_type entry, snake_case
  jira: <JIRA-KEY>                         # omit if no ticket
  title: "<one-line title>"
  created: <YYYY-MM-DD>
repos:
  tests:
    branch: <JIRA-KEY>-<feature-slug>
    todo:
      - Register "<feature-name>" in xtest/tdfs.py feature_type
      - Author scenario + draft test (via scenario-from-ticket)
  platform:
    branch: <JIRA-KEY>-<feature-slug>
    todo: [ ... ]
  sdk-go:
    branch: <JIRA-KEY>-<feature-slug>
    todo:
      - Implement <feature> in the encrypt/decrypt path
      - Add `supports <feature>` case to cli.sh with version-bound awk predicate
  sdk-java: { branch: ..., todo: [ ... ] }
  sdk-web:  { branch: ..., todo: [ ... ] }
scenarios:
  - xtest/scenarios/<jira-key-lowercased>.yaml
```

PR status (open/merged/CI passing) deliberately is NOT in the spec — it's auto-discovered from `gh pr list --search "head:<branch>"` per repo whenever something asks "where are we?" The spec is a declaration of intent.

### Step 4 — Drive the tests-side artifacts

In this order, so each step's output feeds the next:

1. **Add the feature flag to `xtest/tdfs.py`**. Find the `feature_type` Literal alias near the top of the file. Insert the new entry alphabetically. Don't touch any `cli.sh` files — `supports <feature>` cases land per-SDK in their own PRs.

2. **Invoke `scenario-from-ticket`** via the Skill tool (`skill: scenario-from-ticket`, `args: <JIRA-KEY>`). It runs its Story/Task branch and produces the scenario + draft test gated on `supports("<feature>")` — pinning the feature-introducing components to `main` via `source.ref:`. If no Jira key was given, draft the scenario directly using the same shape (`xtest/scenarios/<feature-name>.yaml`).

3. **Validate the scenario**:

   ```bash
   uv run python -m otdf_sdk_mgr.schema validate xtest/scenarios/<jira-key>.yaml
   ```

### Step 5 — Report

One block summarizing:

- The spec path (`xtest/features/<feature-name>.yaml`).
- The scenario + draft test paths.
- The line(s) added to `xtest/tdfs.py`.
- A one-liner suggesting the next step: `feature-orchestrate xtest/features/<feature-name>.yaml`.

## Notes

- This skill produces **tests-side artifacts only**. It does NOT create branches in other repos, does NOT open PRs, does NOT install platform/SDK builds. That's `feature-orchestrate`'s job.
- Bugs that span repos use the same shape — pass the Bug ticket key and `scenario-from-ticket`'s Bug branch fills `expected:` / `actual:` from the reproduction prose. The cross-repo gating still works: tests land dormant, each per-repo PR activates them by adding the supports case as part of the fix.
- For an existing spec being revised, read it first and propose a diff rather than a full rewrite. The tests-side artifacts (scenario, tdfs.py entry) usually shouldn't be regenerated — just edit them surgically.
- If the user starts the conversation by describing the feature in plain chat rather than invoking this skill, answer normally — re-invoke the skill once the scope firms up. Don't gatekeep.
