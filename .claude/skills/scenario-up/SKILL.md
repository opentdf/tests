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

Creates `tests/instances/<id>/` and **self-provisions the bootstrap bundle**: generates the Keycloak TLS pair + `keys/ca.jks` truststore, creates `kas-*.pem` keys, and copies the platform's `opentdf-dev.yaml` (or `opentdf-example.yaml`) into `instances/<id>/opentdf.yaml` with a freshly generated `services.kas.root_key`. Idempotent — existing files are preserved, so the per-instance root key survives re-runs. Double-check with `uv run otdf-local instance ls` first to avoid surprising the user with overwrites.

### Step 3 — Bring it up

```bash
uv run otdf-local --instance <id> up
```

Then poll status until everything is healthy (do not proceed before this succeeds):

```bash
uv run otdf-local --instance <id> status --json
```

If any service stays unhealthy after ~60 seconds, surface the relevant log via `uv run otdf-local --instance <id> logs <service> -n 50` and report the failure mode rather than retrying blindly.

Once healthy, sanity-check the env exports `scenario-run` will rely on:

```bash
uv run otdf-local --instance <id> env --format json | jq '{PLATFORM_DIR,PLATFORMURL,SCHEMA_FILE,OT_ROOT_KEY}'
```

All four must be non-null. If `OT_ROOT_KEY` is null, the instance's `opentdf.yaml` is missing or didn't get a `services.kas.root_key` written (re-run `instance init` to refresh).

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
- The next command the user is likely to run: `scenario-run xtest/scenarios/<id>.yaml`.
