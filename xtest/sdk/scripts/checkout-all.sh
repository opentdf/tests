#!/bin/bash
# Backward-compatible wrapper. Use `otdf-sdk-mgr checkout --all` instead.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$SCRIPT_DIR/../../../../otdf-sdk-mgr"

if command -v uv &>/dev/null && [ -f "$PROJECT_DIR/pyproject.toml" ]; then
  exec uv run --project "$PROJECT_DIR" otdf-sdk-mgr checkout --all
else
  for sdk in go java js; do
    "$SCRIPT_DIR/checkout-sdk-branch.sh" "$sdk" main || exit 1
  done
fi
