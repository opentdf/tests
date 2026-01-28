#!/usr/bin/env bash
# Service Manager Bundle
# Pre-configured bundle for service start/stop scripts
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine bundle directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _BUNDLE_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _BUNDLE_FILE="${(%):-%x}"
else
  _BUNDLE_FILE="$0"
fi
_BUNDLE_DIR="$(cd "$(dirname "$_BUNDLE_FILE")" && pwd)"
_LIB_DIR="$(cd "$_BUNDLE_DIR/.." && pwd)"

# Source core modules
# shellcheck source=../core/logging.sh
source "$_LIB_DIR/core/logging.sh"
# shellcheck source=../core/platform.sh
source "$_LIB_DIR/core/platform.sh"
# shellcheck source=../core/paths.sh
source "$_LIB_DIR/core/paths.sh"

# Source health modules
# shellcheck source=../health/checks.sh
source "$_LIB_DIR/health/checks.sh"
# shellcheck source=../health/waits.sh
source "$_LIB_DIR/health/waits.sh"

# Source service modules
# shellcheck source=../services/kas-utils.sh
source "$_LIB_DIR/services/kas-utils.sh"

# Source config modules
# shellcheck source=../config/yaml.sh
source "$_LIB_DIR/config/yaml.sh"

# Export configuration (from original common.sh)
SCRIPTS_DIR="$(get_scripts_dir)"
XTEST_DIR="$(get_xtest_dir)"
PLATFORM_DIR="$(get_platform_dir)"
LOGS_DIR="$(get_logs_dir)"

export SCRIPTS_DIR XTEST_DIR PLATFORM_DIR LOGS_DIR

# tmux session name
TMUX_SESSION="xtest"
export TMUX_SESSION

# Service ports
KEYCLOAK_PORT=8888
POSTGRES_PORT=5432
PLATFORM_PORT=8080

export KEYCLOAK_PORT POSTGRES_PORT PLATFORM_PORT

# KAS instances configuration (matching CI workflow naming)
# Format: name=port
declare -A KAS_CONFIG=(
  [alpha]=8181  # KASURL1
  [beta]=8282   # KASURL2
  [gamma]=8383  # KASURL3
  [delta]=8484  # KASURL4
  [km1]=8585    # KASURL5, key management enabled
  [km2]=8686    # KASURL6, key management enabled
)

# Key management KAS instances
KM_KAS_INSTANCES=("km1" "km2")

# Health check endpoints
KEYCLOAK_HEALTH="http://localhost:${KEYCLOAK_PORT}/auth/realms/master"
PLATFORM_HEALTH="http://localhost:${PLATFORM_PORT}/healthz"

export KEYCLOAK_HEALTH PLATFORM_HEALTH
