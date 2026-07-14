# otdf-local - Agent Operational Guide

This guide covers operational procedures for managing the test environment with `otdf-local`. For command reference, see [README.md](README.md).

**Depends on `otdf-sdk-mgr`.** `otdf-local` launches binaries that `otdf-sdk-mgr install platform` (or `otdf-sdk-mgr install scenario`) writes into `xtest/platform/dist/`. If `otdf-local up` complains that a binary is missing, run the installer first.

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
- Multi-strategy ERS platform: 8090 (backed by ers-postgres on 5433)
- KAS: alpha=8181, beta=8282, gamma=8383, delta=8484, km1=8585, km2=8686

## Multi-strategy ERS platform

`otdf-local up` boots a **second `platform` process** (`platform-ers-ms`)
on port 8090 alongside the default Keycloak-ERS platform. It runs with
`entityresolution: mode: multi-strategy` and a SQL provider pointed at the
`ers-postgres` container (docker compose profile `ers-test`, port 5433).
Both platforms share the same policy DB, KAS keys, and cryptoProvider
config — only the entity-resolution block differs. This mirrors the
multi-KAS pattern: extra infrastructure is always up; tests that don't
reference the ers-ms fixtures are unaffected.

- Template config: `xtest/platform-configs/opentdf-multistrategy.yaml`.
- Generated config: `xtest/tmp/config/opentdf-ers-ms.yaml`.
- Log file: `xtest/tmp/logs/platform-ers-ms.log`.
- Env vars exported by `otdf-local env`: `PLATFORMURL_ERS_MS`, `PLATFORM_ERS_MS_LOG_FILE`.
- Restart just this instance: `uv run otdf-local restart platform-ers-ms`.

The seed row for the multi-strategy SQL provider (`INSERT INTO
ers_attributes VALUES ('opentdf', 'finance')`) is applied during the
`provision` step and is idempotent, so `otdf-local restart` is safe.

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
cd platform && go run ./service start
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

Add to `platform/opentdf-dev.yaml`:
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

# View service logs
uv run otdf-local logs platform -f
uv run otdf-local logs kas-alpha -f
uv run otdf-local logs --grep error

# Or check log files directly
tail -f tmp/logs/platform.log
tail -f tmp/logs/kas-alpha.log

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
- The codebase uses Python with Pydantic for type safety and better error handling
- See `README.md` for project structure

To test changes:
```bash
cd otdf-local
uv run otdf-local down
uv run otdf-local up
uv run otdf-local status
uv run otdf-local logs -f
```
