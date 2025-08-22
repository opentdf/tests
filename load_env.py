#!/usr/bin/env python3
"""Load environment variables from .env file."""

import os
from pathlib import Path


def load_dotenv(env_file: Path = None):
    """Load environment variables from .env file."""
    if env_file is None:
        env_file = Path(__file__).parent / ".env"
    
    if not env_file.exists():
        return False
    
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value.strip()
    
    return True


# Auto-load .env when imported
load_dotenv()