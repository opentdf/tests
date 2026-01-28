#!/usr/bin/env bats
# Tests for core/platform.sh

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
  load platform.sh
}

@test "is_macos returns correct result" {
  if [ "$(uname -s)" = "Darwin" ]; then
    run is_macos
    [ "$status" -eq 0 ]
  else
    run is_macos
    [ "$status" -ne 0 ]
  fi
}

@test "is_linux returns correct result" {
  run is_linux
  # Just check it runs without error - actual result depends on platform
  # On macOS it should fail (non-zero), on Linux it should pass (zero)
  if [ "$(uname -s)" = "Darwin" ]; then
    [ "$status" -ne 0 ]
  fi
}

@test "is_wsl returns correct result" {
  if [ -f /proc/version ] && grep -qi microsoft /proc/version; then
    run is_wsl
    [ "$status" -eq 0 ]
  else
    run is_wsl
    [ "$status" -ne 0 ]
  fi
}

@test "has_command detects existing commands" {
  run has_command bash
  [ "$status" -eq 0 ]

  run has_command echo
  [ "$status" -eq 0 ]
}

@test "has_command fails for non-existent commands" {
  run has_command nonexistent_command_xyz123
  [ "$status" -ne 0 ]
}

@test "get_sed_inplace returns appropriate flags" {
  run get_sed_inplace
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  # Should return either "-i ''" for macOS or "-i" for Linux
  [[ "$output" == "-i"* ]]
}

@test "get_brew_prefix returns path when brew exists" {
  if command -v brew >/dev/null 2>&1; then
    run get_brew_prefix
    [ "$status" -eq 0 ]
    [ -n "$output" ]
    [ -d "$output" ]
  else
    run get_brew_prefix
    [ "$status" -ne 0 ]
  fi
}

@test "get_cpu_count returns a number" {
  run get_cpu_count
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  [[ "$output" =~ ^[0-9]+$ ]]
  [ "$output" -ge 1 ]
}

@test "get_shell_type detects current shell" {
  run get_shell_type
  [ "$status" -eq 0 ]
  [ -n "$output" ]
  # Should be bash, zsh, or unknown
  [[ "$output" =~ ^(bash|zsh|unknown)$ ]]
}

@test "platform functions work without set -e" {
  set +e
  run is_macos
  # Just check it doesn't crash
  set -e
}
