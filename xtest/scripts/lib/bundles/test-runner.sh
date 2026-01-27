#!/usr/bin/env bash
# Test Runner Bundle
# Pre-configured bundle for test execution scripts
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
# shellcheck source=../core/paths.sh
source "$_LIB_DIR/core/paths.sh"

# Source health modules
# shellcheck source=../health/checks.sh
source "$_LIB_DIR/health/checks.sh"
# shellcheck source=../health/waits.sh
source "$_LIB_DIR/health/waits.sh"

# Source service modules
# shellcheck source=../services/tmux.sh
source "$_LIB_DIR/services/tmux.sh"

# Export configuration
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
PLATFORM_PORT=8080

export KEYCLOAK_PORT PLATFORM_PORT

# KAS instances configuration
declare -A KAS_CONFIG=(
  [alpha]=8181
  [beta]=8282
  [gamma]=8383
  [delta]=8484
  [km1]=8585
  [km2]=8686
)
