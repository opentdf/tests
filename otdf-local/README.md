# otdf-local - OpenTDF Test Environment Manager

A Python CLI for managing the OpenTDF test environment, providing a cleaner alternative to the existing shell scripts.

## Installation

```bash
cd tests/otdf-local
uv sync
```

## Global Installation with Tab Completion

For convenience, you can install `otdf-local` globally and enable tab completion:

```bash
cd tests/otdf-local
uv tool install --editable .
otdf-local --install-completion
```

This makes `otdf-local` available globally. You can now run `otdf-local` from any directory.

To uninstall:
```bash
uv tool uninstall otdf-local
```

**Using Tab Completion:**
```bash
otdf-local <TAB>          # Shows available commands
otdf-local logs <TAB>     # Shows service names
otdf-local restart <TAB>  # Shows restartable services
```

## Quick Start

```bash
# Start all services
uv run otdf-local up

# Check status
uv run otdf-local status

# View logs
uv run otdf-local logs -f

# Stop all services
uv run otdf-local down
```

## Commands

### `up` - Start Environment

Start all or specific services.

```bash
# Start everything (docker, platform, all KAS instances)
otdf-local up

# Start only Docker services
otdf-local up --services docker

# Start without running provisioning
otdf-local up --no-provision
```

### `down` - Stop Environment

```bash
# Stop all services
otdf-local down

# Stop and clean up logs/configs
otdf-local down --clean
```

### `ls` - List Services

```bash
# List running services
otdf-local ls

# List all services (including stopped)
otdf-local ls --all

# Output as JSON
otdf-local ls --json
```

### `status` - Show Status

```bash
# Show current status with health checks
otdf-local status

# Output as JSON
otdf-local status --json

# Watch mode (updates every second)
otdf-local status --watch
```

### `logs` - View Logs

```bash
# Show recent logs from all services
otdf-local logs

# Follow logs (like tail -f)
otdf-local logs -f

# Show logs from specific service
otdf-local logs platform
otdf-local logs kas-alpha

# Show more lines
otdf-local logs -n 100

# Filter by pattern
otdf-local logs --grep error
```

### `restart` - Restart Service

```bash
# Restart platform
otdf-local restart platform

# Restart a KAS instance
otdf-local restart kas-alpha

# Restart Docker services
otdf-local restart docker
```

### `provision` - Run Provisioning

```bash
# Run all provisioning
otdf-local provision

# Provision only Keycloak
otdf-local provision keycloak

# Provision only fixtures
otdf-local provision fixtures
```

### `env` - Configure Shell for pytest

Export environment variables needed by pytest (log file paths, etc.):

```bash
# Set up environment for running tests
eval $(otdf-local env)

# Output as JSON
otdf-local env --format json
```

### `clean` - Clean Up

```bash
# Clean generated configs and logs
otdf-local clean

# Clean but keep logs
otdf-local clean --keep-logs
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
| `OTDF_LOCAL_PLATFORM_URL` | http://localhost:8080 | Platform URL |
| `OTDF_LOCAL_KEYCLOAK_URL` | http://localhost:8888 | Keycloak URL |
| `OTDF_LOCAL_HEALTH_TIMEOUT` | 60 | Health check timeout (seconds) |
| `OTDF_LOCAL_LOG_LEVEL` | info | Log level |

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
otdf-local/
├── src/otdf_local/
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
