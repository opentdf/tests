"""Cross-SDK coverage for the ZIP64 boundary at 2 GiB (DSPX-4592).

Every test here is marked ``zip64`` and is deselected unless the session asks
for a payload size that can reach ``2**31`` -- see the size table in
``sizes.py`` for why 2.1 GiB and not something rounder, and
``pytest_collection_modifyitems`` in ``conftest.py`` for the deselection.

Run it with::

    uv run pytest test_zip64.py --sizes medium --sdks "go java js" -v

These are separate from ``test_tdfs.py`` for three reasons that all come down
to the payload size: the decrypted output is deleted as soon as it has been
compared rather than accumulating at 2.1 GiB a time, the container's ZIP
encoding is asserted on directly, and CI can select them without dragging the
rest of the suite up to multi-GiB payloads.
"""

import filecmp
import logging
from pathlib import Path

import pytest

import tdfs
import zipinspect
from abac import Attribute
from fixtures.encryption import EncryptFactory
from sizes import SIZES, ZIP64_WINDOW_LOW

logger = logging.getLogger(__name__)

# ``no_audit_logs`` is inert today -- nothing here requests the ``audit_logs``
# fixture, and it is not autouse -- but it states the intent: this module tests
# the container encoding, and a rewrap audit event says nothing about that.
pytestmark = [pytest.mark.zip64, pytest.mark.no_audit_logs]


def _assert_reaches_the_window(
    entries: list[zipinspect.CentralDirectoryEntry],
    pt_file: Path,
    encrypt_sdk: tdfs.SDK,
) -> None:
    """Fail unless some entry actually landed at or above 2**31.

    This is the load-bearing assertion in the module. Everything else here
    tests how an SDK handles a value in the broken window; if no value got
    there, the rest of the test passes without exercising a single line of
    the code under test, and reports success for it.

    That is the exact failure this ticket exists to close -- the suite already
    had a large-file path that stepped over the window -- so it is an
    assertion rather than a skip.
    """
    biggest = max((e.local_header_offset for e in entries), default=0)
    assert biggest >= ZIP64_WINDOW_LOW, (
        f"{encrypt_sdk} wrote a container whose largest local-header offset is "
        f"{biggest}, below 2**31 ({ZIP64_WINDOW_LOW}), from a "
        f"{pt_file.stat().st_size}-byte payload. Nothing in this test is "
        f"exercising the 2-4 GiB band.\n" + zipinspect.describe(entries)
    )


def test_zip64_band_roundtrip(
    request: pytest.FixtureRequest,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    size: str,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    """Encrypt and decrypt a payload whose manifest offset is in the broken window.

    The whole cross-SDK matrix runs against one payload: writer defects and
    reader defects both surface as a failure to round-trip, and which SDK is
    at fault is what the structural assertions below disambiguate.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attribute_default_rsa.value_fqns,
    )

    entries = zipinspect.central_directory(ct_file)
    logger.info(
        "%s wrote %s at size=%s (%d bytes):\n%s",
        encrypt_sdk,
        ct_file.name,
        size,
        SIZES[size],
        zipinspect.describe(entries),
    )

    # Writer conformance first, and outside the reader's xfail below. A
    # writer regression must not hide behind a known reader bug: if these
    # fail under an xfail marker the cell reports XFAIL and nobody looks.
    _assert_reaches_the_window(entries, pt_file, encrypt_sdk)
    zipinspect.assert_zip64_above_4gib(entries)

    in_window = zipinspect.entries_in_window(entries)
    logger.info(
        "%s: %d entr%s in [2**31, 2**32); zip64 extra field used for %s",
        encrypt_sdk,
        len(in_window),
        "y" if len(in_window) == 1 else "ies",
        [e.name for e in in_window if e.has_zip64_extra] or "none",
    )

    # Keep the independent segment-defaulting incompatibility out of the
    # ZIP64 result. In particular, web-sdk uses ZIP64 sentinels in this band,
    # so those containers do not exercise Java's signed 32-bit read defect.
    tdfs.skip_chunky_skew(ct_file, decrypt_sdk)

    # Apply the reader xfail only when a real 32-bit value (not the sentinel)
    # exercises the signed-risk window. Writer conformance has already been
    # checked above, so a failure from this point belongs to the reader.
    if zipinspect.entries_with_raw_values_in_window(entries):
        if mark := tdfs.zip64_reader_xfail(decrypt_sdk):
            request.node.add_marker(mark)

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
        # shallow=False explicitly: the default compares a stat signature
        # first and only falls through to a byte compare because the mtimes
        # happen to differ. At this size the difference between checking the
        # bytes and checking the size is worth not leaving to chance.
        assert filecmp.cmp(pt_file, rt_file, shallow=False), (
            f"{decrypt_sdk} decrypted {ct_file.name} without error but the "
            f"output does not match the {pt_file.stat().st_size}-byte input"
        )
    finally:
        # 2.1 GiB per pair. The ciphertext is session-cached and shared, but
        # these are not, and a full matrix would fill the runner's disk long
        # before the last cell.
        rt_file.unlink(missing_ok=True)
