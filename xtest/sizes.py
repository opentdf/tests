"""Plaintext payload sizes, and the ZIP64 window they are chosen around.

Kept free of pytest and of ``tdfs`` so that both ``conftest.py`` and the test
modules can name a size without importing each other.

The ZIP central directory stores local-header offsets and entry sizes in 32-bit
fields that are *unsigned on the wire*. Three regimes follow, and only one of
them can expose a signed-widening bug:

===========================  ==========================================
value                        what a reader sees
===========================  ==========================================
``v < 2**31``                a signed read and an unsigned read agree
``2**31 <= v < 2**32``       a signed read comes back negative
``v >= 2**32``               ZIP64 sentinel; the 32-bit field is never
                             populated with a real value, so the bug
                             cannot fire
===========================  ==========================================

That middle row is the only broken window, and it is exactly what
:data:`SIZES`'s ``medium`` entry exists to land a TDF's manifest offset in.
"""

from __future__ import annotations

#: Smallest value a 32-bit field must be read as unsigned to survive.
ZIP64_WINDOW_LOW = 2**31

#: At and above this the format requires the ZIP64 sentinel plus an extra
#: field, so the 32-bit field holds 0xFFFFFFFF rather than a real value.
ZIP64_WINDOW_HIGH = 2**32

#: 2.1 GiB. Sits ~102 MiB inside the low edge of the broken window.
#:
#: The margin is the point. A TDF writes ``0.payload`` first and
#: ``0.manifest.json`` after it, so the manifest's local-header offset is
#: roughly the payload size -- and that offset is the value under test. The
#: gap to 2**31 has to be wider than anything that could shift it: segment
#: padding, manifest length, per-entry header overhead. 102 MiB is not a
#: round number because it does not need to be; it needs to be unarguably
#: larger than those.
#:
#: Shrinking this below 2**31 does not make the test cheaper, it makes it
#: vacuous -- every SDK takes the safe path and the test passes without
#: exercising anything. See the assertion in test_zip64.py that fails loudly
#: rather than letting that happen quietly.
MEDIUM_BYTES = 2_254_857_830

#: 5 MiB. Nothing to do with the ZIP64 window -- this is the smallest size at
#: which *every* SDK's writer emits more than one **default-sized** segment.
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
    "medium": MEDIUM_BYTES,
    "large": 5 * 2**30,
}

#: Order to emit parametrized sizes in, cheapest first.
SIZE_ORDER: tuple[str, ...] = ("small", "chunky", "medium", "large")


def in_zip64_window(n: int) -> bool:
    """True for values a signed 32-bit read would mangle."""
    return ZIP64_WINDOW_LOW <= n < ZIP64_WINDOW_HIGH


def exercises_zip64_window(size: str) -> bool:
    """True if a payload of this size can put a real value in the broken window.

    Note this is ``>=`` the low edge rather than :func:`in_zip64_window`: a
    5 GiB payload does not itself land in the window, but the run that asked
    for it is plainly a large-file run and the zip64 module has something to
    say about its ZIP64 encoding too.
    """
    return SIZES[size] >= ZIP64_WINDOW_LOW
