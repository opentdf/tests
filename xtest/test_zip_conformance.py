"""Cross-SDK structural/adversarial ZIP conformance tests (DSPX-4591 follow-up).

``test_zip64.py`` covers *size-boundary offset placement* -- whether a
payload's local-header offset lands in the ``[2**31, 2**32)`` band where a
signed 32-bit read goes negative. This module covers a different dimension:
*structural* ZIP layout -- spec-legal-but-unusual central-directory/EOCD
shapes, and adversarial ones -- that any conformant reader must handle
correctly regardless of which SDK produced or is consuming the container.

web-sdk PR #1017 (DSPX-4591) fixed four bugs in exactly this area, found and
verified only by that one SDK's own unit tests, never cross-SDK:

1. backward byte-scanning for the central-directory signature instead of
   properly locating EOCD -> (ZIP64 locator ->) ZIP64 EOCD -> walking exactly
   ``entryCount`` records by declared length,
2. the ZIP64 extra field gated on ``versionNeededToExtract >= 45`` instead of
   purely on the presence of the ``0xFFFFFFFF`` sentinel (APPNOTE 4.5.3),
3. a non-ZIP64 data descriptor writing the uncompressed size into both size
   slots,
4. a signed 32-bit shift corrupting an error message for sizes >= 2 GiB.

The tests below exercise (1) and (2) cross-SDK, at a 128-byte payload rather
than a multi-GiB one: they mutate the container's *trailer* after encryption
(see ``zipmutate.py``), so payload size has no bearing on what they test.
Only web-sdk (``js``) is used as ``encrypt_sdk`` -- it always writes ZIP64
regardless of size, per the ``zip64-at-2gib`` feature in ``tdfs.py`` -- so no
multi-GiB payload is ever needed to manufacture ZIP64 structure here. Every
``decrypt_sdk`` in the run matrix is exercised against each mutated
container.

(3) and (4) are latent/cosmetic single-implementation issues with no
cross-SDK wire disagreement; see the module docstring discussion in the
project plan for why they are out of scope here.

Run it with::

    uv run pytest test_zip_conformance.py --sdks "go java js" -v
"""

import dataclasses
import filecmp
import struct
import subprocess
from pathlib import Path

import pytest

import tdfs
import zipinspect
import zipmutate
from abac import Attribute
from fixtures.encryption import EncryptFactory

# ``no_audit_logs``: nothing here requests the ``audit_logs`` fixture -- this
# module tests container encoding, not KAS rewrap events.
pytestmark = [pytest.mark.zip_conformance, pytest.mark.no_audit_logs]

#: An extended-timestamp extra-field record (header id 0x5455), the shape
#: real writers actually put ahead of a ZIP64 record in the wild.
_FOREIGN_EXTRA_TLV = struct.pack("<HH", 0x5455, 5) + b"\x01\x00\x00\x00\x00"


def _assert_faithful_roundtrip(
    decrypt_sdk: tdfs.SDK, ct_file: Path, rt_file: Path, pt_file: Path
) -> None:
    """Spec-legal-but-unusual structures: decrypt must succeed and be byte-correct.

    No partial credit: a conformant reader has no excuse to reject a
    structure APPNOTE actually permits.
    """
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file, shallow=False), (
        f"{decrypt_sdk} decrypted {ct_file.name} without error but the "
        f"output does not match the original plaintext"
    )


def _assert_no_silent_corruption(
    decrypt_sdk: tdfs.SDK, ct_file: Path, rt_file: Path, pt_file: Path
) -> None:
    """Adversarial structures: either a clean failure, or byte-correct plaintext.

    What must never happen is exiting 0 having decrypted the wrong bytes.
    """
    try:
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    except subprocess.CalledProcessError:
        return
    assert filecmp.cmp(pt_file, rt_file, shallow=False), (
        f"{decrypt_sdk} exited 0 decrypting a deliberately malformed "
        f"{ct_file.name}, but the output does not match the original "
        f"plaintext -- this is silent corruption, not a clean failure"
    )


def _base_container(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    zip_conformance_tdf: EncryptFactory,
    attribute_default_rsa: Attribute,
) -> Path:
    """The one real, unmutated TDF each case starts from.

    Only ``js`` (web-sdk) is used: it always writes ZIP64 regardless of
    payload size, so a 128-byte plaintext already has the structure these
    tests want to reshape. go/java cells for this fixture are skipped
    rather than parametrized away, so each test still reports one cell per
    ``decrypt_sdk`` instead of vanishing from the matrix.
    """
    if encrypt_sdk.sdk != "js":
        pytest.skip(
            "structural mutation needs exactly one producer; js is used "
            "because it always emits ZIP64 regardless of payload size"
        )
    return zip_conformance_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )


def test_zip64_extra_field_not_first_is_still_resolved(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_conformance_pt_file: Path,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """DSPX-4591 finding 2, made cross-SDK.

    A real writer (web-sdk pre-fix) gated ZIP64 resolution on
    ``versionNeededToExtract >= 45``; APPNOTE 4.5.3 keys it purely on the
    ``0xFFFFFFFF`` sentinel. A foreign extra-field TLV -- an extended
    timestamp, which real writers emit -- is placed ahead of the ZIP64 one to
    prove the parse does not assume it comes first either.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    true_offset: int | None = None
    for i, entry in enumerate(trailer.entries):
        if entry.name == "0.manifest.json":
            true_offset = entry.local_header_offset
            trailer.entries[i] = dataclasses.replace(
                entry,
                force_zip64_offset=True,
                extra_prefix=_FOREIGN_EXTRA_TLV,
                version_needed_to_extract=20,
            )
            break
    assert true_offset is not None, f"{ct_file} has no 0.manifest.json entry"

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    cd = zipinspect.central_directory(mutated)
    manifest_entry = next(e for e in cd.entries if e.name == "0.manifest.json")
    assert manifest_entry.has_zip64_extra, (
        "ZIP64 extra field was not resolved when preceded by a foreign extra "
        f"record with version_needed_to_extract=20\n{zipinspect.describe(cd.entries)}"
    )
    assert manifest_entry.uses_zip64_for_offset
    assert manifest_entry.local_header_offset == true_offset

    rt_file = tmp_path / "roundtrip.bin"
    _assert_faithful_roundtrip(decrypt_sdk, mutated, rt_file, zip_conformance_pt_file)


def test_eocd_with_max_length_comment(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_conformance_pt_file: Path,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """A maximum-length (0xFFFF) EOCD comment is spec-legal and must round-trip."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    trailer = dataclasses.replace(trailer, comment=b"c" * 0xFFFF)

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    rt_file = tmp_path / "roundtrip.bin"
    _assert_faithful_roundtrip(decrypt_sdk, mutated, rt_file, zip_conformance_pt_file)


def test_zip64_locator_pushed_past_first_1kib_by_comment(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_conformance_pt_file: Path,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """A ZIP64 EOCD + locator that is not size-mandated is spec-legal.

    Nothing here needs ZIP64 -- the container is a few hundred bytes -- but
    APPNOTE does not forbid using it anyway, and a maximum-length comment
    then pushes the locator behind whatever a reader's naive "look at the
    last 1 KiB" tail read would have found.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    trailer = dataclasses.replace(trailer, force_zip64_eocd=True, comment=b"c" * 0xFFFF)

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    cd = zipinspect.central_directory(mutated)
    assert {e.name for e in cd.entries} == {"0.payload", "0.manifest.json"}, (
        "zipinspect failed to find the ZIP64 locator behind the max-length "
        f"comment\n{zipinspect.describe(cd.entries)}"
    )

    rt_file = tmp_path / "roundtrip.bin"
    _assert_faithful_roundtrip(decrypt_sdk, mutated, rt_file, zip_conformance_pt_file)


@pytest.mark.parametrize("count_offset", [1, None], ids=["real_plus_one", "0xFFFF"])
def test_central_directory_entry_count_is_overstated(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_conformance_pt_file: Path,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
    count_offset: int | None,
):
    """DSPX-4591 finding 1, from the opposite direction.

    An entry count that overstates what the central directory actually holds
    must be refused, not walked past into whatever bytes happen to follow --
    which for a reader that trusts the declared count over the real content
    is exactly the shape of the misparse that finding fixed. The
    ``0xFFFF`` case is the boundary value APPNOTE reserves to mean "see the
    ZIP64 EOCD instead", asserted here with no such record to back it up.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    real_count = len(trailer.entries)
    declared_count = real_count + count_offset if count_offset is not None else 0xFFFF
    trailer = dataclasses.replace(trailer, entry_count_override=declared_count)

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    with pytest.raises(zipinspect.MalformedZipError):
        zipinspect.central_directory(mutated)

    rt_file = tmp_path / "roundtrip.bin"
    _assert_no_silent_corruption(decrypt_sdk, mutated, rt_file, zip_conformance_pt_file)


def test_payload_bytes_containing_a_fake_central_directory_signature(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_conformance_pt_file: Path,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """DSPX-4591 finding 1, the case that motivated it.

    Payload bytes that happen to contain the central-directory signature
    (``PK\\x01\\x02``) must not be mistaken for a directory entry. A reader
    that finds entries by scanning for that signature rather than walking the
    EOCD-declared count from ``cd_offset`` is fooled by this; one anchored on
    the real trailer is not.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    cd_before = zipinspect.central_directory(ct_file)
    mutated = tmp_path / "mutated.tdf"
    zipmutate.corrupt_entry_bytes(
        ct_file, mutated, "0.payload", at=0, patch=zipinspect.CEN_SIG
    )

    cd_after = zipinspect.central_directory(mutated)
    before = [(e.name, e.local_header_offset) for e in cd_before.entries]
    after = [(e.name, e.local_header_offset) for e in cd_after.entries]
    assert after == before, (
        "planting the central-directory signature inside the payload changed "
        "what the trailer-anchored parser reports -- it should not\n"
        + zipinspect.describe(cd_after.entries)
    )

    rt_file = tmp_path / "roundtrip.bin"
    _assert_no_silent_corruption(decrypt_sdk, mutated, rt_file, zip_conformance_pt_file)
