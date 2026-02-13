#!/bin/bash
# Backward-compatible wrapper. Use `otdf-sdk-mgr clean` instead.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$SCRIPT_DIR/../../../../otdf-sdk-mgr"

if command -v uv &>/dev/null && [ -f "$PROJECT_DIR/pyproject.toml" ]; then
  exec uv run --project "$PROJECT_DIR" otdf-sdk-mgr clean
else
  # Fallback: inline cleanup matching original behavior
  for sdk in go java js; do
    rm -rf "$SCRIPT_DIR/../$sdk/dist"
    for branch in "$SCRIPT_DIR/../${sdk}/src/"*; do
      if [[ $branch == *.git ]]; then
        continue
      fi
      if [ -d "$branch" ]; then
        rm -rf "$branch"
      fi
    done
  done
fi
