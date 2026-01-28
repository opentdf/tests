# xtest Shell Script Library

Modular shell script library for xtest local development and CI/CD. This library provides reusable utilities for service management, testing, and development workflows with full bash and zsh compatibility.

## Quick Start

### Use Task Bundles (Recommended)

The easiest way to use this library is through pre-configured bundles:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the service manager bundle (includes logging, health checks, KAS utils, etc.)
source "$SCRIPT_DIR/../lib/bundles/service-manager.sh"

# Now you have access to all functions and configuration
log_info "Starting service..."
check_prerequisites
wait_for_health "$PLATFORM_HEALTH" "Platform" 60
```

### Import Individual Modules

For more granular control, source specific modules:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"

# Source only what you need
source "$LIB_DIR/core/logging.sh"
source "$LIB_DIR/core/paths.sh"
source "$LIB_DIR/health/checks.sh"

# Use the functions
log_info "Checking prerequisites..."
check_prerequisites
```

## Library Structure

```
scripts/lib/
├── README.md                       # This file
├── test_helper.bash                # Shared BATS test utilities
├── core/                           # Core functionality
│   ├── logging.sh                  # Enhanced logging with levels
│   ├── logging.bats                # Tests
│   ├── platform.sh                 # Platform detection (macOS/Linux/WSL)
│   ├── platform.bats              # Tests
│   ├── paths.sh                    # Path resolution utilities
│   └── paths.bats                  # Tests
├── health/                         # Health checks and waiting
│   ├── checks.sh                   # Prerequisites and health checks
│   ├── checks.bats                 # Tests
│   ├── waits.sh                    # Port/service waiting
│   └── waits.bats                  # Tests
├── services/                       # Service-specific utilities
│   ├── tmux.sh                     # tmux session management
│   ├── kas-utils.sh                # KAS-specific utilities
│   └── kas-utils.bats              # Tests
├── config/                         # Configuration management
│   ├── yaml.sh                     # YAML manipulation (yq)
│   └── yaml.bats                   # Tests
├── bundles/                        # Pre-configured module sets
│   ├── service-manager.sh          # For service start/stop scripts
│   ├── test-runner.sh              # For test execution
│   └── dev-setup.sh                # For setup scripts
└── compat.sh                       # Backward compatibility (temporary)
```

## Module Reference

### core/logging.sh

Enhanced logging with configurable levels and colored output.

**Functions:**
- `log_info(message...)` - Log informational message (blue)
- `log_success(message...)` - Log success message (green)
- `log_warn(message...)` - Log warning message (yellow)
- `log_error(message...)` - Log error message to stderr (red)
- `log_debug(message...)` - Log debug message (cyan, requires XTEST_LOGLEVEL=debug)
- `log_trace(message...)` - Log trace message (cyan, requires XTEST_LOGLEVEL=trace)
- `log_traced_call(command...)` - Log and execute command with trace output

**Environment Variables:**
- `XTEST_LOGLEVEL` - Set log level: quiet, error, warning, info (default), debug, trace

**Example:**
```bash
source "$LIB_DIR/core/logging.sh"

log_info "Starting application"
log_success "Service started successfully"

# Enable debug logging
export XTEST_LOGLEVEL=debug
log_debug "Detailed debug information"

# Trace command execution
XTEST_LOGLEVEL=trace log_traced_call curl -sf http://localhost:8080/health
```

### core/platform.sh

Platform detection and compatibility utilities for cross-platform scripts.

**Functions:**
- `is_macos()` - Returns 0 if running on macOS
- `is_linux()` - Returns 0 if running on Linux (not WSL)
- `is_wsl()` - Returns 0 if running on Windows Subsystem for Linux
- `has_command(cmd)` - Returns 0 if command exists in PATH
- `get_sed_inplace()` - Get platform-specific sed in-place flags
- `get_brew_prefix()` - Get Homebrew prefix if available
- `get_cpu_count()` - Get number of CPU cores
- `get_shell_type()` - Get shell type (bash/zsh/unknown)

**Example:**
```bash
source "$LIB_DIR/core/platform.sh"

if is_macos; then
  log_info "Running on macOS"
  brew_prefix="$(get_brew_prefix)"
fi

if has_command docker; then
  log_info "Docker is available"
fi

# Use platform-specific sed
sed_flags="$(get_sed_inplace)"
sed $sed_flags "s/foo/bar/" file.txt
```

### core/paths.sh

Path resolution utilities for consistent directory references.

**Functions:**
- `get_lib_dir()` - Get library directory (scripts/lib)
- `get_scripts_dir()` - Get scripts directory
- `get_xtest_dir()` - Get xtest directory (tests/xtest)
- `get_platform_dir()` - Get platform directory
- `get_logs_dir()` - Get logs directory (tests/xtest/logs)
- `resolve_script_dir()` - Resolve current script directory (bash/zsh compatible)
- `ensure_dir(path)` - Create directory if it doesn't exist
- `ensure_logs_dir()` - Ensure logs directory exists

**Example:**
```bash
source "$LIB_DIR/core/paths.sh"

XTEST_DIR="$(get_xtest_dir)"
LOGS_DIR="$(get_logs_dir)"

ensure_logs_dir
log_info "Logs will be written to $LOGS_DIR"
```

### health/checks.sh

Prerequisites and health check utilities.

**Functions:**
- `check_command(cmd)` - Check if a command exists
- `check_prerequisites()` - Check all required commands (go, docker, tmux, yq, curl)
- `wait_for_health(url, name, max_attempts)` - Wait for health endpoint to return 200

**Example:**
```bash
source "$LIB_DIR/health/checks.sh"

# Check single command
if ! check_command docker; then
  exit 1
fi

# Check all prerequisites
check_prerequisites || exit 1

# Wait for service to be healthy
wait_for_health "http://localhost:8080/healthz" "Platform" 60
```

### health/waits.sh

Port and service waiting utilities.

**Functions:**
- `wait_for_port(port, name, max_attempts)` - Wait for port to be listening
- `port_in_use(port)` - Check if port is in use

**Example:**
```bash
source "$LIB_DIR/health/waits.sh"

# Wait for service to start
wait_for_port 8080 "Platform" 30

# Check if port is already in use
if port_in_use 8080; then
  log_error "Port 8080 is already in use"
  exit 1
fi
```

### services/tmux.sh

tmux session management utilities for local development.

**Environment Variables:**
- `TMUX_SESSION` - Session name (default: "xtest")
- `XTEST_DIR` - xtest directory for window initialization

**Functions:**
- `session_exists()` - Check if tmux session exists
- `create_session()` - Create new tmux session
- `create_window(name, [cmd])` - Create new window
- `run_in_window(window, cmd...)` - Run command in window
- `interrupt_window(window)` - Send Ctrl-C to window
- `kill_window(window)` - Kill specific window
- `kill_session()` - Kill entire session
- `attach_session()` - Attach to session
- `list_windows()` - List all windows
- `get_window_output(window, [lines])` - Get window pane content
- `wait_for_window_text(window, text, [max_attempts])` - Wait for text in window
- `create_all_windows()` - Create standard xtest window layout
- `show_layout_help()` - Show session layout documentation

**Example:**
```bash
source "$LIB_DIR/services/tmux.sh"

# Create session and windows
create_session
create_window "platform"
create_window "tests"

# Run commands
run_in_window "platform" "cd $PLATFORM_DIR && go run cmd/main.go"
run_in_window "tests" "pytest tests/"

# Wait for output
wait_for_window_text "platform" "Server started" 60

# Attach to session
attach_session
```

### services/kas-utils.sh

KAS-specific utilities for configuration and management.

**Environment Variables:**
- `XTEST_DIR` - xtest directory (for config paths)
- `KM_KAS_INSTANCES` - Array of key management KAS instance names

**Functions:**
- `get_kas_config_path(name)` - Get KAS config file path
- `is_km_kas(name)` - Check if this is a key management KAS
- `generate_root_key()` - Generate root key for key management

**Example:**
```bash
source "$LIB_DIR/services/kas-utils.sh"

for kas_name in alpha beta gamma; do
  config_path="$(get_kas_config_path "$kas_name")"

  if is_km_kas "$kas_name"; then
    root_key="$(generate_root_key)"
    yq_set "$config_path" ".keymanagement.rootkey" "\"$root_key\""
  fi
done
```

### config/yaml.sh

YAML manipulation utilities using yq.

**Functions:**
- `yq_check()` - Check if yq is installed
- `yq_set(file, path, value)` - Set value in YAML file
- `yq_get(file, path)` - Get value from YAML file
- `copy_config(source, dest)` - Copy config file with logging
- `update_yaml_port(file, port)` - Update server.port in YAML

**Example:**
```bash
source "$LIB_DIR/config/yaml.sh"

# Check yq availability
yq_check || exit 1

# Manipulate YAML
yq_set "config.yaml" ".server.port" "8080"
port="$(yq_get "config.yaml" ".server.port")"

# Copy and update config
copy_config "config.template.yaml" "config.yaml"
update_yaml_port "config.yaml" 9090
```

## Bundles

Pre-configured module sets for common use cases.

### bundles/service-manager.sh

For service start/stop scripts. Includes:
- Core: logging, platform, paths
- Health: checks, waits
- Services: kas-utils
- Config: yaml
- Full configuration exports (ports, KAS config, health endpoints)

**Use for:** kas-start.sh, platform-start.sh, docker-up.sh, provision.sh

### bundles/test-runner.sh

For test execution scripts. Includes:
- Core: logging, paths
- Health: checks, waits
- Services: tmux
- Test-relevant configuration (ports, KAS config)

**Use for:** local-test.sh, cleanup.sh

### bundles/dev-setup.sh

For development setup scripts. Includes:
- Core: logging, platform, paths
- Minimal configuration (directories only)

**Use for:** init-keys.sh, trust-cert.sh

## Shell Compatibility

### Error Handling

**CRITICAL:** Library files do NOT set shell options (`set -e`, `set -o pipefail`). Consumer scripts control their own error handling behavior.

All library functions use explicit error checking and return codes:

```bash
# Good: explicit error checking
if ! check_command docker; then
  log_error "Docker not found"
  exit 1
fi

# Also good: use with set -e
set -euo pipefail
check_command docker  # Will exit if fails
```

### Cross-Shell Sourcing

All modules use bash/zsh compatible sourcing pattern:

```bash
if [ -n "${BASH_SOURCE:-}" ]; then
  _FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _FILE="${(%):-%x}"
else
  _FILE="$0"
fi
```

### Associative Arrays

KAS configuration uses associative arrays (bash 4+ and zsh):

```bash
declare -A KAS_CONFIG=(
  [alpha]=8181
  [beta]=8282
)

# Access values
port="${KAS_CONFIG[alpha]}"
```

## Cross-Platform Support

### Supported Platforms

- **macOS** - With Homebrew or Nix
- **Linux** - Ubuntu, Debian, RHEL, etc.
- **WSL** - Windows Subsystem for Linux

### Platform Detection

Use `core/platform.sh` for platform-specific code:

```bash
source "$LIB_DIR/core/platform.sh"

if is_macos; then
  # macOS-specific code
  brew install yq
elif is_linux; then
  # Linux-specific code
  sudo apt-get install yq
elif is_wsl; then
  # WSL-specific code
  log_warn "Running on WSL - some features may be limited"
fi
```

### Command Availability

Always check command availability:

```bash
if has_command brew; then
  brew_prefix="$(get_brew_prefix)"
fi

if ! check_command yq; then
  log_error "yq is required but not installed"
  exit 1
fi
```

## Testing

### Running Tests

All modules include BATS unit tests co-located with source files:

```bash
# Run all tests
cd tests/xtest/scripts/lib
bats core/*.bats health/*.bats services/*.bats config/*.bats

# Run specific module tests
bats core/logging.bats
bats health/checks.bats
```

### Test Dependencies

Tests require:
- bats-core
- bats-support (optional, for better assertions)
- bats-assert (optional, for better assertions)

Install on macOS:
```bash
brew install bats-core
brew install bats-support
brew install bats-assert
```

### Writing Tests

Use the test helper for consistent test setup:

```bash
#!/usr/bin/env bats

setup() {
  bats_require_minimum_version 1.5.0
  load ../test_helper.bash
  setup_bats_libs

  # Load module under test
  load module_name.sh
}

@test "function_name returns expected value" {
  run function_name arg1 arg2
  [ "$status" -eq 0 ]
  [[ "$output" == *"expected"* ]]
}
```

## Migration Guide

### From old common.sh

**Old:**
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../lib/tmux-helpers.sh"
```

**New (using bundle):**
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/bundles/service-manager.sh"
```

**New (using individual modules):**
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"
source "$LIB_DIR/core/logging.sh"
source "$LIB_DIR/core/paths.sh"
source "$LIB_DIR/health/checks.sh"
```

### Function Mapping

All functions from common.sh and tmux-helpers.sh are preserved with the same names and signatures:

- `log_info`, `log_success`, `log_warn`, `log_error` - **core/logging.sh**
- `check_command`, `check_prerequisites`, `wait_for_health` - **health/checks.sh**
- `wait_for_port`, `port_in_use` - **health/waits.sh**
- `get_kas_config_path`, `is_km_kas`, `generate_root_key` - **services/kas-utils.sh**
- All tmux functions - **services/tmux.sh**

### Configuration Variables

All environment variables are preserved:
- `SCRIPTS_DIR`, `XTEST_DIR`, `PLATFORM_DIR`, `LOGS_DIR`
- `TMUX_SESSION`
- `KEYCLOAK_PORT`, `POSTGRES_PORT`, `PLATFORM_PORT`
- `KAS_CONFIG` associative array
- `KM_KAS_INSTANCES` array
- `KEYCLOAK_HEALTH`, `PLATFORM_HEALTH`

### Temporary Compatibility Shim

For gradual migration, use `compat.sh`:

```bash
# Provides complete backward compatibility with old common.sh
source "$SCRIPT_DIR/../lib/compat.sh"

# This will log a deprecation warning but work identically
```

**Note:** `compat.sh` will be removed after all scripts are migrated to bundles.

## Development

### Code Style

Format shell scripts with shfmt:

```bash
cd tests/xtest/scripts
shfmt -w -i 2 -ci -sr lib/**/*.sh
```

**Note:** shfmt may report errors on zsh-specific expansions. These are false positives and can be ignored.

### Linting

Run shellcheck on all scripts:

```bash
cd tests/xtest/scripts/lib
shellcheck core/*.sh health/*.sh services/*.sh config/*.sh bundles/*.sh
```

### Adding New Modules

1. Create module file in appropriate directory (core/, health/, services/, config/)
2. Use the standard header with bash/zsh compatible sourcing
3. Do NOT set shell options (no `set -e`, `set -o pipefail`)
4. Use explicit error checking and return codes
5. Source dependencies if needed
6. Create co-located .bats test file
7. Add to appropriate bundle if commonly used
8. Update this README

### CI/CD Integration

Tests and formatting are checked in CI/CD workflow. See `.github/workflows/check.yml`.

## Contributing

### Guidelines

1. **No shell options in libraries** - Consumer scripts manage error handling
2. **Explicit error checking** - All functions return meaningful exit codes
3. **Cross-shell compatibility** - Test in both bash and zsh
4. **Comprehensive tests** - Aim for 80%+ coverage
5. **Inline documentation** - Document complex logic with comments
6. **Platform compatibility** - Test on macOS, Linux, and WSL if possible

### Pull Request Checklist

- [ ] All tests pass (`bats **/*.bats`)
- [ ] Code formatted with shfmt (ignoring zsh expansion warnings)
- [ ] shellcheck passes with no errors
- [ ] Functions documented in this README
- [ ] Cross-shell compatibility verified
- [ ] Appropriate bundle(s) updated if needed

## License

Copyright Virtru Corporation. Internal use only.

## Support

For questions or issues, contact the platform team or file an issue in the repository.
