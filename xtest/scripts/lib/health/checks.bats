#!/usr/bin/env bats
# Tests for health/checks.sh

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
  load checks.sh
}

@test "check_command succeeds for existing commands" {
  run check_command bash
  [ "$status" -eq 0 ]

  run check_command echo
  [ "$status" -eq 0 ]
}

@test "check_command fails for non-existent commands" {
  run check_command nonexistent_command_xyz123
  [ "$status" -eq 1 ]
  [[ "$output" == *"Required command not found"* ]]
}

@test "check_prerequisites checks multiple commands" {
  # This will likely fail unless all commands are present
  # but it should not crash
  run check_prerequisites
  # Status depends on system, just check it runs
}

@test "check_command works without set -e" {
  set +e
  run check_command bash
  [ "$status" -eq 0 ]
  run check_command nonexistent_xyz
  [ "$status" -eq 1 ]
  set -e
}

@test "wait_for_health times out on unreachable endpoint" {
  run timeout 5 bash -c "source checks.sh && wait_for_health 'http://localhost:99999/nonexistent' 'test' 2"
  [ "$status" -ne 0 ]
}
