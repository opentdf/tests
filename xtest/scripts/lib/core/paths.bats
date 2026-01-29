#!/usr/bin/env bats
# Tests for core/paths.sh

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
  load paths.sh

  # Create temporary directory for testing
  TEST_TEMP_DIR="$(mktemp -d)"
}

teardown() {
  if [ -n "$TEST_TEMP_DIR" ] && [ -d "$TEST_TEMP_DIR" ]; then
    rm -rf "$TEST_TEMP_DIR"
  fi
}

@test "get_lib_dir returns valid directory" {
  run get_lib_dir
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  [ -d "$output" ]
  # Should end with /lib
  [[ "$output" == */lib ]]
}

@test "get_scripts_dir returns valid directory" {
  run get_scripts_dir
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  [ -d "$output" ]
  # Should end with /scripts
  [[ "$output" == */scripts ]]
}

@test "get_xtest_dir returns valid directory" {
  run get_xtest_dir
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  [ -d "$output" ]
  # Should end with /xtest
  [[ "$output" == */xtest ]]
}

@test "get_platform_dir returns path" {
  run get_platform_dir
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  # May or may not exist, but should be a path
  [[ "$output" == */platform ]]
}

@test "get_logs_dir returns expected path" {
  run get_logs_dir
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  # Should end with /logs
  [[ "$output" == */logs ]]
}

@test "ensure_dir creates new directory" {
  local test_dir="$TEST_TEMP_DIR/new_dir"
  [ ! -d "$test_dir" ]

  run ensure_dir "$test_dir"
  [ "$status" -eq 0 ]
  [ -d "$test_dir" ]
}

@test "ensure_dir succeeds for existing directory" {
  local test_dir="$TEST_TEMP_DIR/existing_dir"
  mkdir -p "$test_dir"
  [ -d "$test_dir" ]

  run ensure_dir "$test_dir"
  [ "$status" -eq 0 ]
  [ -d "$test_dir" ]
}

@test "ensure_dir creates nested directories" {
  local test_dir="$TEST_TEMP_DIR/a/b/c"
  [ ! -d "$test_dir" ]

  run ensure_dir "$test_dir"
  [ "$status" -eq 0 ]
  [ -d "$test_dir" ]
}

@test "ensure_logs_dir creates logs directory" {
  # This test might fail if logs already exists, but that's OK
  run ensure_logs_dir
  [ "$status" -eq 0 ]

  # Check that logs dir now exists
  local logs_dir
  logs_dir="$(get_logs_dir)"
  [ -d "$logs_dir" ]
}

@test "path functions work without set -e" {
  set +e
  run get_lib_dir
  [ "$status" -eq 0 ]
  run get_scripts_dir
  [ "$status" -eq 0 ]
  set -e
}
