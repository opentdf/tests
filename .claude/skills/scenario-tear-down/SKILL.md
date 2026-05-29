---
name: scenario-tear-down
description: This skill should be used when the user asks to "tear down the scenario", "stop the instance", "shut down the test environment", "clean up the scenario", "free the ports", or is done with a scenario and wants services stopped and (optionally) on-disk state removed.
allowed-tools: Bash, Read
---

# scenario-tear-down

Stop a running scenario cleanly and optionally remove its on-disk state. Confirm shared resources (docker stacks across worktrees, symlinked platform dirs) are handled appropriately.

## Inputs

- The instance name (typically the lowercased Jira key, e.g. `dspx-3302`). If the user passed the scenario YAML path instead, read its `instance.metadata.name`.
- Whether to preserve the instance directory (default: yes — keep it for re-runs).

## Process

### Step 1 — Pre-flight shared resources

Before stopping anything, list the docker compose projects currently sharing the host daemon:

```bash
docker ps --format '{{.Names}}' \
  | grep -E -- '-keycloak-|-opentdfdb-' \
  | sed -E 's/-(keycloak|opentdfdb)-[0-9]+$//' \
  | sort -u
```

Each line is a compose-project name — typically the directory name where `docker compose` was invoked (a worktree's `xtest/platform/src/<slug>/`). If more than one project appears, surface this in the reply: `down` will *keep* docker keycloak/postgres running because another instance still uses them. The user's expectation that "ports 5432 and 8888 are now free" would be wrong.

### Step 2 — Stop services

```bash
uv run otdf-local --instance <name> down
```

Halts the platform process, all KAS instances under management, and the docker dependencies — unless another instance is still using them, in which case docker is left running (per Step 1's pre-flight). Other instances' platforms and KAS processes are untouched.

### Step 3 — Optionally clean state

Only if the user explicitly asked to remove:

```bash
uv run otdf-local instance rm <name> -y
```

Deletes `tests/instances/<name>/` including its `logs/`, `keys/`, and per-KAS configs. The platform binary at `xtest/platform/dist/<slug>/service` is shared and is NOT removed. To free those too:

```bash
uv run otdf-sdk-mgr clean --dist-only
```

### Step 4 — Confirm

```bash
uv run otdf-local instance ls --json
```

Verify the instance is gone (if `rm`'d) or that its services no longer appear running. If sibling worktrees still own ports, that's recorded in Step 1's output — flag it in the summary.

## Post-down notes to surface

- **Symlinked platform dir**: if this worktree's `xtest/platform` is a symlink (or `xtest/platform.local-backup/` exists), mention it. That was a one-time workaround for `uv tool install`'d CLIs anchoring to a sibling worktree (see DSPX-3415). The backup directory accumulates stale `src/` and can be reclaimed (`rm -rf xtest/platform.local-backup`) once the user is sure the symlink is permanent.
- **Foreign docker-compose project**: if Step 1 surfaced another project, name it so the user knows which worktree to manage if they want a truly clean host.

## Caution

Never remove an instance without explicit user confirmation. The directory may contain golden keys or generated configs that took time to assemble. If unsure, leave it.

## Output

One-line summary, then optional sections in this order:
- Stop result (services stopped: …).
- Cleaned (if `rm` was run): instance dir removed at …
- Docker status: stopped / still running (with project names if shared).
- Post-down notes (symlinks, backup dirs, foreign projects).

Skip empty sections.
