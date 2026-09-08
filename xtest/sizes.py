"""Plaintext payload sizes for cross-SDK test fixtures.

Kept free of pytest and of ``tdfs`` so that both ``conftest.py`` and the test
modules can name a size without importing each other.
"""

from __future__ import annotations

#: 5 MiB. This is the smallest size at which *every* SDK's writer emits more
#: than one **default-sized** segment.
#:
#: A segment only exercises the ``chunky`` path if its size equals the
#: manifest-level default, because that is precisely the case web-sdk omits
#: ``segmentSize``/``encryptedSegmentSize`` for. A payload smaller than one
#: default segment produces a single *partial* segment, whose size is written
#: out explicitly, and every reader copes -- which is the only reason a
#: 128-byte suite stayed green through four years of this bug.
#:
#: Defaults differ: web-sdk 1 MiB, go and java ~2 MiB. 5 MiB clears twice the
#: largest of them with room to spare. 2 MiB would only do it for web-sdk.
CHUNKY_BYTES = 5 * 2**20

SIZES: dict[str, int] = {
    "small": 128,
    "chunky": CHUNKY_BYTES,
    "large": 5 * 2**30,
}

#: Order to emit parametrized sizes in, cheapest first.
SIZE_ORDER: tuple[str, ...] = ("small", "chunky", "large")
