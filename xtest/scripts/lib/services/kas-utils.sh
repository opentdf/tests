#!/usr/bin/env bash
# KAS-specific utilities
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _KAS_UTILS_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _KAS_UTILS_FILE="${(%):-%x}"
else
  _KAS_UTILS_FILE="$0"
fi
_KAS_UTILS_DIR="$(cd "$(dirname "$_KAS_UTILS_FILE")" && pwd)"

# Get KAS config file path
get_kas_config_path() {
  local name="$1"
  local xtest_dir="${XTEST_DIR:-$(cd "$_KAS_UTILS_DIR/../../.." && pwd)}"
  echo "$xtest_dir/logs/kas-${name}.yaml"
}

# Check if this is a key management KAS
# Uses KM_KAS_INSTANCES array if available
is_km_kas() {
  local name="$1"

  # If KM_KAS_INSTANCES is not set, default to km1 and km2
  if [ -z "${KM_KAS_INSTANCES:-}" ]; then
    if [ "$name" = "km1" ] || [ "$name" = "km2" ]; then
      return 0
    else
      return 1
    fi
  fi

  # Check if name is in KM_KAS_INSTANCES array
  # This pattern works in both bash and zsh
  for km_instance in "${KM_KAS_INSTANCES[@]}"; do
    if [ "$km_instance" = "$name" ]; then
      return 0
    fi
  done

  return 1
}

# Generate root key for key management KAS instances
generate_root_key() {
  openssl rand -hex 32
}
