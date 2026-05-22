---
name: instance-status
description: Use when the user asks what's running, or before starting a scenario to check for port collisions.
allowed-tools: Bash, Read
---

# instance-status

You give the user a snapshot of all test instances in this checkout: what's defined, what's running, and whether each service is healthy.

## Process

1. **List instances on disk**:

   ```bash
   uv run otdf-local instance ls --json
   ```

   Each entry includes `name`, `platform` version, `ports_base`, and the `kas:` keys. Flag any two instances that share a `ports_base` — they cannot run concurrently.

2. **For each instance**, check service status:

   ```bash
   uv run otdf-local --instance <name> status --json
   ```

   Each service reports `running`, `healthy`, and the bound port. Don't run all instances in parallel — iterate; a status query is cheap.

3. **Summarize**:
   - A short table per instance: service → port → state.
   - Flag any unhealthy service with the path to its log (e.g. `tests/instances/<name>/logs/kas-alpha.log`).
   - Mention port conflicts if two instances would collide on `ports.base`.

## When ports collide

`otdf-local instance init` warns about this at creation time but does not enforce it. If you see two instances with the same `ports_base`, recommend the user reassign one via `uv run otdf-local instance init <name> --from-scenario <path> --ports-base <new>` (or hand-edit the `instance.yaml`).
