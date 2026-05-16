---
name: scenario-up
description: Provision artifacts, scaffold the instance directory, and start the test environment for a given xtest/scenarios/<id>.yaml. Use after `scenario-from-ticket` (or `scenario-matrix`, or when the user already has a scenario YAML) and wants the environment running.
allowed-tools: Bash, Read
---

# scenario-up

You bring the environment described by a `scenarios.yaml` up and confirm it's healthy. The three steps are non-negotiable; do them in order.

## Inputs

- Path to a validated `xtest/scenarios/<id>.yaml`. If the user doesn't provide one, ask.

## Process

1. **Install artifacts** — platform binary, per-KAS binaries, helper scripts, and the encrypt+decrypt SDKs declared in the scenario:

   ```bash
   uv run otdf-sdk-mgr install scenario xtest/scenarios/<id>.yaml
   ```

   This writes `xtest/scenarios/<id>.installed.json` next to the scenario with the resolved dist paths. The first `go build` per platform version takes ~30-60s; subsequent runs reuse the cached binary.

2. **Scaffold the instance directory** (creates `tests/instances/<id>/`):

   ```bash
   uv run otdf-local instance init <id> --from-scenario xtest/scenarios/<id>.yaml
   ```

   If the instance already exists, this is a no-op for the existing files; double-check with `uv run otdf-local instance ls` first to avoid surprising the user.

3. **Bring it up**:

   ```bash
   uv run otdf-local --instance <id> up
   ```

   Then poll status until everything is healthy (don't proceed before this succeeds):

   ```bash
   uv run otdf-local --instance <id> status --json
   ```

   If any service stays unhealthy after ~60 seconds, surface the relevant log via `uv run otdf-local --instance <id> logs <service> -n 50` and report the failure mode rather than retrying blindly.

## Output

Once healthy, report:
- The instance name and which ports it occupies (look at `instance.yaml`'s `ports.base`).
- The next command the user is likely to run (`scenario-run`).
