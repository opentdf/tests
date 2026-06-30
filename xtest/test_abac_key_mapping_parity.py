"""Cross-SDK parity for GetKeyMappingsByFqns-based key split resolution.

Verifies that a go SDK build which resolves key splits via the new
GetKeyMappingsByFqns RPC produces the same TDF key-access split structure as a
previous released go SDK (which walks the full attribute set), and that the two
containers cross-decrypt.

Status: initial scaffold. It can only pass once both of the following hold, so it
skips otherwise:
  - the platform under test exposes GetKeyMappingsByFqns (the
    ``key_mapping_resolution`` feature, pinned to the release that ships
    opentdf/platform#3634), and
  - a "new" go SDK build that uses the new granter (opentdf/platform#3699) is
    present in ``sdk/go/dist`` alongside a previous released go SDK.

Coverage is currently value-level mapped keys, since otdfctl.py only exposes
``key_assign_value``. Definition- and namespace-level mapped-key cases, and
any_of / hierarchy rules with keys on distinct KASes, are TODO and need
``key_assign_attribute`` / ``key_assign_namespace`` helpers plus multi-KAS keyed
fixtures.
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


def test_key_mapping_split_parity_value_level(
    attribute_with_different_kids: Attribute,
    pt_file: Path,
    tmp_dir: Path,
):
    pfs = tdfs.get_platform_features()
    pfs.skip_if_unsupported("key_management", "key_mapping_resolution")
    new_sdk, prev_sdk = _go_sdk_pair()

    fqns = attribute_with_different_kids.value_fqns

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
