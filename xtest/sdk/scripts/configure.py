#!/usr/bin/env python3
"""Backward-compatible wrapper. Use `otdf-sdk-mgr install` instead."""
import sys
from pathlib import Path

# tests/otdf-sdk-mgr/src/ is three levels up from xtest/sdk/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "otdf-sdk-mgr" / "src"))
from otdf_sdk_mgr.installers import configure_main  # noqa: E402

if __name__ == "__main__":
    configure_main()
