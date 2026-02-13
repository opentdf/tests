#!/bin/bash
# Removes the checked out branches of each of the sdks under test

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null  && pwd)

for sdk in go java js; do
  rm -rf "$SCRIPT_DIR/../$sdk/dist"
  for branch in "$SCRIPT_DIR/../${sdk}/src/"*; do
    # Check if the path ends with .git
    if [[ $branch == *.git ]]; then
      continue
    fi
    if [ -d "$branch" ]; then
      rm -rf "$branch"
    fi
  done
done
