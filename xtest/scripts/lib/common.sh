#!/usr/bin/env bash
# Shared configuration and utilities for local xtest execution

set -euo pipefail

# Determine script directories (use _COMMON_DIR to avoid overwriting caller's SCRIPT_DIR)
_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$_COMMON_DIR/.." && pwd)"
XTEST_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
PLATFORM_DIR="$(cd "$XTEST_DIR/../../platform" && pwd)"

# tmux session name
TMUX_SESSION="xtest"

# Logs directory
LOGS_DIR="$XTEST_DIR/logs"

# Service ports
KEYCLOAK_PORT=8888
POSTGRES_PORT=5432
PLATFORM_PORT=8080

# KAS instances configuration (matching CI workflow naming)
# Format: name=port
# shellcheck disable=SC2034  # Used by external scripts that source this file
declare -A KAS_CONFIG=(
    [alpha]=8181    # KASURL1
    [beta]=8282     # KASURL2
    [gamma]=8383    # KASURL3
    [delta]=8484    # KASURL4
    [km1]=8585      # KASURL5, key management enabled
    [km2]=8686      # KASURL6, key management enabled
)

# Key management KAS instances
KM_KAS_INSTANCES=("km1" "km2")

# Health check endpoints
# Keycloak: use the master realm endpoint as a readiness check
# (management health endpoints aren't enabled in this docker-compose setup)
KEYCLOAK_HEALTH="http://localhost:${KEYCLOAK_PORT}/auth/realms/master"
PLATFORM_HEALTH="http://localhost:${PLATFORM_PORT}/healthz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Check if a command exists
check_command() {
    local cmd="$1"
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command not found: $cmd"
        return 1
    fi
}

# Check all prerequisites
check_prerequisites() {
    local missing=0
    for cmd in go docker tmux yq curl; do
        if ! check_command "$cmd"; then
            missing=1
        fi
    done
    return $missing
}

# Wait for a health endpoint to return 200
wait_for_health() {
    local url="$1"
    local name="$2"
    local max_attempts="${3:-60}"
    local attempt=1

    log_info "Waiting for $name to be healthy..."
    while [ "$attempt" -le "$max_attempts" ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            log_success "$name is healthy"
            return 0
        fi
        sleep 1
        ((attempt++))
    done
    log_error "$name failed to become healthy after $max_attempts seconds"
    return 1
}

# Wait for a port to be listening
wait_for_port() {
    local port="$1"
    local name="$2"
    local max_attempts="${3:-30}"
    local attempt=1

    log_info "Waiting for $name on port $port..."
    while [ "$attempt" -le "$max_attempts" ]; do
        if nc -z localhost "$port" 2>/dev/null; then
            log_success "$name is listening on port $port"
            return 0
        fi
        sleep 1
        ((attempt++))
    done
    log_error "$name failed to start on port $port after $max_attempts seconds"
    return 1
}

# Check if port is in use
port_in_use() {
    local port="$1"
    nc -z localhost "$port" 2>/dev/null
}

# Ensure logs directory exists
ensure_logs_dir() {
    mkdir -p "$LOGS_DIR"
}

# Get KAS config file path
get_kas_config_path() {
    local name="$1"
    echo "$XTEST_DIR/logs/kas-${name}.yaml"
}

# Check if this is a key management KAS
# Check if this is a key management KAS (literal string match intentional)
# shellcheck disable=SC2076
is_km_kas() {
    local name="$1"
    [[ " ${KM_KAS_INSTANCES[*]} " =~ " ${name} " ]]
}

# Generate root key for key management KAS instances
generate_root_key() {
    openssl rand -hex 32
}

# Export variables for child scripts
export SCRIPTS_DIR XTEST_DIR PLATFORM_DIR
export TMUX_SESSION LOGS_DIR
export KEYCLOAK_PORT POSTGRES_PORT PLATFORM_PORT
export KEYCLOAK_HEALTH PLATFORM_HEALTH
