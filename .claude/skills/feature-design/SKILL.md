---
name: feature-design
description: This skill should be used when the user asks to "design a cross-repo feature", "set up a feature spec", "draft a feature across platform and SDKs", "design a fix that spans repos", or wants the tests-side artifacts + per-repo todo lists set up in one pass for work that crosses platform + Go/Java/JS SDKs. Hands off to `feature-orchestrate` for the per-repo PR work.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Skill
---

# feature-design

Turn a fuzzy "let's build X across the OpenTDF repos" into a concrete bundle of artifacts that pin down the tests-side work first and stage the cross-repo work for handoff to `feature-orchestrate`.

Two ideas to internalize before reading the steps:

1. **Tests-side artifacts land first, dormant.** The scenario + draft test + `feature_type` entry merge to `tests/main` as a regular PR. They stay "all skipped" until each SDK opens its own PR adding a `supports <feature>` case to its `cli.sh` source — that PR's CI activates the test for that SDK. No cross-PR lockstep coordination; per-repo PRs land async, in any order.
2. **Propose, don't ask.** Draft a complete spec from the Jira ticket on the first pass and let the user redirect what's wrong in a single revision. Only ask one composite question. If information is missing that can't be filled in (no Jira ticket, ambiguous scope, unclear feature name), bail — don't fabricate.

## Inputs

- Jira key (Story/Task usually; Bug works the same way), OR a free-text description of the feature.
- (Optional) explicit list of repos to scope to, if the user wants something tighter than the default.

## Steps

### Step 1 — Pull the Jira context

If a Jira key was given, run both — `view` takes the key positionally, `comment list` requires `--key`; comments often carry scope refinements:

```bash
acli jira workitem view <JIRA-KEY> --fields '*all' --json
acli jira workitem comment list --key <JIRA-KEY>
```

Extract Issue Type, summary, description, status, and any comments about scope or implementation notes. If no Jira key, the user's description IS the spec input.

### Step 2 — Propose a complete draft

Draft the full spec body and the per-repo todo lists inline in the reply. Don't ask the user one field at a time — produce a complete first draft they can react to:

- **Feature flag name** — snake_case identifier derived from the Jira summary. Becomes the `supports("<name>")` gate string AND the `feature_type` entry in `xtest/tdfs.py`. Validate it's a valid Python identifier and doesn't collide with an existing `feature_type` member.
- **Touched cells** — the spec divides work into *cells of effort*, not just repos. The platform monorepo holds proto definitions, the Go SDK, KAS service code, and shared libraries; a feature often touches multiple cells *inside* `platform` plus one or more standalone SDK repos. Default cells when a feature spans the whole stack:
  - `tests` — always present (dormant scenario + `feature_type` entry); no `path:` since it IS the current repo.
  - `platform-proto` — when the feature changes wire format (`.proto` edits + `buf generate`). The bindings it produces are an upstream dependency for every SDK cell. `path: platform`.
  - `platform-service` — KAS path / policy plumbing / dev-harness env-var handling. `path: platform`.
  - `platform-go-sdk` — Go SDK encrypt/decrypt path (lives in the platform monorepo at `sdk/`). `path: platform`.
  - `java-sdk` — Java SDK. `path: java-sdk` (standalone repo).
  - `web-sdk` — JS/TS SDK. `path: web-sdk` (standalone repo).
  - `otdfctl` — Go CLI. `path: otdfctl`. Rare; usually only when the feature surfaces in the CLI directly.

  Pure platform-internal features skip the SDK cells. SDK-only features skip the platform cells. Trim aggressively.

- **`path:`** — for every non-`tests` cell, set `path:` to the sibling directory under `~/Documents/GitHub/opentdf/`. Multiple cells can share a `path` value (the orchestrator creates a separate worktree per cell, each on its own branch).

- **`depends_on:`** — list other cell keys whose work must finish before this cell can adopt their output. The canonical case: every cell that consumes regenerated bindings declares `depends_on: [platform-proto]` whenever the feature changes proto. Without `depends_on`, the orchestrator runs cells in parallel.

- **Per-cell todo lists** — 2-4 bullets per cell:
  - `tests` — register the feature in `feature_type`, author the scenario, draft the test gated on `supports("<feature>")`.
  - `platform-proto` — edit the `.proto`, run `buf generate`, commit the regenerated stubs across Go / Java / JS subdirs.
  - `platform-service` — implement the server-side change; honor any new env var the test harness uses (e.g. `XT_WITH_<FEATURE>`).
  - `platform-go-sdk` / `java-sdk` / `web-sdk` / `otdfctl` — implement the client encrypt/decrypt path, plus a `supports <feature>` case in that SDK's `cli.sh` source. **Don't pin the version bound in the spec** — the implementing engineer sets the `awk` predicate at PR time, since the bound depends on which release ships the impl.

- **Branch names** — `<JIRA-KEY>-<cell-key>` (e.g. `DSPX-2719-platform-proto`, `DSPX-2719-java-sdk`). Cell-specific rather than uniform-across-repos because the orchestrator creates a separate worktree per cell, each on its own branch — multiple cells sharing the same `path` would otherwise collide.

Present the draft, then ask exactly one composite question: "Anything to redirect — feature name, touched cells, todo items, dependency edges, branches?" Apply edits in a single revision rather than turn-by-turn. The user can always drop into plain chat if they want to think out loud — just answer them and re-invoke this skill once the design firms up.

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
    branch: <JIRA-KEY>-tests
    todo:
      - Register "<feature-name>" in xtest/tdfs.py feature_type
      - Author scenario + draft test (via scenario-from-ticket)
  platform-proto:                          # cell key, not repo name
    path: platform                         # which sibling repo this lives in
    branch: <JIRA-KEY>-platform-proto
    todo:
      - Edit <service>.proto, add <RPC> with <fields>
      - Run buf generate; commit regenerated Go/Java/JS stubs
  platform-service:
    path: platform
    branch: <JIRA-KEY>-platform-service
    depends_on: [platform-proto]           # waits for proto cell
    todo:
      - Implement the new RPC handler in the KAS service
      - Honor XT_WITH_<FEATURE> in the dev test harness
  platform-go-sdk:
    path: platform
    branch: <JIRA-KEY>-platform-go-sdk
    depends_on: [platform-proto]
    todo:
      - Implement <feature> in the SDK's encrypt path
      - Add `supports <feature>` case to sdk/go/cli.sh
  java-sdk:
    path: java-sdk
    branch: <JIRA-KEY>-java-sdk
    depends_on: [platform-proto]
    todo:
      - Implement <feature> in the Java SDK encrypt path
      - Add `supports <feature>` case to sdk/java/cli.sh
  web-sdk:
    path: web-sdk
    branch: <JIRA-KEY>-web-sdk
    depends_on: [platform-proto]
    todo:
      - Implement <feature> in the JS SDK encrypt path
      - Add `supports <feature>` case to sdk/js/cli.sh
scenarios:
  - xtest/scenarios/<jira-key-lowercased>.yaml
```

PR status (open/merged/CI passing) deliberately is NOT in the spec — it's auto-discovered from `gh pr list --search "head:<branch>"` per repo whenever something asks "where are we?" The spec is a declaration of intent. The orchestrator (`feature-orchestrate`) reads this file and fans out one subagent per cell, respecting `depends_on` waves.

### Step 4 — Drive the tests-side artifacts

In this order, so each step's output feeds the next:

1. **Add the feature flag to `xtest/tdfs.py`**. Find the `feature_type` Literal alias near the top of the file. Insert the new entry alphabetically. Don't touch any `cli.sh` files — `supports <feature>` cases land per-SDK in their own PRs.

2. **Invoke `scenario-from-ticket`** via the Skill tool (`skill: scenario-from-ticket`, `args: <JIRA-KEY>`). It runs its Story/Task branch and produces the scenario + draft test gated on `supports("<feature>")`. If no Jira key was given, draft the scenario directly using the same shape (`xtest/scenarios/<feature-name>.yaml`).

3. **Validate the scenario**:

   ```bash
   uv run python -m otdf_sdk_mgr.schema validate xtest/scenarios/<jira-key>.yaml
   ```

### Step 5 — Report

One block summarizing:

- The spec path (`xtest/features/<feature-name>.yaml`).
- The scenario + draft test paths.
- The line(s) added to `xtest/tdfs.py`.
- A one-liner suggesting next steps: `feature-orchestrate xtest/features/<feature-name>.yaml` (for per-repo PR work), or `scenario-up xtest/scenarios/<id>.yaml` + `scenario-doctor <id>` (to bring the dormant scenario up against `main` and confirm "all skipped" baseline before SDK work starts).

## Notes

- This skill produces **tests-side artifacts only**. It does NOT create branches in other repos, does NOT open PRs, does NOT install platform/SDK builds. That's `feature-orchestrate`'s job.
- Bugs that span repos use the same shape — pass the Bug ticket key and `scenario-from-ticket`'s Bug branch fills `expected:` / `actual:` from the reproduction prose. The cross-repo gating still works: tests land dormant, each per-repo PR activates them by adding the supports case as part of the fix.
- For an existing spec being revised, read it first and propose a diff rather than a full rewrite. The tests-side artifacts (scenario, tdfs.py entry) usually shouldn't be regenerated — edit them surgically.
- If the user starts the conversation by describing the feature in plain chat rather than invoking this skill, answer normally — re-invoke the skill once the scope firms up. Don't gatekeep.
