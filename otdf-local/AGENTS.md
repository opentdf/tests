# otdf-local - Agent Operational Guide

This guide covers operational procedures for managing the test environment with `otdf-local`. For command reference, see [README.md](README.md).

**Depends on a platform source tree.** `otdf-local` runs `go run ./service` from the first of:

1. `platform/` beside `xtest/` (a hand-cloned checkout)
2. the single worktree under `xtest/platform/src/<ref>/`, from `otdf-sdk-mgr install tip|release platform` (the `scripts--*` helper checkout is ignored)
3. `platform/` beside a further ancestor (e.g. a multi-repo workspace)

If several refs are installed and there is no sibling checkout, it refuses to guess: set `OTDF_LOCAL_PLATFORM_DIR` to the one to run. `otdf-local up` prints the directory it chose.

Config is generated from `opentdf.yaml` into `opentdf-dev.yaml` on every `up`/`restart`. If `opentdf.yaml` is missing it is seeded from the committed `opentdf-dev.yaml` (git HEAD).

## Environment Setup for pytest

```bash
cd otdf-local
eval $(uv run otdf-local env)         # Sets PLATFORM_LOG_FILE, KAS_*_LOG_FILE, etc.
uv run otdf-local env --format json   # Output as JSON
cd ../xtest
uv run pytest --sdks go -v
```

## Service Ports

Auto-configured by otdf-local:
- Keycloak: 8888, Postgres: 5432, Platform: 8080
- KAS: alpha=8181, beta=8282, gamma=8383, delta=8484, km1=8585, km2=8686

## Restart Procedures

### Full Environment Restart
```bash
cd otdf-local

uv run otdf-local down
uv run otdf-local up

# Or with cleanup
uv run otdf-local down --clean
uv run otdf-local up
```

### Service-Specific Restart
```bash
cd otdf-local

uv run otdf-local restart platform
uv run otdf-local restart kas-alpha
uv run otdf-local restart kas-km1
uv run otdf-local restart docker
```

### Manual Restart (Emergency)

Only use when otdf-local itself is broken or unresponsive:

```bash
pkill -9 -f "go run ./service start"
pkill -9 -f "opentdf-kas"
cd platform && docker compose down 2>/dev/null || true
sleep 5
cd otdf-local && uv run otdf-local up
```

### Platform Only (Manual)
```bash
pkill -9 -f "go run ./service start"
sleep 2
cd "$(uv run otdf-local env --format json | jq -r .PLATFORM_DIR)" && go run ./service start
```

## Viewing Service Logs

**Via otdf-local:**
```bash
uv run otdf-local logs -f                    # Follow all
uv run otdf-local logs platform -f           # Follow specific service
uv run otdf-local logs --grep "error" -f     # Filter
```

**Via log files:**
```bash
tail -f tmp/logs/platform.log
tail -f tmp/logs/kas-alpha.log
tail -f tmp/logs/kas-km1.log
```

## Golden Key Auto-Configuration

When using `otdf-local up` or `otdf-local restart platform`, golden keys are automatically configured:
1. `otdf-local` reads `xtest/extra-keys.json` containing the `golden-r1` key
2. Key files are extracted to `platform/golden-r1-private.pem` and `platform/golden-r1-cert.pem`
3. The key is added to `cryptoProvider.standard.keys` in the platform config
4. A legacy keyring entry is added to `services.kas.keyring`

**Manual configuration** (emergency fallback only — drifts from current platform schema; check `platform/opentdf-dev.yaml.example` if this fails):

Add to `opentdf.yaml` in the platform directory (`opentdf-dev.yaml` is regenerated from it on every `up`/`restart`):
```yaml
services:
  kas:
    keyring:
      - kid: golden-r1
        alg: rsa:2048
        legacy: true
server:
  cryptoProvider:
    standard:
      keys:
        - kid: golden-r1
          alg: rsa:2048
          private: golden-r1-private.pem
          cert: golden-r1-cert.pem
```

Extract key files:
```bash
jq -r '.[0].privateKey' xtest/extra-keys.json > platform/golden-r1-private.pem
jq -r '.[0].cert' xtest/extra-keys.json > platform/golden-r1-cert.pem
```

## Troubleshooting

```bash
cd otdf-local

# Check service status
uv run otdf-local status
uv run otdf-local ls --all

# Logs: see "Viewing Service Logs" above

# Kill stuck processes
pkill -9 -f "go run ./service start"

# Check port availability
lsof -i :8080   # Platform
lsof -i :8181   # KAS alpha
lsof -i :8888   # Keycloak
```

## Extending otdf-local

The shell scripts in `scripts/lib/` are deprecated. For new automation:
- Extend the `otdf-local` Python CLI instead of creating new shell scripts

To test changes:
```bash
cd otdf-local
uv run otdf-local down
uv run otdf-local up
uv run otdf-local status
uv run otdf-local logs -f
```
