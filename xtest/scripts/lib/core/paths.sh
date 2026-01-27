#!/usr/bin/env bash
# Path resolution utilities
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _PATHS_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _PATHS_FILE="${(%):-%x}"
else
  _PATHS_FILE="$0"
fi
_PATHS_DIR="$(cd "$(dirname "$_PATHS_FILE")" && pwd)"

# Get library directory (scripts/lib)
get_lib_dir() {
  echo "$(cd "$_PATHS_DIR/.." && pwd)"
}

# Get scripts directory (scripts)
get_scripts_dir() {
  echo "$(cd "$_PATHS_DIR/../.." && pwd)"
}

# Get xtest directory (tests/xtest)
get_xtest_dir() {
  echo "$(cd "$_PATHS_DIR/../../.." && pwd)"
}

# Get platform directory (platform)
get_platform_dir() {
  local xtest_dir
  xtest_dir="$(get_xtest_dir)"
  echo "$(cd "$xtest_dir/../../platform" && pwd)"
}

# Get logs directory (tests/xtest/logs)
get_logs_dir() {
  local xtest_dir
  xtest_dir="$(get_xtest_dir)"
  echo "$xtest_dir/logs"
}

# Resolve script directory safely (for consumer scripts)
# Usage: SCRIPT_DIR="$(resolve_script_dir)"
resolve_script_dir() {
  if [ -n "${BASH_SOURCE:-}" ]; then
    local script_file="${BASH_SOURCE[0]}"
  elif [ -n "${ZSH_VERSION:-}" ]; then
    local script_file="${(%):-%x}"
  else
    local script_file="$0"
  fi

  cd "$(dirname "$script_file")" && pwd
}

# Ensure directory exists (with mkdir -p)
ensure_dir() {
  local dir="$1"
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir"
    return $?
  fi
  return 0
}

# Ensure logs directory exists
ensure_logs_dir() {
  local logs_dir
  logs_dir="$(get_logs_dir)"
  ensure_dir "$logs_dir"
}
