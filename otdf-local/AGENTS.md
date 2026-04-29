# otdf-local - Agent Operational Guide

This guide covers operational procedures for managing the test environment with `otdf-local`. For command reference, see [README.md](README.md).

## Environment Setup for pytest

```bash
cd otdf-local
uv run otdf-local env > ../xtest/local.env   # Generate local.env
cd ../xtest
set -a && source local.env && set +a         # Source the environment
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

**Manual configuration** (if not using otdf-local):

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
