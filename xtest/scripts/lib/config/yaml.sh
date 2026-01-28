#!/usr/bin/env bash
# YAML manipulation utilities
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _YAML_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _YAML_FILE="${(%):-%x}"
else
  _YAML_FILE="$0"
fi
_YAML_DIR="$(cd "$(dirname "$_YAML_FILE")" && pwd)"

# Source logging and platform if available
if [ -f "$_YAML_DIR/../core/logging.sh" ]; then
  # shellcheck source=../core/logging.sh
  source "$_YAML_DIR/../core/logging.sh"
fi

if [ -f "$_YAML_DIR/../core/platform.sh" ]; then
  # shellcheck source=../core/platform.sh
  source "$_YAML_DIR/../core/platform.sh"
fi

# Check if yq is installed
yq_check() {
  if ! command -v yq >/dev/null 2>&1; then
    if type log_error >/dev/null 2>&1; then
      log_error "yq is not installed. Please install yq to continue."
    else
      echo "ERROR: yq is not installed. Please install yq to continue." >&2
    fi
    return 1
  fi
  return 0
}

# Safe yq set with error handling
yq_set() {
  local file="$1"
  local path="$2"
  local value="$3"

  if ! yq_check; then
    return 1
  fi

  if [ ! -f "$file" ]; then
    if type log_error >/dev/null 2>&1; then
      log_error "File not found: $file"
    fi
    return 1
  fi

  # Use yq to set value in-place
  if yq eval "$path = $value" -i "$file"; then
    return 0
  else
    if type log_error >/dev/null 2>&1; then
      log_error "Failed to set $path in $file"
    fi
    return 1
  fi
}

# Safe yq get with error handling
yq_get() {
  local file="$1"
  local path="$2"

  if ! yq_check; then
    return 1
  fi

  if [ ! -f "$file" ]; then
    if type log_error >/dev/null 2>&1; then
      log_error "File not found: $file"
    fi
    return 1
  fi

  # Use yq to get value
  if yq eval "$path" "$file"; then
    return 0
  else
    if type log_error >/dev/null 2>&1; then
      log_error "Failed to get $path from $file"
    fi
    return 1
  fi
}

# Copy config file with logging
copy_config() {
  local source="$1"
  local dest="$2"

  if [ ! -f "$source" ]; then
    if type log_error >/dev/null 2>&1; then
      log_error "Source file not found: $source"
    fi
    return 1
  fi

  if type log_debug >/dev/null 2>&1; then
    log_debug "Copying $source to $dest"
  fi

  if cp "$source" "$dest"; then
    return 0
  else
    if type log_error >/dev/null 2>&1; then
      log_error "Failed to copy $source to $dest"
    fi
    return 1
  fi
}

# Update port in YAML config
update_yaml_port() {
  local file="$1"
  local port="$2"

  if ! yq_check; then
    return 1
  fi

  if [ ! -f "$file" ]; then
    if type log_error >/dev/null 2>&1; then
      log_error "File not found: $file"
    fi
    return 1
  fi

  if type log_debug >/dev/null 2>&1; then
    log_debug "Updating port to $port in $file"
  fi

  # Update server.port in YAML
  if yq_set "$file" ".server.port" "$port"; then
    return 0
  else
    return 1
  fi
}
