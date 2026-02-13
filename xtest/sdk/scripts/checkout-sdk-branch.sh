#!/bin/bash
# Backward-compatible wrapper. Use `otdf-sdk-mgr checkout` instead.
#
# Usage: ./checkout-sdk-branch.sh [sdk language] [branch]
# Example: ./checkout-sdk-branch.sh js main

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$SCRIPT_DIR/../../../../otdf-sdk-mgr"

if command -v uv &>/dev/null && [ -f "$PROJECT_DIR/pyproject.toml" ]; then
  exec uv run --project "$PROJECT_DIR" otdf-sdk-mgr checkout "${1:-js}" "${2:-main}"
else
  # Fallback: direct Python import (works in CI without uv)
  exec python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/src')
from otdf_sdk_mgr.checkout import checkout_sdk_branch
checkout_sdk_branch('${1:-js}', '${2:-main}')
"
fi
