#!/usr/bin/env bats

setup() {
  export MONOLOG_LEVEL
  export PATH="$PATH:${BATS_TEST_DIRNAME}"
}

@test "ERROR >= 3" {
  MONOLOG_LEVEL=3
  run monolog ERROR "at error"
  [[ $output == *error* ]]
}

@test "WARN >= 3" {
  MONOLOG_LEVEL=3
  run monolog WARN "at warning"
  [[ $output == *warning* ]]
}

@test "DEBUG < 3" {
  MONOLOG_LEVEL=3
  run monolog DEBUG "at debug"
  [[ $output == "" ]]
}

@test "WTF >= 5" {
  MONOLOG_LEVEL=5
  run monolog WTF "at critical"
  [[ $output == *critical* ]]
}

@test "CRITICAL >= 5" {
  MONOLOG_LEVEL=5
  run monolog CRITICAL "at critical"
  [[ $output == *critical* ]]
}

@test "ERROR < 5" {
  MONOLOG_LEVEL=5
  run monolog ERROR "at error"
  [[ $output == "" ]]
}

@test "WARN < 5" {
  MONOLOG_LEVEL=5
  run monolog WARN "at warning"
  [[ $output == "" ]]
}

@test "DEBUG < 5" {
  MONOLOG_LEVEL=5
  run monolog DEBUG "at debug"
  [[ $output == "" ]]
}

@test "DEBUG >= 0" {
  MONOLOG_LEVEL=0
  run monolog DEBUG "at debug"
  [[ $output == *debug* ]]
}
