#!/usr/bin/env bash
# Port and service waiting utilities
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _WAITS_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _WAITS_FILE="${(%):-%x}"
else
  _WAITS_FILE="$0"
fi
_WAITS_DIR="$(cd "$(dirname "$_WAITS_FILE")" && pwd)"

# Source logging if available
if [ -f "$_WAITS_DIR/../core/logging.sh" ]; then
  # shellcheck source=../core/logging.sh
  source "$_WAITS_DIR/../core/logging.sh"
fi

# Wait for a port to be listening
wait_for_port() {
  local port="$1"
  local name="$2"
  local max_attempts="${3:-30}"
  local attempt=1

  if type log_info >/dev/null 2>&1; then
    log_info "Waiting for $name on port $port..."
  fi

  while [ "$attempt" -le "$max_attempts" ]; do
    if nc -z localhost "$port" 2>/dev/null; then
      if type log_success >/dev/null 2>&1; then
        log_success "$name is listening on port $port"
      fi
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  if type log_error >/dev/null 2>&1; then
    log_error "$name failed to start on port $port after $max_attempts seconds"
  fi
  return 1
}

# Check if port is in use
port_in_use() {
  local port="$1"
  if nc -z localhost "$port" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}
