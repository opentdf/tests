#!/usr/bin/env bats

setup() {
  export PATH="$PATH:${BATS_TEST_DIRNAME}"
}

@test "doesnt wait for existing file" {
  run touch "$BATS_TMPDIR/a.tmp"
  wait-for-file "$BATS_TMPDIR/a.tmp"
}

@test "fails if file doesn't exist" {
  run wait-for-file --wait-cycles 2 "$BATS_TMPDIR/b.tmp"
  [[ $status == 1 ]]
  [[ $output == *failed* ]]
}

@test "runs a command" {
  run touch "$BATS_TMPDIR/c.tmp"
  run wait-for-file --wait-cycles 1 "$BATS_TMPDIR/c.tmp" -- echo hello, world
  [[ $status == 0 ]]
  [[ $output == *world* ]]
}

@test "links files" {
  echo hello > "$BATS_TMPDIR/d.tmp"
  echo world > "$BATS_TMPDIR/e.tmp"
  run wait-for-file --wait-cycles 1 --ln "$BATS_TMPDIR/d.tmp" "$BATS_TMPDIR/d" --ln "$BATS_TMPDIR/e.tmp" "$BATS_TMPDIR/e" -- echo hello
  [[ $status == 0 ]]
  [[ $output == *hello* ]]
  [[ -L "$BATS_TMPDIR/d" && -L "$BATS_TMPDIR/e" ]]
}
