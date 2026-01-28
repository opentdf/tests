#!/usr/bin/env bash
# Platform detection and compatibility utilities
# CRITICAL: NO shell options (set -e, set -o pipefail) - consumer scripts control error handling

# Determine library directory (bash/zsh compatible)
if [ -n "${BASH_SOURCE:-}" ]; then
  _PLATFORM_FILE="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
  _PLATFORM_FILE="${(%):-%x}"
else
  _PLATFORM_FILE="$0"
fi
_PLATFORM_DIR="$(cd "$(dirname "$_PLATFORM_FILE")" && pwd)"

# Check if running on macOS
is_macos() {
  if [ "$(uname -s)" = "Darwin" ]; then
    return 0
  else
    return 1
  fi
}

# Check if running on Linux (not WSL)
is_linux() {
  if [ "$(uname -s)" = "Linux" ] && ! is_wsl; then
    return 0
  else
    return 1
  fi
}

# Check if running on WSL
is_wsl() {
  if [ -f /proc/version ] && grep -qi microsoft /proc/version; then
    return 0
  else
    return 1
  fi
}

# Check if a command exists
has_command() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    return 0
  else
    return 1
  fi
}

# Get platform-specific sed in-place edit flags
get_sed_inplace() {
  if is_macos; then
    echo "-i ''"
  else
    echo "-i"
  fi
}

# Get Homebrew prefix if available
get_brew_prefix() {
  if has_command brew; then
    brew --prefix
    return 0
  else
    return 1
  fi
}

# Get number of CPU cores (for parallel operations)
get_cpu_count() {
  if is_macos; then
    sysctl -n hw.ncpu
  elif is_linux || is_wsl; then
    nproc
  else
    echo "1"
  fi
}

# Detect shell type
get_shell_type() {
  if [ -n "${BASH_VERSION:-}" ]; then
    echo "bash"
  elif [ -n "${ZSH_VERSION:-}" ]; then
    echo "zsh"
  else
    echo "unknown"
  fi
}
