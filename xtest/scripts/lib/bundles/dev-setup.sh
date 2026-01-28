#!/usr/bin/env bash
# Dev Setup Bundle
# Pre-configured bundle for development setup scripts
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

# Export minimal configuration
SCRIPTS_DIR="$(get_scripts_dir)"
XTEST_DIR="$(get_xtest_dir)"
PLATFORM_DIR="$(get_platform_dir)"
LOGS_DIR="$(get_logs_dir)"

export SCRIPTS_DIR XTEST_DIR PLATFORM_DIR LOGS_DIR
