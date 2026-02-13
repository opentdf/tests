#!/bin/bash
# Backward-compatible wrapper. Use `otdf-sdk-mgr java-fixup` instead.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$SCRIPT_DIR/../../../../otdf-sdk-mgr"

if command -v uv &>/dev/null && [ -f "$PROJECT_DIR/pyproject.toml" ]; then
  exec uv run --project "$PROJECT_DIR" otdf-sdk-mgr java-fixup
else
  # Fallback: direct Python import
  exec python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/src')
from otdf_sdk_mgr.java_fixup import post_checkout_java_fixup
post_checkout_java_fixup()
"
fi
