#!/usr/bin/env bats
# Tests for services/kas-utils.sh

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
  load kas-utils.sh
}

@test "get_kas_config_path returns expected path" {
  run get_kas_config_path "alpha"
  [ "$status" -eq 0 ]
  [[ "$output" == */logs/kas-alpha.yaml ]]
}

@test "is_km_kas recognizes km1 by default" {
  run is_km_kas "km1"
  [ "$status" -eq 0 ]
}

@test "is_km_kas recognizes km2 by default" {
  run is_km_kas "km2"
  [ "$status" -eq 0 ]
}

@test "is_km_kas rejects non-km instances by default" {
  run is_km_kas "alpha"
  [ "$status" -ne 0 ]

  run is_km_kas "beta"
  [ "$status" -ne 0 ]
}

@test "is_km_kas uses KM_KAS_INSTANCES array when set" {
  export KM_KAS_INSTANCES=("custom1" "custom2")
  run is_km_kas "custom1"
  [ "$status" -eq 0 ]

  run is_km_kas "km1"
  [ "$status" -ne 0 ]
}

@test "generate_root_key produces 64-character hex string" {
  run generate_root_key
  [ "$status" -eq 0 ]
  [ "${#output}" -eq 64 ]
  [[ "$output" =~ ^[0-9a-f]{64}$ ]]
}

@test "generate_root_key produces unique keys" {
  run generate_root_key
  local key1="$output"

  run generate_root_key
  local key2="$output"

  [ "$key1" != "$key2" ]
}
