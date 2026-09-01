"""Regression test for opentdf/platform#3645.

Without the []string -> []any coercion in multi-strategy/service.go, the v2
ResolveEntities handler drops the resolved entity via `continue` after
structpb.NewStruct rejects []string in result.Metadata["attempted_strategies"].
KAS then sees an empty EntityRepresentations, PDP has no subject entity to
evaluate, and rewrap returns PermissionDenied.

This test targets a dedicated `platform-ers-ms` instance (localhost:8090)
running in multi-strategy ERS mode with a SQL provider. otdf-local boots
this instance alongside the default Keycloak-ERS platform. Existing xtests
never touch these fixtures and are unaffected.

Bug trigger: encrypt with an attribute whose KAS grant points at the ers-ms
KAS (8090). The TDF manifest's keyAccess.url becomes 8090/kas, so decrypt
naturally routes rewrap through the ers-ms platform. The multi-strategy
SQL provider matches the azp=opentdf claim, queries ers_attributes for
username='opentdf', and returns department=finance. The subject condition
`.department = finance` gates the attribute, so PDP grants and rewrap
succeeds -- IFF result.Metadata serializes correctly.
"""

import filecmp

import pytest

import tdfs
from abac import AttributeValue
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory


def test_multistrategy_sql_rewrap_succeeds(
    attribute_ers_ms_finance_grant: AttributeValue,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    kas_url_ers_ms: str,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
    encrypted_tdf: EncryptFactory,
    pt_file,
):
    """End-to-end rewrap through the multi-strategy ERS platform.

    Passes on any platform ref that has the []string -> []any coercion fix
    for `attempted_strategies` in service/entityresolution/multi-strategy/
    service.go. Fails on any ref that doesn't -- decrypt returns 403 and
    the ers-ms platform log contains `proto: invalid type: []string`.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")

    finance_fqn = attribute_ers_ms_finance_grant.fqn
    assert finance_fqn is not None

    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=[finance_fqn],
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )

    # Sanity: the TDF must route rewrap through the ers-ms KAS -- otherwise
    # the test would exercise the default Keycloak-ERS platform and prove
    # nothing about multi-strategy.
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_ers_ms, (
        f"expected KAS URL {kas_url_ers_ms} in manifest, got "
        f"{manifest.encryptionInformation.keyAccess[0].url}"
    )

    mark = audit_logs.mark("before_ers_ms_decrypt")

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)

    audit_logs.assert_rewrap_success(
        attr_fqns=[finance_fqn],
        min_count=1,
        since_mark=mark,
    )
