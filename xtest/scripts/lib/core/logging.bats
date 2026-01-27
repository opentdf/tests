#!/usr/bin/env bats
# Tests for core/logging.sh

setup() {
  bats_require_minimum_version 1.5.0

  # Try to load bats-support and bats-assert
  local bats_support_path="${BATS_SUPPORT_PATH:-}"
  if [ -z "$bats_support_path" ] && command -v brew >/dev/null 2>&1; then
    bats_support_path="$(brew --prefix)/lib"
  fi

  if [ -n "$bats_support_path" ] && [ -d "$bats_support_path" ]; then
    load "${bats_support_path}/bats-support/load.bash" 2>/dev/null || true
    load "${bats_support_path}/bats-assert/load.bash" 2>/dev/null || true
  fi

  # Load the library under test
  load logging.sh

  # Store full path for subprocess tests
  TEST_LIB_FILE="${BATS_TEST_DIRNAME}/logging.sh"

  # Unset log level for each test (use default)
  unset XTEST_LOGLEVEL
}

@test "log_info outputs blue INFO prefix" {
  run log_info "test message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[INFO]"* ]]
  [[ "$output" == *"test message"* ]]
}

@test "log_success outputs green OK prefix" {
  run log_success "success message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[OK]"* ]]
  [[ "$output" == *"success message"* ]]
}

@test "log_warn outputs yellow WARN prefix" {
  run log_warn "warning message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[WARN]"* ]]
  [[ "$output" == *"warning message"* ]]
}

@test "log_error outputs red ERROR prefix to stderr" {
  run log_error "error message"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[ERROR]"* ]]
  [[ "$output" == *"error message"* ]]
}

@test "log_debug outputs CYAN DEBUG prefix" {
  run log_debug "debug message"
  [ "$status" -eq 0 ]
  # Default level is info, so debug should not output
  [ -z "$output" ]
}

@test "log_debug outputs when XTEST_LOGLEVEL=debug" {
  XTEST_LOGLEVEL=debug run bash -c "source '$TEST_LIB_FILE' && log_debug 'debug message'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[DEBUG]"* ]]
  [[ "$output" == *"debug message"* ]]
}

@test "log_trace outputs when XTEST_LOGLEVEL=trace" {
  XTEST_LOGLEVEL=trace run bash -c "source '$TEST_LIB_FILE' && log_trace 'trace message'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[TRACE]"* ]]
  [[ "$output" == *"trace message"* ]]
}

@test "log_trace does not output at default level" {
  run log_trace "trace message"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "XTEST_LOGLEVEL=quiet suppresses all output" {
  XTEST_LOGLEVEL=quiet run bash -c "source '$TEST_LIB_FILE' && log_error 'error'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]

  XTEST_LOGLEVEL=quiet run bash -c "source '$TEST_LIB_FILE' && log_warn 'warning'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]

  XTEST_LOGLEVEL=quiet run bash -c "source '$TEST_LIB_FILE' && log_info 'info'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "XTEST_LOGLEVEL=error shows only errors" {
  XTEST_LOGLEVEL=error run bash -c "source '$TEST_LIB_FILE' && log_error 'error'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"[ERROR]"* ]]

  XTEST_LOGLEVEL=error run bash -c "source '$TEST_LIB_FILE' && log_warn 'warning'"
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "logging functions work without set -e" {
  set +e
  run log_info "test"
  [ "$status" -eq 0 ]
  set -e
}

@test "logging functions work with set -e" {
  set -e
  run log_info "test"
  [ "$status" -eq 0 ]
  set +e
}

@test "log_traced_call executes command and returns exit code" {
  XTEST_LOGLEVEL=trace run bash -c "source '$TEST_LIB_FILE' && log_traced_call echo 'hello'"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Executing: echo hello"* ]]
  [[ "$output" == *"hello"* ]]
  [[ "$output" == *"Command exited with code: 0"* ]]
}

@test "log_traced_call preserves non-zero exit codes" {
  XTEST_LOGLEVEL=trace run bash -c "source '$TEST_LIB_FILE' && log_traced_call false"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Command exited with code: 1"* ]]
}
