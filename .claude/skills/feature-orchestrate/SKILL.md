---
name: feature-orchestrate
description: Coordinate a TDD multi-repo feature implementation. Pushes the tests-side draft PR in Wave 1 (so SDK subagents can run CI against the test definitions), then fans out one `claude -p` subagent per implementation cell — each in its own git worktree — to implement, commit, and open draft PRs across platform, java-sdk, web-sdk, and other repos in dependency order. Use when `feature-design` has finished and you're ready to dispatch cross-repo implementation.
allowed-tools: Bash, Read
---

# feature-orchestrate

You drive the cross-repo implementation of a feature whose spec lives at `xtest/features/<feature-name>.yaml`. The tests-side artifacts (scenario, draft test, `feature_type` entry) have already been authored by `feature-design`; your job is to dispatch a subagent per remaining cell, in dependency order, and report the resulting PRs.

The heavy lifting is a Python helper: `uv run otdf-sdk-mgr orchestrate run <spec>`. The skill body is a thin wrapper around it — invoke the verb, surface its output.

## Inputs

- Path to a feature spec at `xtest/features/<name>.yaml` (produced by `feature-design`).
- (Optional) `--only <cell-key>` to run a subset of cells. Repeatable.
- (Optional) `--dry-run` to print the plan without dispatching.

## Process

### Step 1 — Sanity-check the spec

Before dispatching, run a dry-run so the user can confirm the topology and pinning are what they expect:

```bash
uv run otdf-sdk-mgr orchestrate run xtest/features/<name>.yaml --dry-run
```

The output names each cell, its target repo path, the branch it'll work on, and the worktree path the orchestrator will create (or `action=push+draft-PR` for the `tests` cell). Cells that already have an open PR are annotated with `[PR EXISTS: <url>]` — those will be skipped on the real run (no subagent launched). Each wave is a set of cells with no dependencies between them; cells in a later wave have at least one `depends_on` edge into an earlier wave.

Surface the dry-run output to the user verbatim. If anything looks wrong (a cell going to the wrong repo, a missing `depends_on` edge, a stale branch name), ask the user to fix the spec via `feature-design` (or edit it directly) before proceeding.

### Step 2 — Dispatch

When the user confirms, run for real:

```bash
uv run otdf-sdk-mgr orchestrate run xtest/features/<name>.yaml
```

The run is **idempotent**: cells whose branch already has an open PR are reported as `OK` with the existing PR URL and no subagent is launched. Re-running after a partial failure resumes from where it left off — already-done cells are skipped, failed or not-yet-started cells are dispatched. Use `--force` to re-run a cell even if it already has a PR (e.g. to incorporate spec changes into an existing draft).

For each cell that needs work, the orchestrator:

1. Creates `~/Documents/GitHub/worktrees/<JIRA-KEY>-<cell-key>/` as a worktree of `~/Documents/GitHub/opentdf/<path>` on branch `<cell.branch>`. Idempotent — reuses an existing worktree if it's already on the right branch, bails if it's on a different one.
2. Writes a minimal `.claude/settings.json` into the worktree (allowing `git`, `gh pr create`, and the repo-type-appropriate test commands: `go`/`make`/`buf` for platform, `mvn` for java-sdk, `npm` for web-sdk).
3. Launches `claude -p --model sonnet --permission-mode acceptEdits` inside the worktree with a prompt containing the full spec body + that cell's todo + house-style commit guidance. The subagent implements, commits, opens a draft PR via `gh pr create --draft`, and prints the PR URL as its last line of output.
4. Captures stdout to `.claude/tmp/runs/<JIRA-KEY>-<cell-key>.jsonl` for inspection.

Cells in the same wave run in parallel (Python `ThreadPoolExecutor`). Each subagent has a 30-minute timeout by default (`--timeout 1800` to override). If a subagent fails, its dependents in later waves are skipped with a clear "upstream dependency failed" note.

### Step 3 — Report

When the orchestrator finishes, it prints a final table:

```
CELL                     STATUS PR / ERROR
tests                    OK     https://github.com/opentdf/tests/pull/123
platform-proto           OK     https://github.com/opentdf/platform/pull/1234
platform-service         OK     https://github.com/opentdf/platform/pull/1235
java-sdk                 OK     https://github.com/opentdf/java-sdk/pull/567
web-sdk                  FAIL   exit 1
```

Pass the table on to the user, plus the JSONL transcript paths for any FAIL rows so they can inspect what went wrong.

## Resumption and partial runs

**Resuming after a failure** — just re-run the same command. The orchestrator skips cells that already have open PRs and only dispatches the ones that failed or were skipped due to upstream failures. The dependency check still runs: if a cell's `depends_on` failed in the previous wave, it will be skipped again rather than dispatched into a broken state. Fix the upstream cell first (see below), then re-run.

**Fixing a failed cell** — inspect the transcript at `.claude/tmp/runs/<JIRA-KEY>-<cell-key>.jsonl`, identify the problem, fix it (in the worktree at `~/Documents/GitHub/worktrees/<JIRA-KEY>-<cell-key>/` or by patching the spec), then re-run. If the fix was in the worktree (e.g. the subagent left partial commits), you may want `--only <cell-key>` to avoid redundant PR-existence checks across many cells.

**Staging a cell before its dependents** — `--only platform-proto` runs only the proto cell. Once its PR is reviewed and merged, re-run without `--only` and the orchestrator picks up from the next wave (proto cell already has a PR, so it's skipped; service/SDK cells proceed).

**Forcing a re-run** — `--force` makes the orchestrator ignore existing PRs and dispatch a fresh subagent for every non-skipped cell. Combine with `--only` to force just one cell:
```bash
uv run otdf-sdk-mgr orchestrate run xtest/features/<name>.yaml --only java-sdk --force
```

## Notes

- **TDD/BDD lifecycle.** The `tests` cell is handled differently from all other cells: the orchestrator pushes the branch and opens a draft PR directly (no subagent) in Wave 1, alongside `platform-proto`. This makes the dormant tests visible to CI early — each SDK's per-repo PR can link back to the tests PR, and once that repo adds a `supports <feature>` case to its CLI wrapper, its CI activates the relevant tests automatically. No cross-PR lockstep coordination is needed.
- **The `tests` cell is never skipped automatically.** If `feature-design` produced the tests-side artifacts on the current branch, the orchestrator pushes that branch and opens the draft PR. If the tests repo is on a different branch, the orchestrator reports an error rather than silently skipping.
- Worktrees live at `~/Documents/GitHub/worktrees/<JIRA-KEY>-<cell-key>/` regardless of which repo they came from. The user's main checkouts (`~/Documents/GitHub/opentdf/{platform,java-sdk,web-sdk,otdfctl}/`) are never modified.
- Subagents print the PR URL on their last line of output as a contract — the orchestrator parses it with a regex. If a subagent doesn't print one, the orchestrator reports the cell as "no PR URL" but doesn't mark it failed (the subagent may have done useful work even if the PR step failed).
- The orchestrator dispatches subagents in parallel within a wave, so per-cell logs interleave in real time but each cell's full transcript lands in its own JSONL file. Inspect transcripts under `.claude/tmp/runs/`.
- For features whose protos don't change wire format, omit `depends_on: [platform-proto]` on the SDK cells — they can run in parallel with the proto cell (or skip the proto cell entirely).
