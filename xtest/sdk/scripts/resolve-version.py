#!/usr/bin/env python3
"""Backward-compatible wrapper. Use `otdf-sdk-mgr versions resolve` instead."""
import sys
from pathlib import Path

# tests/otdf-sdk-mgr/src/ is three levels up from xtest/sdk/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "otdf-sdk-mgr" / "src"))

# Re-export types and constants for any code that imports this module directly
from otdf_sdk_mgr.config import LTS_VERSIONS as lts_versions  # noqa: E402, F401, N812
from otdf_sdk_mgr.resolve import (  # noqa: E402, F401
    ResolveError,
    ResolveResult,
    ResolveSuccess,
    is_resolve_error,
    is_resolve_success,
    main,
)

if __name__ == "__main__":
    main()
