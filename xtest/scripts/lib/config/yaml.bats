#!/usr/bin/env bats
# Tests for config/yaml.sh

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
  load yaml.sh

  # Create temporary directory for testing
  TEST_TEMP_DIR="$(mktemp -d)"

  # Create a test YAML file
  cat >"$TEST_TEMP_DIR/test.yaml" <<EOF
server:
  port: 8080
  host: localhost
database:
  name: testdb
EOF
}

teardown() {
  if [ -n "$TEST_TEMP_DIR" ] && [ -d "$TEST_TEMP_DIR" ]; then
    rm -rf "$TEST_TEMP_DIR"
  fi
}

@test "yq_check succeeds when yq is installed" {
  if command -v yq >/dev/null 2>&1; then
    run yq_check
    [ "$status" -eq 0 ]
  else
    skip "yq not installed"
  fi
}

@test "yq_get reads values from YAML" {
  if ! command -v yq >/dev/null 2>&1; then
    skip "yq not installed"
  fi

  run yq_get "$TEST_TEMP_DIR/test.yaml" ".server.port"
  [ "$status" -eq 0 ]
  [ "$output" = "8080" ]
}

@test "yq_set updates values in YAML" {
  if ! command -v yq >/dev/null 2>&1; then
    skip "yq not installed"
  fi

  run yq_set "$TEST_TEMP_DIR/test.yaml" ".server.port" "9090"
  [ "$status" -eq 0 ]

  # Verify the change
  run yq_get "$TEST_TEMP_DIR/test.yaml" ".server.port"
  [ "$output" = "9090" ]
}

@test "copy_config copies files" {
  echo "test content" >"$TEST_TEMP_DIR/source.txt"

  run copy_config "$TEST_TEMP_DIR/source.txt" "$TEST_TEMP_DIR/dest.txt"
  [ "$status" -eq 0 ]
  [ -f "$TEST_TEMP_DIR/dest.txt" ]
  [ "$(cat "$TEST_TEMP_DIR/dest.txt")" = "test content" ]
}

@test "copy_config fails for missing source" {
  run copy_config "$TEST_TEMP_DIR/nonexistent.txt" "$TEST_TEMP_DIR/dest.txt"
  [ "$status" -ne 0 ]
}

@test "update_yaml_port updates server port" {
  if ! command -v yq >/dev/null 2>&1; then
    skip "yq not installed"
  fi

  run update_yaml_port "$TEST_TEMP_DIR/test.yaml" "7070"
  [ "$status" -eq 0 ]

  # Verify the change
  run yq_get "$TEST_TEMP_DIR/test.yaml" ".server.port"
  [ "$output" = "7070" ]
}
