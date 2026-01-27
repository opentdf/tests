#!/usr/bin/env bats
# Tests for health/waits.sh

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
  load waits.sh
}

@test "port_in_use fails for closed port" {
  # Use a very high port number that is unlikely to be in use
  run port_in_use 65534
  [ "$status" -ne 0 ]
}

@test "wait_for_port times out on closed port" {
  # Use a very short timeout
  run timeout 5 bash -c "source waits.sh && wait_for_port 65533 'test' 2"
  [ "$status" -ne 0 ]
}

@test "port functions work without set -e" {
  set +e
  run port_in_use 65532
  # Just check it doesn't crash
  set -e
}
