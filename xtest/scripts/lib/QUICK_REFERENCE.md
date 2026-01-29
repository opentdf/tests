# Shell Scripts Library - Quick Reference

## Import Bundles

```bash
# Service management scripts (kas-start.sh, platform-start.sh, docker-up.sh, provision.sh)
source "$SCRIPT_DIR/../lib/bundles/service-manager.sh"

# Test execution scripts (local-test.sh, cleanup.sh)
source "$SCRIPT_DIR/lib/bundles/test-runner.sh"

# Setup scripts (init-keys.sh, trust-cert.sh)
source "$SCRIPT_DIR/../lib/bundles/dev-setup.sh"
```

## Common Functions

### Logging
```bash
log_info "Starting service..."         # Blue [INFO]
log_success "Service started"          # Green [OK]
log_warn "Port already in use"         # Yellow [WARN]
log_error "Failed to connect"          # Red [ERROR] to stderr

# Debug/trace (require XTEST_LOGLEVEL=debug or trace)
export XTEST_LOGLEVEL=debug
log_debug "Detailed debug info"        # Cyan [DEBUG]
log_trace "Trace information"          # Cyan [TRACE]
log_traced_call curl http://localhost:8080  # Log and execute
```

### Prerequisites & Health Checks
```bash
check_prerequisites                    # Check go, docker, tmux, yq, curl
check_command docker                   # Check single command

wait_for_health "http://localhost:8080/healthz" "Platform" 60
wait_for_port 8080 "Platform" 30
port_in_use 8080 && log_error "Port in use"
```

### Platform Detection
```bash
is_macos && log_info "Running on macOS"
is_linux && log_info "Running on Linux"
is_wsl && log_warn "Running on WSL"

has_command brew && brew_prefix="$(get_brew_prefix)"
cpu_count="$(get_cpu_count)"
```

### Path Utilities
```bash
XTEST_DIR="$(get_xtest_dir)"
LOGS_DIR="$(get_logs_dir)"
ensure_logs_dir                        # Create logs dir if needed
ensure_dir "/path/to/dir"              # Create any directory
```

### tmux Management
```bash
create_session                         # Create new tmux session
create_window "platform"               # Create window
run_in_window "platform" "go run main.go"  # Run command
wait_for_window_text "platform" "Server started" 60
interrupt_window "platform"            # Send Ctrl-C
kill_window "platform"
kill_session                           # Kill entire session
attach_session                         # Attach to session
```

### KAS Utilities
```bash
config_path="$(get_kas_config_path "alpha")"  # Get config file path
is_km_kas "km1" && log_info "Key management KAS"
root_key="$(generate_root_key)"       # Generate 64-char hex key
```

### YAML Manipulation
```bash
yq_check || exit 1                     # Check yq installed
yq_set "config.yaml" ".server.port" "8080"
port="$(yq_get "config.yaml" ".server.port")"
update_yaml_port "config.yaml" 9090
copy_config "template.yaml" "config.yaml"
```

## Environment Variables

### Configuration (auto-exported by bundles)
```bash
SCRIPTS_DIR          # scripts directory
XTEST_DIR            # tests/xtest directory
PLATFORM_DIR         # platform directory
LOGS_DIR             # tests/xtest/logs directory
TMUX_SESSION         # "xtest"
KEYCLOAK_PORT        # 8888
POSTGRES_PORT        # 5432
PLATFORM_PORT        # 8080
KEYCLOAK_HEALTH      # http://localhost:8888/auth/realms/master
PLATFORM_HEALTH      # http://localhost:8080/healthz
```

### KAS Configuration
```bash
# Associative array
declare -A KAS_CONFIG=(
  [alpha]=8181  [beta]=8282   [gamma]=8383
  [delta]=8484  [km1]=8585    [km2]=8686
)

# Key management instances array
KM_KAS_INSTANCES=("km1" "km2")

# Usage
port="${KAS_CONFIG[alpha]}"            # Get port for KAS instance
```

### Logging Control
```bash
XTEST_LOGLEVEL=quiet     # Suppress all output
XTEST_LOGLEVEL=error     # Show only errors
XTEST_LOGLEVEL=warning   # Show errors and warnings
XTEST_LOGLEVEL=info      # Show info, warnings, errors (default)
XTEST_LOGLEVEL=debug     # Show debug messages
XTEST_LOGLEVEL=trace     # Show all messages including traces
```

## Migration Patterns

### Old Style
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/tmux-helpers.sh"
```

### New Style (Bundles)
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/bundles/service-manager.sh"  # or test-runner.sh or dev-setup.sh
```

### New Style (Individual Modules)
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
source "$LIB_DIR/core/logging.sh"
source "$LIB_DIR/core/paths.sh"
source "$LIB_DIR/health/checks.sh"
```

## Testing

### Run All Tests
```bash
cd tests/xtest/scripts/lib
bats core/*.bats health/*.bats services/*.bats config/*.bats
```

### Run Specific Module Tests
```bash
bats core/logging.bats
bats health/checks.bats
bats services/kas-utils.bats
```

### Check Syntax
```bash
bash -n script.sh
shellcheck script.sh
```

## Shell Compatibility

### Error Handling
```bash
# Library files do NOT set shell options
# Consumer scripts control their own error handling

# Option 1: Explicit checking
if ! check_command docker; then
  exit 1
fi

# Option 2: Use with set -e
set -euo pipefail
check_command docker  # Will exit if fails
```

### Cross-Shell Sourcing
```bash
# In consumer scripts - works in bash and zsh
if [ -n "${BASH_SOURCE:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
elif [ -n "${ZSH_VERSION:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${(%):-%N}")" && pwd)"
else
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi
```

## Common Patterns

### Service Startup Script
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/bundles/service-manager.sh"

log_info "Starting service..."
check_prerequisites
ensure_logs_dir

# Start service
run_service &

# Wait for health
wait_for_health "$SERVICE_HEALTH" "Service" 60
log_success "Service started successfully"
```

### Test Runner Script
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/bundles/test-runner.sh"

log_info "Running tests..."
check_prerequisites

create_session
create_window "tests"
run_in_window "tests" "pytest tests/"

wait_for_window_text "tests" "passed" 300
log_success "Tests completed"
```

### Setup Script
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/bundles/dev-setup.sh"

log_info "Setting up development environment..."

if is_macos; then
  log_info "Installing dependencies with Homebrew..."
  brew install yq tmux
elif is_linux; then
  log_info "Installing dependencies with apt..."
  sudo apt-get install yq tmux
fi

ensure_dir "$XTEST_DIR/logs"
log_success "Setup complete"
```

## Troubleshooting

### Import Error
```bash
# Problem: source: file not found
# Solution: Check relative path from script to lib directory

# From scripts/services/kas-start.sh:
source "$SCRIPT_DIR/../lib/bundles/service-manager.sh"

# From scripts/local-test.sh:
source "$SCRIPT_DIR/lib/bundles/test-runner.sh"
```

### Function Not Found
```bash
# Problem: command not found: log_info
# Solution: Ensure bundle is sourced before using functions

source "$SCRIPT_DIR/lib/bundles/service-manager.sh"
log_info "Now it works"
```

### Log Level Not Working
```bash
# Problem: Debug messages not showing
# Solution: Export XTEST_LOGLEVEL before sourcing library

export XTEST_LOGLEVEL=debug
source "$SCRIPT_DIR/lib/bundles/service-manager.sh"
log_debug "Now visible"
```

## Documentation

- **Full Reference:** `lib/README.md`
- **Implementation Details:** `lib/IMPLEMENTATION_SUMMARY.md`
- **This Quick Reference:** `lib/QUICK_REFERENCE.md`

## Support

File issues in the repository or contact the platform team.
