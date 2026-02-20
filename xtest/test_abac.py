import filecmp
import re
import subprocess
from pathlib import Path

import pytest

import tdfs
from abac import Attribute, ObligationValue
from audit_logs import AuditLogAsserter
from test_policytypes import skip_rts_as_needed

cipherTexts: dict[str, Path] = {}
rewrap_403_pattern = (
    "tdf: rewrap request 403|403 for \\[https?://[^\\]]+\\]; rewrap permission denied"
)


dspx1153Fails = []

try:
    dspx1153Fails = [
        tdfs.SDK("go", "v0.15.0"),
    ]
except FileNotFoundError:
    dspx1153Fails = []


def skip_dspx1153(encrypt_sdk: tdfs.SDK, decrypt_sdk: tdfs.SDK):
    if encrypt_sdk != decrypt_sdk and decrypt_sdk in dspx1153Fails:
        pytest.skip("dspx1153 fails with this SDK version combination")


def skip_dspx2457(encrypt_sdk: tdfs.SDK):
    if encrypt_sdk.sdk == "java":
        pytest.skip(
            "DSPX-2457 Java SDK unable to handle KAS grants with different types"
        )


def assert_decrypt_fails_with_patterns(
    decrypt_sdk: tdfs.SDK,
    ct_file: Path,
    rt_file: Path,
    container: tdfs.container_type,
    expected_patterns: list[str],
    unexpected_patterns: list[str] | None = None,
):
    try:
        decrypt_sdk.decrypt(ct_file, rt_file, container, expect_error=True)
        pytest.fail(f"Decrypt succeeded unexpectedly for {ct_file}")
    except subprocess.CalledProcessError as exc:
        output = (exc.output or b"").decode(errors="replace")
        stderr = (exc.stderr or b"").decode(errors="replace")
        combined_output = output + stderr

        for pattern in expected_patterns:
            assert re.search(pattern, combined_output, re.IGNORECASE), (
                f"Expected pattern '{pattern}' not found in output.\nSTDOUT: {output}\nSTDERR: {stderr}"
            )

        if unexpected_patterns:
            for pattern in unexpected_patterns:
                assert not re.search(pattern, combined_output, re.IGNORECASE), (
                    f"Unexpected pattern '{pattern}' found in output.\nSTDOUT: {output}\nSTDERR: {stderr}"
                )


def test_key_mapping_multiple_mechanisms(
    attribute_with_different_kids: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_default: str,
    in_focus: set[tdfs.SDK],
):
    global counter

    tdfs.skip_if_unsupported(encrypt_sdk, "key_management")
    skip_dspx2457(encrypt_sdk)
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"multimechanism-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        # Currently, we only support rsa:2048 and ec:secp256r1
        vals = [
            v
            for v in attribute_with_different_kids.value_fqns
            if v.endswith("/e1") or v.endswith("/r1")
        ]
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=vals,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
    manifest = tdfs.manifest(ct_file)
    assert {kao.kid for kao in manifest.encryptionInformation.keyAccess} == {"r1", "e1"}
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_default

    tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"multimechanism-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_key_mapping_extended_mechanisms(
    attribute_allof_with_extended_mechanisms: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_km1: str,
    kas_url_km2: str,
    in_focus: set[tdfs.SDK],
):
    """Test encryption and decryption with extended cryptographic mechanisms.

    This test verifies support for ec:secp384r1, ec:secp521r1, and rsa:4096
    key types by encrypting with all three mechanisms and successfully decrypting.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "key_management")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    skip_dspx1153(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_allof_with_extended_mechanisms

    sample_name = f"extended-mechanisms-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=attr.value_fqns,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 5

    # Verify that all three key IDs are present in the manifest
    manifest_kids = {kao.kid for kao in manifest.encryptionInformation.keyAccess}
    expected_kids = set(key_ids)
    assert manifest_kids == expected_kids, (
        f"Expected key IDs {expected_kids} but got {manifest_kids}"
    )

    # Verify KAS URLs are from km1 or km2
    manifest_urls = {kao.url for kao in manifest.encryptionInformation.keyAccess}
    assert manifest_urls <= {kas_url_km1, kas_url_km2}, (
        f"Expected KAS URLs to be from km1 or km2, but got {manifest_urls}"
    )

    # Verify EC wrapping support if needed
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")

    # Decrypt and verify
    rt_file = tmp_dir / f"extended-mechanisms-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_key_mapping_extended_ec_mechanisms(
    attribute_allof_with_extended_mechanisms: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_km2: str,
    in_focus: set[tdfs.SDK],
):
    """Test encryption and decryption with extended cryptographic mechanisms.

    This test verifies support for ec:secp384r1, ec:secp521r1, and rsa:4096
    key types by encrypting with all three mechanisms and successfully decrypting.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "key_management")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    skip_dspx1153(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_allof_with_extended_mechanisms

    ec_kids = [kid for kid in key_ids if kid.startswith("e3")]
    ec_vals = [v for v in attr.value_fqns if "ec-secp3" in v]
    assert len(ec_kids) == len(ec_vals), "Mismatch in EC key IDs and attribute values"

    sample_name = f"extended-mechanisms-ec-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=ec_vals,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == len(ec_kids)

    # Verify that all three key IDs are present in the manifest
    manifest_kids = {kao.kid for kao in manifest.encryptionInformation.keyAccess}
    expected_kids = set(ec_kids)
    assert manifest_kids == expected_kids, (
        f"Expected key IDs {expected_kids} but got {manifest_kids}"
    )

    # Verify KAS URLs are from km2
    manifest_urls = {kao.url for kao in manifest.encryptionInformation.keyAccess}
    assert manifest_urls <= {kas_url_km2}, (
        f"Expected KAS URLs to be from km2, but got {manifest_urls}"
    )

    # Decrypt and verify
    rt_file = tmp_dir / f"extended-mechanisms-ec-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_key_mapping_extended_rsa_mechanisms(
    attribute_allof_with_extended_mechanisms: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_km1: str,
    in_focus: set[tdfs.SDK],
):
    """Test encryption and decryption with extended cryptographic mechanisms.

    This test verifies support for ec:secp384r1, ec:secp521r1, and rsa:4096
    key types by encrypting with all three mechanisms and successfully decrypting.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "key_management")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    skip_dspx1153(encrypt_sdk, decrypt_sdk)

    attr, key_ids = attribute_allof_with_extended_mechanisms

    rsa_kids = [kid for kid in key_ids if kid.startswith("r")]
    rsa_vals = [v for v in attr.value_fqns if "rsa-" in v]
    assert len(rsa_kids) == len(rsa_vals), (
        "Mismatch in RSA key IDs and attribute values"
    )

    sample_name = f"extended-mechanisms-rsa-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=rsa_vals,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == len(rsa_kids)

    # Verify that all three key IDs are present in the manifest
    manifest_kids = {kao.kid for kao in manifest.encryptionInformation.keyAccess}
    expected_kids = set(rsa_kids)
    assert manifest_kids == expected_kids, (
        f"Expected key IDs {expected_kids} but got {manifest_kids}"
    )

    # Verify KAS URLs are from km1
    manifest_urls = {kao.url for kao in manifest.encryptionInformation.keyAccess}
    assert manifest_urls <= {kas_url_km1}, (
        f"Expected KAS URLs to be from km1, but got {manifest_urls}"
    )

    # Decrypt and verify
    rt_file = tmp_dir / f"extended-mechanisms-rsa-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_standard(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_alpha: str,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
):
    global counter

    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-one-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=attribute_single_kas_grant.value_fqns,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_alpha

    # Mark timestamp before decrypt for audit log correlation
    mark = audit_logs.mark("before_decrypt")

    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-one-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)

    # Verify rewrap was logged with expected attribute FQNs
    audit_logs.assert_rewrap_success(
        attr_fqns=attribute_single_kas_grant.value_fqns,
        min_count=1,
        since_mark=mark,
    )


def test_autoconfigure_two_kas_or_standard(
    attribute_two_kas_grant_or: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_alpha: str,
    kas_url_beta: str,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-two-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                attribute_two_kas_grant_or.value_fqns[0],
                attribute_two_kas_grant_or.value_fqns[1],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert {kas_url_alpha, kas_url_beta} == {
        kao.url for kao in manifest.encryptionInformation.keyAccess
    }
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")

    # Mark timestamp before decrypt for audit log correlation
    mark = audit_logs.mark("before_decrypt")

    rt_file = tmp_dir / f"test-abac-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)

    # Verify rewrap was logged - for OR policy, SDK only needs one KAS to succeed
    # so we expect at least 1 rewrap event (may be 2 if SDK tries both)
    audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)


def test_autoconfigure_double_kas_and(
    attribute_two_kas_grant_and: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_alpha: str,
    kas_url_beta: str,
    in_focus: set[tdfs.SDK],
    audit_logs: AuditLogAsserter,
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-three-and-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                attribute_two_kas_grant_and.value_fqns[0],
                attribute_two_kas_grant_and.value_fqns[1],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert {kas_url_alpha, kas_url_beta} == {
        kao.url for kao in manifest.encryptionInformation.keyAccess
    }
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")

    # Mark timestamp before decrypt for audit log correlation
    mark = audit_logs.mark("before_decrypt")

    rt_file = tmp_dir / f"test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)

    # Verify rewrap was logged - for AND policy, SDK must contact both KASes
    # so we expect 2 rewrap success events
    audit_logs.assert_rewrap_success(min_count=2, since_mark=mark)


def test_autoconfigure_one_attribute_attr_grant(
    one_attribute_attr_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_gamma: str,
    in_focus: set[tdfs.SDK],
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-one-attr-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                one_attribute_attr_kas_grant.value_fqns[0],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_gamma
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-one-attr-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_attr_and_value_grant(
    attr_and_value_kas_grants_or: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_gamma: str,
    kas_url_alpha: str,
    in_focus: set[tdfs.SDK],
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-attr-val-or-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                attr_and_value_kas_grants_or.value_fqns[0],
                attr_and_value_kas_grants_or.value_fqns[1],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert {kas_url_gamma, kas_url_alpha} == {
        kao.url for kao in manifest.encryptionInformation.keyAccess
    }
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-attr-val-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_and_attr_and_value_grant(
    attr_and_value_kas_grants_and: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_gamma: str,
    kas_url_alpha: str,
    in_focus: set[tdfs.SDK],
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-attr-val-and-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                attr_and_value_kas_grants_and.value_fqns[0],
                attr_and_value_kas_grants_and.value_fqns[1],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert {kas_url_gamma, kas_url_alpha} == {
        kao.url for kao in manifest.encryptionInformation.keyAccess
    }
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-attr-val-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_ns_grant(
    one_attribute_ns_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_delta: str,
    in_focus: set[tdfs.SDK],
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure", "ns_grants")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-one-ns-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                one_attribute_ns_kas_grant.value_fqns[0],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_delta
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-one-ns-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_ns_and_value_grant(
    ns_and_value_kas_grants_or: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_delta: str,
    kas_url_alpha: str,
    in_focus: set[tdfs.SDK],
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure", "ns_grants")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-ns-val-or-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                ns_and_value_kas_grants_or.value_fqns[0],
                ns_and_value_kas_grants_or.value_fqns[1],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert {kas_url_delta, kas_url_alpha} == {
        kao.url for kao in manifest.encryptionInformation.keyAccess
    }
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-ns-val-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_and_ns_and_value_grant(
    ns_and_value_kas_grants_and: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_delta: str,
    kas_url_alpha: str,
    in_focus: set[tdfs.SDK],
):
    skip_dspx1153(encrypt_sdk, decrypt_sdk)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure", "ns_grants")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-ns-val-and-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=[
                ns_and_value_kas_grants_and.value_fqns[0],
                ns_and_value_kas_grants_and.value_fqns[1],
            ],
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert {kas_url_delta, kas_url_alpha} == {
        kao.url for kao in manifest.encryptionInformation.keyAccess
    }
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-ns-val-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_obligations_not_entitled(
    obligation_setup_no_scs_unscoped_trigger: tuple[Attribute, ObligationValue],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    container: tdfs.container_type,
):
    """
    Test that no required obligations are returned when the user is not entitled
    to the data.
    """
    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container=container, in_focus=in_focus)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")

    # Skip platform compatibility checks
    tdfs.skip_if_unsupported(decrypt_sdk, "obligations")

    # Unpack the test setup
    attr, _ = obligation_setup_no_scs_unscoped_trigger

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations.ztdf"
    assert attr.values, "Attribute has no values"
    attr_val = attr.values[0]
    assert attr_val is not None and attr_val.fqn, "Attribute value is invalid"

    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr_val.fqn],
        container=container,
    )

    obligations_pattern = "required\\s*obligations"
    rt_file = tmp_dir / "test-obligations.untdf"

    assert_decrypt_fails_with_patterns(
        decrypt_sdk=decrypt_sdk,
        ct_file=ct_file,
        rt_file=rt_file,
        container=container,
        expected_patterns=[rewrap_403_pattern],
        unexpected_patterns=[obligations_pattern],
    )


def test_obligations_not_fulfillable(
    obligation_setup_scs_unscoped_trigger: tuple[Attribute, ObligationValue],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    container: tdfs.container_type,
):
    """
    Test that required obligations are returned when the user is entitled
    to the data but cannot fulfill the obligations.
    """

    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container=container, in_focus=in_focus)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")

    # Skip platform compatibility checks
    tdfs.skip_if_unsupported(decrypt_sdk, "obligations")

    # Unpack the test setup
    attr, obligation_value = obligation_setup_scs_unscoped_trigger
    assert attr.values, "Attribute has no values"
    attr_val = attr.values[0]
    assert attr_val is not None and attr_val.fqn, "Attribute value is invalid"

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations-fulfillable.ztdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr_val.fqn],
        container=container,
    )

    obligations_pattern = obligation_value.fqn
    assert obligations_pattern, "Obligation fqn is invalid"
    rt_file = tmp_dir / "test-obligations-fulfillable.untdf"
    assert_decrypt_fails_with_patterns(
        decrypt_sdk=decrypt_sdk,
        ct_file=ct_file,
        rt_file=rt_file,
        container=container,
        expected_patterns=[obligations_pattern, rewrap_403_pattern],
    )


def test_obligations_client_not_scoped(
    obligation_setup_scs_scoped_trigger_different_client: tuple[
        Attribute, ObligationValue
    ],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    container: tdfs.container_type,
):
    """
    Otdf client is not scoped to the trigger, so it should be able to decrypt the data.
    """
    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container=container, in_focus=in_focus)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")

    # Skip platform compatibility checks
    tdfs.skip_if_unsupported(decrypt_sdk, "obligations")

    # Unpack the test setup
    attr, _ = obligation_setup_scs_scoped_trigger_different_client
    assert attr.values, "Attribute has no values"
    attr_val = attr.values[0]
    assert attr_val is not None and attr_val.fqn, "Attribute value is invalid"

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations-fulfillable.ztdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr_val.fqn],
        container=container,
    )

    rt_file = tmp_dir / "test-obligations-fulfillable.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container, expect_error=False)

    # Assert that the decrypted file matches the original plaintext file
    assert filecmp.cmp(pt_file, rt_file), (
        f"Decrypted file {rt_file} does not match original {pt_file}"
    )


def test_obligations_client_scoped(
    obligation_setup_scs_scoped_trigger: tuple[Attribute, ObligationValue],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    container: tdfs.container_type,
):
    """
    Otdf client is scoped to the trigger, so it should NOT be able to decrypt the data.
    """
    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container=container, in_focus=in_focus)
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")

    # Skip platform compatibility checks
    tdfs.skip_if_unsupported(decrypt_sdk, "obligations")

    # Unpack the test setup
    attr, obligation_value = obligation_setup_scs_scoped_trigger
    assert attr.values, "Attribute has no values"
    attr_val = attr.values[0]
    assert attr_val is not None and attr_val.fqn, "Attribute value is invalid"

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations-fulfillable.ztdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr_val.fqn],
        container=container,
    )

    obligations_pattern = obligation_value.fqn
    assert obligations_pattern, "Obligation fqn is invalid"
    rt_file = tmp_dir / "test-obligations-fulfillable.untdf"
    assert_decrypt_fails_with_patterns(
        decrypt_sdk=decrypt_sdk,
        ct_file=ct_file,
        rt_file=rt_file,
        container=container,
        expected_patterns=[obligations_pattern, rewrap_403_pattern],
    )


"""
Key management tests

Note:
These tests should be last, because one sets a default key on the platform
that cannot currently be unset.
"""


def test_autoconfigure_key_management_two_kas_two_keys(
    attribute_allof_with_two_managed_keys: tuple[Attribute, list[str]],
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_km1: str,
    kas_url_km2: str,
    in_focus: set[tdfs.SDK],
):
    """Encrypts with an ALL_OF attribute that has two managed keys and decrypts successfully.

    Verifies that the manifest contains two keyAccess entries pointing to km1/km2
    with KIDs matching the managed keys created by the fixture.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "key_management")
    tdfs.skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_dspx2457(encrypt_sdk)
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"km-allof-two-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = tmp_dir / f"{sample_name}.tdf"
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            mime_type="text/plain",
            container="ztdf",
            attr_values=attribute_allof_with_two_managed_keys[0].value_fqns,
            target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    # The managed key fixture uses key ids 'km1-rsa' and 'km2-ec'
    assert {kao.kid for kao in manifest.encryptionInformation.keyAccess} == {
        attribute_allof_with_two_managed_keys[1][0],
        attribute_allof_with_two_managed_keys[1][1],
    }
    assert {kao.url for kao in manifest.encryptionInformation.keyAccess} == {
        kas_url_km1,
        kas_url_km2,
    }

    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"km-allof-two-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_import_legacy_golden_r1_key_and_decrypt_no_split(
    legacy_imported_golden_r1_key,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(decrypt_sdk, "key_management")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")

    from test_legacy import get_golden_file

    golden_file_name = "key-management-no-split-golden"
    ct_file = get_golden_file(f"{golden_file_name}.tdf")
    rt_file = tmp_dir / f"{golden_file_name}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    with rt_file.open("r", encoding="utf-8") as f:
        assert f.read().strip() == "hello"


def test_encrypt_decrypt_all_containers_with_base_key_e1(
    base_key_e1,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    container: tdfs.container_type,
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_if_unsupported(encrypt_sdk, "key_management")
    tdfs.skip_if_unsupported(decrypt_sdk, "key_management")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"base-e1-{encrypt_sdk}"
    ct_file = tmp_dir / f"{sample_name}.tdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        container=container,
    )

    rt_file = tmp_dir / f"{sample_name}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container=container)
    assert filecmp.cmp(pt_file, rt_file)
