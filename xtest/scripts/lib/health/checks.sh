#!/usr/bin/env bash
# Prerequisites and health check utilities
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _CHECKS_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _CHECKS_FILE="${(%):-%x}"
else
  _CHECKS_FILE="$0"
fi
_CHECKS_DIR="$(cd "$(dirname "$_CHECKS_FILE")" && pwd)"

# Source logging if available
if [ -f "$_CHECKS_DIR/../core/logging.sh" ]; then
  # shellcheck source=../core/logging.sh
  source "$_CHECKS_DIR/../core/logging.sh"
fi

# Check if a command exists
check_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    if type log_error >/dev/null 2>&1; then
      log_error "Required command not found: $cmd"
    else
      echo "ERROR: Required command not found: $cmd" >&2
    fi
    return 1
  fi
  return 0
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

  if type log_info >/dev/null 2>&1; then
    log_info "Waiting for $name to be healthy..."
  fi

  while [ "$attempt" -le "$max_attempts" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      if type log_success >/dev/null 2>&1; then
        log_success "$name is healthy"
      fi
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  if type log_error >/dev/null 2>&1; then
    log_error "$name failed to become healthy after $max_attempts seconds"
  fi
  return 1
}
