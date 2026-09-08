"""Plaintext payload sizes for cross-SDK test fixtures.

Kept free of pytest and of ``tdfs`` so that both ``conftest.py`` and the test
modules can name a size without importing each other.
"""

from __future__ import annotations

SIZES: dict[str, int] = {
    "small": 128,
    "large": 5 * 2**30,
}

#: Order to emit parametrized sizes in, cheapest first.
SIZE_ORDER: tuple[str, ...] = ("small", "large")
