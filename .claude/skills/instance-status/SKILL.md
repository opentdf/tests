---
name: instance-status
description: This skill should be used when the user asks "what's running", "check ports", "show instance status", "list test instances", "are any services up", or before invoking `scenario-up` to detect port collisions (including from sibling git worktrees). For deeper "does the running env match what the scenario yaml says" verification, defer to `scenario-doctor` instead.
allowed-tools: Bash, Read
---

# instance-status

Report a snapshot of test environment state: which instances are defined in this worktree, what is actually listening on the conventional ports (regardless of which worktree owns it), and whether each service is healthy. Surface port collisions before they bite `scenario-up`.

## Process

### Step 0 — Cross-worktree probe (always first)

`otdf-local instance ls` is scoped to the current worktree's `tests/instances/`. Sibling worktrees' running services are invisible to that listing but very much listening on the host's ports. Probe the host directly:

```bash
bash ${CLAUDE_PLUGIN_ROOT:-.}/skills/instance-status/scripts/cross-worktree-probe.sh
```

Output is tab-separated, one row per listener:

```
port   proto  pid    cwd                                        kind
8080   tcp    28656  /Users/.../reproducing-things/...           platform
8585   tcp    28684  /Users/.../reproducing-things/...           kas
compose docker -    main                                         compose-project
```

Carry forward two facts into the rest of the report:
1. Which of the conventional ports (`8080`, `8181..8686`, `5432`, `8888`) are occupied.
2. The owning `cwd` for each — when it differs from the current worktree, label the line as **foreign** in the final summary so the user knows to tear that down before re-using the port.

### Step 1 — List instances on disk

```bash
uv run otdf-local instance ls --json
```

Each entry includes `name`, `platform` version, `ports_base`, and the `kas:` keys. Two checks:
- Flag any two local instances that share a `ports_base` — they cannot run concurrently.
- Note: this listing is **worktree-scoped**. The cross-worktree probe from Step 0 is the source of truth for "what's actually using port X."

### Step 2 — Per-instance status

For each local instance from Step 1:

```bash
uv run otdf-local --instance <name> status --json
```

Each service reports `running`, `healthy`, and the bound port. Run sequentially (a status query is cheap; parallel adds nothing). Cross-reference each "running" entry with Step 0's table — if the port shows `kind=platform` but the owning `cwd` is a sibling worktree, the local instance's status reading is misleading (it's reporting on someone else's binary).

### Step 3 — Summarize

Compose the reply in this order:
1. **Cross-worktree listeners** — the Step 0 table, with each foreign row labeled. Skip if no ports are occupied.
2. **Local instances** — one short block per instance: service → port → state (running/healthy). Mark each row's port as `local` or `foreign` based on Step 0's owner.
3. **Port-base collisions** — any pair of local instances with the same `ports_base`, recommending a re-init: `uv run otdf-local instance init <name> --from-scenario <path> --ports-base <new>`.
4. **Unhealthy rows** — each with the path to its log (e.g. `tests/instances/<name>/logs/kas-alpha.log`).

Skip empty sections rather than print "(none)".

## When ports collide

If Step 0 shows a foreign listener on a port the user is about to use, two paths:
- Tear down the foreign instance first. Find the owning worktree from the `cwd` column; cd there and run `OTDF_LOCAL_INSTANCE_NAME=<name> uv run otdf-local down`.
- Or pick a different ports base for the new instance: `uv run otdf-local instance init <name> --from-scenario <path> --ports-base 9080` (or any free base).

If `otdf-local instance init` warns about a local collision at creation time, it doesn't enforce it; re-running with `--ports-base <new>` is the fix.

## What this skill does NOT do

For the deeper question "is the binary serving port X actually the one my scenario YAML pinned?", use `scenario-doctor` — that skill diffs the running service's `.version` sidecar against the instance's expected pin. `instance-status` reports *what's listening*, not *whether it's the right thing*.

## Additional Resources

### Script

- **`scripts/cross-worktree-probe.sh`** — surveys conventional ports + docker compose projects across all worktrees on this host. Always run first in Step 0. Tab-separated stdout (header on line 1).
