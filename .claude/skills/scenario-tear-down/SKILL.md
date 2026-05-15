---
name: scenario-tear-down
description: Stop the services for a scenario's instance and optionally delete the instance directory. Use when the user is done with a reproduction or wants to free ports/disk for a different scenario.
allowed-tools: Bash, Read
---

# scenario-tear-down

You stop a running scenario cleanly and optionally remove its on-disk state.

## Inputs

- The instance name (typically the lowercased Jira key, e.g. `dspx-3302`). If the user passes the scenario YAML path instead, read its `instance.metadata.name`.
- Whether the user wants the instance directory preserved (default: yes — keep it for re-runs).

## Process

1. **Stop services**:

   ```bash
   uv run otdf-local --instance <name> down
   ```

   The `down` command halts the platform process, all KAS instances under management, and the docker dependencies (keycloak, postgres) — unless another instance is still using them, in which case docker is left running.

2. **Optionally clean state**. Only if the user explicitly asked to remove:

   ```bash
   uv run otdf-local instance rm <name> -y
   ```

   This deletes `tests/instances/<name>/` including its `logs/`, `keys/`, and per-KAS configs. The platform binary at `xtest/platform/dist/<version>/service` is shared and is NOT removed (`otdf-sdk-mgr clean --dist-only` is the right command if the user wants to free that too).

3. **Confirm port range is free** (useful if the user is about to bring up another scenario on the same base):

   ```bash
   uv run otdf-local instance ls --json
   ```

## Caution

Never remove an instance without explicit user confirmation. The directory may contain golden keys or generated configs that took time to assemble. If unsure, leave it.
