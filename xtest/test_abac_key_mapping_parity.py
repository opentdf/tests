"""Cross-SDK parity for GetKeyMappingsByFqns-based key split resolution.

Verifies that a go SDK build which resolves key splits via the new
GetKeyMappingsByFqns RPC produces the same TDF key-access split structure as a
previous released go SDK (which walks the full attribute set via
GetAttributeValuesByFqns), and that the two containers cross-decrypt.

The server now resolves both mapped keys and legacy KAS grants inside
GetKeyMappingsByFqns (value > definition > namespace; grants with a cached public
key are converted to keys). The go SDK falls back to GetAttributeValuesByFqns
only for values the server returns no keys for (remote/uncached-key grants), so
split output should match the previous SDK for every configuration below.

Status: scaffold. It skips unless both hold:
  - the platform exposes GetKeyMappingsByFqns (``key_mapping_resolution`` feature,
    pinned to the release that ships opentdf/platform#3634), and
  - a "new" go SDK build using the new granter (opentdf/platform#3699) is present
    in ``sdk/go/dist`` alongside a previous released go SDK.

Coverage: value-level keys across single-KAS multi-KID, two-KAS ANY_OF (share),
and multi-value ALL_OF (split) configurations. NOTE: on platforms with
``key_management`` the two_kas_grant fixtures assign *mapped keys* (grants
auto-convert), so this suite exercises the mapped-key path plus grant→key
conversion for cached-key KAS. A dedicated *legacy-grant-only* parity case (grants
that never convert) is a TODO: it needs a fixture that forces ``grant_assign_value``
even when ``key_management`` is supported.
"""

import filecmp
from pathlib import Path

import pytest

import tdfs
from abac import Attribute


def _split_structure(m: tdfs.Manifest) -> set[frozenset[tuple[str, str | None]]]:
    """Map each split (grouped by split id) to its set of (kas_url, kid) pairs.

    Split ids are random per encrypt, so the collection of (url, kid) sets is the
    stable, comparable representation of the split plan.
    """
    by_sid: dict[str, set[tuple[str, str | None]]] = {}
    for kao in m.encryptionInformation.keyAccess:
        by_sid.setdefault(kao.sid or "", set()).add((kao.url, kao.kid))
    return {frozenset(pairs) for pairs in by_sid.values()}


def _go_sdk_pair() -> tuple[tdfs.SDK, tdfs.SDK]:
    go = tdfs.all_versions_of("go")
    new = next((s for s in go if not s.is_released()), None)
    prev = next((s for s in go if s.is_released()), None)
    if new is None or prev is None:
        pytest.skip("requires both a new (main/sha) and a previous released go SDK build")
    return new, prev


def _assert_split_parity(attr: Attribute, pt_file: Path, tmp_dir: Path) -> None:
    """Encrypt the same plaintext with the new and previous go SDK over the
    attribute's value FQNs, assert identical split structure, and cross-decrypt."""
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "key_mapping_resolution")
    new_sdk, prev_sdk = _go_sdk_pair()

    fqns = attr.value_fqns
    new_ct = tmp_dir / "parity-new.tdf"
    prev_ct = tmp_dir / "parity-prev.tdf"
    new_sdk.encrypt(pt_file, new_ct, container="ztdf", attr_values=fqns)
    prev_sdk.encrypt(pt_file, prev_ct, container="ztdf", attr_values=fqns)

    # Server-resolved splits (new SDK) must match client-resolved splits (previous SDK).
    assert _split_structure(tdfs.manifest(new_ct)) == _split_structure(
        tdfs.manifest(prev_ct)
    )

    # The two containers must also cross-decrypt.
    for ct, decrypt_sdk in ((new_ct, prev_sdk), (prev_ct, new_sdk)):
        rt = tmp_dir / f"{ct.stem}.untdf"
        decrypt_sdk.decrypt(ct, rt, "ztdf")
        assert filecmp.cmp(pt_file, rt)


def test_key_mapping_split_parity_single_kas_multikid(
    attribute_with_different_kids: Attribute,
    pt_file: Path,
    tmp_dir: Path,
):
    # Single KAS, two value-level keys with different KIDs.
    _assert_split_parity(attribute_with_different_kids, pt_file, tmp_dir)


def test_key_mapping_split_parity_two_kas_any_of(
    attribute_two_kas_grant_or: Attribute,
    pt_file: Path,
    tmp_dir: Path,
):
    # ANY_OF across two distinct KAS (a share). Exercises rule-driven combine.
    _assert_split_parity(attribute_two_kas_grant_or, pt_file, tmp_dir)


def test_key_mapping_split_parity_all_of(
    attribute_two_kas_grant_and: Attribute,
    pt_file: Path,
    tmp_dir: Path,
):
    # ALL_OF across multiple values/KAS (a split). Exercises rule-driven combine.
    _assert_split_parity(attribute_two_kas_grant_and, pt_file, tmp_dir)
