# test_helper.bash
# Shared test utilities for BATS tests

# Load bats-support and bats-assert
# Supports both Homebrew and Nix installations
setup_bats_libs() {
  local bats_support_path="${BATS_SUPPORT_PATH:-}"

  # Try common paths if not explicitly set
  if [ -z "$bats_support_path" ]; then
    if command -v brew > /dev/null 2>&1; then
      bats_support_path="$(brew --prefix)/lib"
    elif [ -d "/usr/lib" ]; then
      bats_support_path="/usr/lib"
    fi
  fi

  if [ -n "$bats_support_path" ]; then
    load "${bats_support_path}/bats-support/load.bash" || true
    load "${bats_support_path}/bats-assert/load.bash" || true
  fi
}

# Mock common external commands for testing
mock_command() {
  local cmd="$1"
  local return_code="${2:-0}"
  local output="${3:-}"

  eval "${cmd}() { echo '${output}'; return ${return_code}; }"
}

# Restore original command
unmock_command() {
  local cmd="$1"
  unset -f "$cmd"
}

# Create a temporary directory for test files
setup_test_dir() {
  TEST_TEMP_DIR="$(mktemp -d)"
  export TEST_TEMP_DIR
}

# Clean up temporary test directory
teardown_test_dir() {
  if [ -n "${TEST_TEMP_DIR:-}" ] && [ -d "$TEST_TEMP_DIR" ]; then
    rm -rf "$TEST_TEMP_DIR"
  fi
}
