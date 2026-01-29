# lmgmt - OpenTDF Test Environment Manager

A Python CLI for managing the OpenTDF test environment, providing a cleaner alternative to the existing shell scripts.

## Installation

```bash
cd tests/xtest/lmgmt
uv sync
```

## Quick Start

```bash
# Start all services
uv run lmgmt up

# Check status
uv run lmgmt status

# View logs
uv run lmgmt logs -f

# Stop all services
uv run lmgmt down
```

## Commands

### `up` - Start Environment

Start all or specific services.

```bash
# Start everything (docker, platform, all KAS instances)
lmgmt up

# Start only Docker services
lmgmt up --services docker

# Start without waiting for health checks
lmgmt up --no-wait

# Start without running provisioning
lmgmt up --no-provision
```

### `down` - Stop Environment

```bash
# Stop all services
lmgmt down

# Stop and clean up logs/configs
lmgmt down --clean
```

### `ls` - List Services

```bash
# List running services
lmgmt ls

# List all services (including stopped)
lmgmt ls --all

# Output as JSON
lmgmt ls --json
```

### `status` - Show Status

```bash
# Show current status with health checks
lmgmt status

# Output as JSON
lmgmt status --json

# Watch mode (updates every second)
lmgmt status --watch
```

### `logs` - View Logs

```bash
# Show recent logs from all services
lmgmt logs

# Follow logs (like tail -f)
lmgmt logs -f

# Show logs from specific service
lmgmt logs platform
lmgmt logs kas-alpha

# Show more lines
lmgmt logs -n 100

# Filter by pattern
lmgmt logs --grep error
```

### `restart` - Restart Service

```bash
# Restart platform
lmgmt restart platform

# Restart a KAS instance
lmgmt restart kas-alpha

# Restart Docker services
lmgmt restart docker
```

### `provision` - Run Provisioning

```bash
# Run all provisioning
lmgmt provision

# Provision only Keycloak
lmgmt provision keycloak

# Provision only fixtures
lmgmt provision fixtures
```

### `clean` - Clean Up

```bash
# Clean generated configs and logs
lmgmt clean

# Clean but keep logs
lmgmt clean --keep-logs
```

## Services Managed

| Service | Port | Type | Description |
|---------|------|------|-------------|
| keycloak | 8888 | Docker | Authentication |
| postgres | 5432 | Docker | Database |
| platform | 8080 | Subprocess | Main OpenTDF platform |
| kas-alpha | 8181 | Subprocess | Standard KAS |
| kas-beta | 8282 | Subprocess | Standard KAS |
| kas-gamma | 8383 | Subprocess | Standard KAS |
| kas-delta | 8484 | Subprocess | Standard KAS |
| kas-km1 | 8585 | Subprocess | Key management KAS |
| kas-km2 | 8686 | Subprocess | Key management KAS |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LMGMT_PLATFORM_URL` | http://localhost:8080 | Platform URL |
| `LMGMT_KEYCLOAK_URL` | http://localhost:8888 | Keycloak URL |
| `LMGMT_HEALTH_TIMEOUT` | 60 | Health check timeout (seconds) |
| `LMGMT_LOG_LEVEL` | info | Log level |

## Development

Run tests:

```bash
# Unit tests
uv run pytest tests/test_health.py -v

# Integration tests (requires Docker)
uv run pytest tests/test_integration.py -v -m integration
```

## Project Structure

```
lmgmt/
├── src/lmgmt/
│   ├── cli.py              # Typer CLI commands
│   ├── config/
│   │   ├── ports.py        # Port constants
│   │   └── settings.py     # Pydantic settings
│   ├── services/
│   │   ├── base.py         # Service ABC
│   │   ├── docker.py       # Docker compose management
│   │   ├── platform.py     # Platform service
│   │   ├── kas.py          # KAS instance management
│   │   └── provisioner.py  # Keycloak/fixtures provisioning
│   ├── health/
│   │   ├── checks.py       # HTTP/port health checks
│   │   └── waits.py        # Wait-for-ready utilities
│   ├── process/
│   │   ├── manager.py      # Subprocess lifecycle
│   │   └── logs.py         # Log aggregation
│   └── utils/
│       ├── yaml.py         # YAML manipulation
│       ├── keys.py         # Key generation
│       └── console.py      # Rich console helpers
└── tests/
    ├── test_health.py      # Unit tests
    └── test_integration.py # Integration tests
```

## Comparison with Shell Scripts

This CLI replaces the functionality of these scripts (now removed):
- `scripts/local-test.sh` (removed) → `lmgmt up`, `lmgmt down`, `lmgmt status`
- `scripts/cleanup.sh` (removed) → `lmgmt clean`

And deprecates these service scripts (still present but deprecated):
- `scripts/services/docker-up.sh` → `lmgmt up --services docker`
- `scripts/services/platform-start.sh` → `lmgmt up --services platform`
- `scripts/services/kas-start.sh` → `lmgmt up --services kas`

Benefits over shell scripts:
- Type-safe configuration with Pydantic
- Better error handling and reporting
- Rich terminal output with progress indicators
- Structured logging and log aggregation
- Easier to test and maintain
