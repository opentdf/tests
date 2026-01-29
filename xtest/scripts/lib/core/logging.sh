#!/usr/bin/env bash
# Enhanced logging utilities with level support
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _LOGGING_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  # shellcheck disable=SC2296
  _LOGGING_FILE="${(%):-%x}"
else
  _LOGGING_FILE="$0"
fi
_LOGGING_DIR="$(cd "$(dirname "$_LOGGING_FILE")" && pwd)"

# Color constants
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging levels (higher = more verbose)
# quiet=0, error=1, warning=2, info=3, debug=4, trace=5
declare -A _LOG_LEVELS=(
  [quiet]=0
  [error]=1
  [warning]=2
  [info]=3
  [debug]=4
  [trace]=5
)

# Get current log level (default: info)
_get_log_level() {
  local level="${XTEST_LOGLEVEL:-info}"
  echo "${_LOG_LEVELS[$level]:-3}"
}

# Check if message should be logged at given level
_should_log() {
  local msg_level="$1"
  local current_level
  current_level="$(_get_log_level)"

  if [ "$msg_level" -le "$current_level" ]; then
    return 0
  else
    return 1
  fi
}

# Basic logging functions (from original common.sh)
log_info() {
  if _should_log 3; then
    echo -e "${BLUE}[INFO]${NC} $*"
  fi
}

log_success() {
  if _should_log 3; then
    echo -e "${GREEN}[OK]${NC} $*"
  fi
}

log_warn() {
  if _should_log 2; then
    echo -e "${YELLOW}[WARN]${NC} $*"
  fi
}

log_error() {
  if _should_log 1; then
    echo -e "${RED}[ERROR]${NC} $*" >&2
  fi
}

# Enhanced logging functions (inspired by DSP)
log_debug() {
  if _should_log 4; then
    echo -e "${CYAN}[DEBUG]${NC} $*"
  fi
}

log_trace() {
  if _should_log 5; then
    echo -e "${CYAN}[TRACE]${NC} $*"
  fi
}

# Log a command then execute it
log_traced_call() {
  if _should_log 5; then
    log_trace "Executing: $*"
  fi

  # Execute the command and return its exit code
  "$@"
  local exit_code=$?

  if _should_log 5; then
    log_trace "Command exited with code: $exit_code"
  fi

  return $exit_code
}
