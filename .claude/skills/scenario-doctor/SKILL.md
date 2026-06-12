---
name: scenario-doctor
description: This skill should be used when the user asks to "verify my instance", "doctor my scenario", "is my environment healthy", "does the running platform match the scenario", or to diagnose a flaky test run by confirming the expected binaries / keys / health are actually live. Cross-checks running state against `tests/instances/<name>/instance.yaml`.
allowed-tools: Bash, Read
---

# scenario-doctor

Cross-check what an instance's `instance.yaml` *intends* against what is *actually* running, and produce a verdict the user can act on. Most "the test failed for a weird reason" sessions trace back to a drift here — the wrong binary serving the port, stale keys in the worktree, an extra service from a sibling worktree squatting on a port, or a process owned by a different worktree's `otdf-local`.

## Inputs

- Instance name (typically the lowercased Jira key, e.g. `dspx-3302`). If a scenario YAML path is provided instead, read its `instance.metadata.name` and proceed.

## Process

### Step 1 — Run the diff script

```bash
bash ${CLAUDE_PLUGIN_ROOT:-.}/skills/scenario-doctor/scripts/diff-running-vs-intended.sh <name>
```

Output is tab-separated, one row per service:

```
service   port  expected_sha  actual_sha  health  status
platform  8080  08ab3a0aef27  08ab3a0aef27  200    MATCH
km1       8585  08ab3a0aef27  -             down   NOT-RUNNING
alpha     8181  v090...       a1b2c3d4...   200    WRONG-BINARY
```

`status` enumerates:
- `MATCH` — expected ref matches the running binary's `.version` sha, health is 200.
- `WRONG-BINARY` — service is up but serving from a different ref than the instance pins. Often means a sibling worktree's environment is shadowing this one's expected binary.
- `NOT-RUNNING` — port is empty; `otdf-local --instance <name> up` (or `restart <service>`) is needed.
- `EXTRA` — port is occupied by a service the instance didn't declare. Usually a leftover from another instance/worktree.
- `NO-PIN` — instance manifest didn't pin this service (skip).

### Step 2 — Verify instance-dir seed files

`otdf-local instance init` is responsible for seeding `keys/{ca.jks,localhost.crt,localhost.key}`, `keys/kas-*.pem`, and `instances/<name>/opentdf.yaml` (with a generated `services.kas.root_key`). Confirm they're all present:

```bash
bash ${CLAUDE_PLUGIN_ROOT:-.}/skills/scenario-doctor/scripts/check-instance-seed.sh <name>
```

Tab-separated output, one row per artifact, `state ∈ {ok, missing, empty}`. Treat any non-`ok` row as a real problem — re-run `uv run otdf-local instance init <name> --from-scenario <path>` to refresh (existing files are preserved, so this won't churn the root_key).

### Step 3 — Assign a verdict

Roll up Steps 1–2 into one of three colors. Lead the reply with the verdict; users scan for this.

- **GREEN** — every declared service is `MATCH` + 200, no `EXTRA` rows, every seed file `ok`. Nothing for the user to do.
- **YELLOW** — at least one `WRONG-BINARY`, `EXTRA`, or `missing`/`empty` seed-file row, but the instance is *running*. Tests may pass or fail unpredictably until the drift is resolved.
- **RED** — at least one declared service is `NOT-RUNNING`. Tests cannot succeed; recommend `otdf-local --instance <name> up` (fresh start) or per-service `restart`.

### Step 4 — Per-row remedy

For each non-`MATCH` row, emit a one-line remedy alongside the diff table:

| Status | Remedy |
|---|---|
| `NOT-RUNNING` | `otdf-local --instance <name> up` (full) or `restart <service>` (single service) |
| `WRONG-BINARY` | Identify owning PID's worktree via `lsof -p <pid> -d cwd`. If sibling worktree: tear that down first (`OTDF_LOCAL_INSTANCE_NAME=<other> otdf-local down`). If same worktree, stale binary: `otdf-sdk-mgr install tip --ref <expected-ref> platform` then restart. |
| `EXTRA` | Confirm the PID and its cwd. Stop owning instance or kill the stale PID. |
| `missing` / `empty` (seed file) | Re-run `otdf-local instance init <name> --from-scenario <path>`. Existing files are preserved; only the missing seed gets regenerated. |

### Step 5 — Output

Compose the reply in this order: verdict line, diff table (Step 1 output, lightly formatted), seed-file table (Step 2 output, only rows that aren't `ok`), per-row remedy bullets. Skip empty sections rather than print "(none)" — agents pattern-match on what's present.

## When this skill triggers

After any of:
- A surprising pytest result (skip when expected to pass, or pass when expected to skip-then-fail).
- The user asking "what's running" with the implication that they suspect drift, not a simple `instance ls` query (that's `instance-status`'s job).
- Returning to a long-lived branch where the running environment might be stale.

For the simpler "what's defined / what's listening here" question without the diff-against-intent angle, defer to `instance-status`.

## Limits

- The script depends on the `.version` sidecar that `otdf-sdk-mgr install platform` writes. Binaries placed under `xtest/platform/dist/` by other means won't be diffable; they show as `expected_sha=?`.
- `yq` is preferred for parsing `instance.yaml`; the script falls back to grep when `yq` isn't installed. Coverage of the fallback is narrower — install `yq` for accurate KAS-list extraction in unusual manifests.
- Cross-worktree owner detection uses `lsof -p <pid> -d cwd`. Containers running services (rare today) wouldn't surface that way; the verdict would still flag the port collision via `EXTRA`, just without an owning-worktree label.

## Additional Resources

### Scripts

- **`scripts/diff-running-vs-intended.sh`** — automates Step 1's expected-vs-actual diff. Takes one positional argument: the instance name. Tab-separated stdout.
- **`scripts/check-instance-seed.sh`** — read-only verifier for Step 2. Takes one positional argument: the instance name. Confirms `keys/{ca.jks,localhost.crt,localhost.key}`, `keys/kas-*.pem`, and `opentdf.yaml` (with a non-empty `services.kas.root_key`) are present in `tests/instances/<name>/`. Tab-separated stdout.

### Reference files

- **`references/probe-recipes.md`** — verbose shell snippets for ad-hoc inspection: resolving a PID to its worktree, comparing `.version` sidecars by hand, detecting Docker-created empty-dir stubs, listing compose-project owners. Read this when the script's output is ambiguous or the user wants the underlying mechanics.
