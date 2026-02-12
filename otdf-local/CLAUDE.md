# otdf-local - Agent Operational Guide

This guide covers operational procedures for managing the test environment with `otdf-local`. For command reference, see [README.md](README.md).

## Environment Setup for pytest

```bash
cd tests/otdf-local
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
cd tests/otdf-local

uv run otdf-local down
uv run otdf-local up

# Or with cleanup
uv run otdf-local down --clean
uv run otdf-local up
```

### Service-Specific Restart
```bash
cd tests/otdf-local

uv run otdf-local restart platform
uv run otdf-local restart kas-alpha
uv run otdf-local restart kas-km1
uv run otdf-local restart docker
```

### Manual Restart (Emergency)

Only use when otdf-local itself is broken or unresponsive:

```bash
pkill -9 -f "go.*service.*start"
pkill -9 -f "opentdf-kas"
tmux kill-session -t xtest 2>/dev/null || true
cd platform && docker compose down 2>/dev/null || true
sleep 5
cd tests/otdf-local && uv run otdf-local up
```

### Platform Only (Manual)
```bash
# Via tmux session
tmux attach -t xtest
# Navigate to window 1 (platform)
# Ctrl-B 1 → Ctrl-C → Up arrow + Enter

# Or via kill + restart
pkill -9 -f "go.*service.*start"
sleep 2
cd platform && go run ./service start
```

### Individual KAS (Manual)
```bash
tmux attach -t xtest
# Window numbers: kas-alpha=2, beta=3, gamma=4, delta=5, km1=6, km2=7
# Ctrl-B <number> → Ctrl-C → Up arrow + Enter
```

## Viewing Service Logs

**Via otdf-local:**
```bash
uv run otdf-local logs -f                    # Follow all
uv run otdf-local logs platform -f           # Follow specific service
uv run otdf-local logs --grep "error" -f     # Filter
```

**Via tmux session:**
```bash
tmux attach -t xtest

# Navigate windows
Ctrl-B 0-9     # Switch to window by number
Ctrl-B w       # Show window list
Ctrl-B n/p     # Next/previous window

# Scroll logs
Ctrl-B [       # Enter scroll mode
q              # Exit scroll mode

# Detach
Ctrl-B d
```

**Via log files:**
```bash
tail -f tests/xtest/logs/platform.log
tail -f tests/xtest/logs/kas-alpha.log
tail -f tests/xtest/logs/kas-km1.log
```

## Golden Key Auto-Configuration

When using `otdf-local up` or `otdf-local restart platform`, golden keys are automatically configured:
1. `otdf-local` reads `tests/xtest/extra-keys.json` containing the `golden-r1` key
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
jq -r '.[0].privateKey' tests/xtest/extra-keys.json > platform/golden-r1-private.pem
jq -r '.[0].cert' tests/xtest/extra-keys.json > platform/golden-r1-cert.pem
```

## Troubleshooting

```bash
cd tests/otdf-local

# Check service status
uv run otdf-local status
uv run otdf-local ls --all

# View service logs
uv run otdf-local logs platform -f
uv run otdf-local logs kas-alpha -f
uv run otdf-local logs --grep error

# Or check log files directly
tail -f tests/xtest/logs/platform.log
tail -f tests/xtest/logs/kas-alpha.log

# Kill stuck processes
pkill -9 -f "go.*service.*start"

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
cd tests/otdf-local
uv run otdf-local down
uv run otdf-local up
uv run otdf-local status
uv run otdf-local logs -f
```
