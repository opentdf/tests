---
name: scenario-up
description: This skill should be used when the user asks to "bring up a scenario", "start a scenario environment", "spin up the test instance", "install and run the scenario", or has authored a `xtest/scenarios/<id>.yaml` and wants the platform + KAS + dependencies started before invoking pytest. Use `scenario-run` after this succeeds.
allowed-tools: Bash, Read
---

# scenario-up

Bring the environment described by a `xtest/scenarios/<id>.yaml` up and confirm it is healthy. The four steps are non-negotiable; do them in order.

## Inputs

- Path to a validated `xtest/scenarios/<id>.yaml`. If the user did not provide one, ask.

## Process

### Step 1 — Install artifacts

```bash
uv run otdf-sdk-mgr install scenario xtest/scenarios/<id>.yaml
```

Installs the platform binary, per-KAS binaries, helper scripts, and the encrypt + decrypt SDKs declared in the scenario. The result is recorded at `xtest/scenarios/<id>.installed.json` next to the scenario.

**Guard against partial installs.** Read the resulting `<id>.installed.json` immediately:

```bash
cat xtest/scenarios/<id>.installed.json | jq '{status, sdk_count: (.sdks.encrypt + .sdks.decrypt | length)}'
```

If `status == "partial"` OR `sdks.encrypt` / `sdks.decrypt` are empty arrays *but* the scenario declared SDK entries, treat it as a hard failure and stop. Today `install scenario` silently ignores source-built SDK pins (only released versions resolve via `install_release`). The remedy:

```bash
# Install source-built SDKs separately, then continue.
uv run otdf-sdk-mgr install tip --ref <ref> <sdk>
```

This limitation is tracked at [DSPX-3417](https://virtru.atlassian.net/browse/DSPX-3417). When that ships, the guard becomes redundant — keep it until then.

First `go build` per platform version takes ~30–60s; subsequent runs reuse the cached binary.

### Step 2 — Scaffold the instance directory

```bash
uv run otdf-local instance init <id> --from-scenario xtest/scenarios/<id>.yaml
```

Creates `tests/instances/<id>/`. If the instance already exists, the command is a no-op for existing files. Double-check with `uv run otdf-local instance ls` first to avoid surprising the user with overwrites.

### Step 2.5 — Bootstrap PR worktrees (when source-pinned)

A freshly built PR worktree from `install tip --ref pr:N` ships *templates* but not generated dev keys, and lacks the `opentdf.yaml` filename `otdf-local` expects. Running `up` against it produces cryptic Docker "Is a directory" and platform "no such file" errors. Pre-flight the seed files:

```bash
bash ${CLAUDE_PLUGIN_ROOT:-.}/skills/scenario-up/scripts/bootstrap-pr-worktree.sh xtest/scenarios/<id>.yaml
```

Script behaviour: for each `source.ref` pin in the scenario, resolve the dist's worktree via its `.version` sidecar; check that `kas-*.pem`, `keys/{ca.jks,localhost.crt,localhost.key}`, and `opentdf.yaml` exist as *files* (not Docker-created empty dirs). On miss it generates / copies from `xtest/platform/src/main/` / suggests `bash .github/scripts/init-temp-keys.sh`. Output is tab-separated; review the rows where `action != kept` before proceeding.

Skip this step for scenarios pinned entirely on `dist:` (released versions) — those use pre-baked artifacts and don't need seeding.

[DSPX-3416](https://virtru.atlassian.net/browse/DSPX-3416) tracks moving this bootstrap into `otdf-local up` itself. Until it lands, run the script.

### Step 3 — Bring it up

```bash
uv run otdf-local --instance <id> up
```

Then poll status until everything is healthy (do not proceed before this succeeds):

```bash
uv run otdf-local --instance <id> status --json
```

If any service stays unhealthy after ~60 seconds, surface the relevant log via `uv run otdf-local --instance <id> logs <service> -n 50` and report the failure mode rather than retrying blindly.

## Source-build env knobs

When the scenario pins source-built artifacts (`source.ref` on platform / KAS / SDKs), two env-var overrides are temporarily required for `scenario-run`. Note them now so the user has them ready:

```bash
# Tell xtest which otdfctl binary to use (the slug under xtest/sdk/go/dist/).
export OTDFCTL_HEADS='["refs--pull--<N>--head"]'

# Make tdfs.get_platform_features() enable in-flight feature flags whose semver
# gate is in the future; PR builds self-report old versions.
export PLATFORM_VERSION=0.17.0
```

These workarounds are tracked at [DSPX-3418](https://virtru.atlassian.net/browse/DSPX-3418) (`OTDFCTL_HEADS` → CLI flag) and [DSPX-3419](https://virtru.atlassian.net/browse/DSPX-3419) (auto-derive `PLATFORM_VERSION`). When either lands, remove the corresponding line.

## Output

Once healthy, report:
- The instance name and which ports it occupies (look at `instance.yaml`'s `ports.base`).
- The path to `<id>.installed.json` (so `scenario-run` can find it).
- Any unusual rows from the bootstrap probe (e.g. "seeded `keys/ca.jks` from main worktree").
- The next command the user is likely to run: `scenario-run xtest/scenarios/<id>.yaml`.

## Additional Resources

### Script

- **`scripts/bootstrap-pr-worktree.sh`** — pre-flights a PR worktree's seed files before `otdf-local up`. Takes one positional argument: the scenario YAML path. Tab-separated stdout. Idempotent — safe to re-run.
