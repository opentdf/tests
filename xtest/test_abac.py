import filecmp
import os
import re
import subprocess
import pytest
from pathlib import Path

import tdfs
from abac import Attribute, ObligationValue
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
            assert re.search(
                pattern, combined_output, re.IGNORECASE
            ), f"Expected pattern '{pattern}' not found in output.\nSTDOUT: {output}\nSTDERR: {stderr}"

        if unexpected_patterns:
            for pattern in unexpected_patterns:
                assert not re.search(
                    pattern, combined_output, re.IGNORECASE
                ), f"Unexpected pattern '{pattern}' found in output.\nSTDOUT: {output}\nSTDERR: {stderr}"


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
    assert set([kao.kid for kao in manifest.encryptionInformation.keyAccess]) == set(
        ["r1", "e1"]
    )
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_default

    tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"multimechanism-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_standard(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_value1: str,
    in_focus: set[tdfs.SDK],
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
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_value1

    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-one-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_standard(
    attribute_two_kas_grant_or: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_value1: str,
    kas_url_value2: str,
    in_focus: set[tdfs.SDK],
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
    assert set([kas_url_value1, kas_url_value2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_double_kas_and(
    attribute_two_kas_grant_and: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_value1: str,
    kas_url_value2: str,
    in_focus: set[tdfs.SDK],
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
    assert set([kas_url_value1, kas_url_value2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    if any(
        kao.type == "ec-wrapped" for kao in manifest.encryptionInformation.keyAccess
    ):
        tdfs.skip_if_unsupported(decrypt_sdk, "ecwrap")
    rt_file = tmp_dir / f"test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_attr_grant(
    one_attribute_attr_kas_grant: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    kas_url_attr: str,
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
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_attr
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
    kas_url_attr: str,
    kas_url_value1: str,
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
    assert set([kas_url_attr, kas_url_value1]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
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
    kas_url_attr: str,
    kas_url_value1: str,
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
    assert set([kas_url_attr, kas_url_value1]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
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
    kas_url_ns: str,
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
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_ns
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
    kas_url_ns: str,
    kas_url_value1: str,
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
    assert set([kas_url_ns, kas_url_value1]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
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
    kas_url_ns: str,
    kas_url_value1: str,
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
    assert set([kas_url_ns, kas_url_value1]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
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
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr.values[0].fqn],
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

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations-fulfillable.ztdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr.values[0].fqn],
        container=container,
    )

    obligations_pattern = obligation_value.fqn
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

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations-fulfillable.ztdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr.values[0].fqn],
        container=container,
    )

    rt_file = tmp_dir / "test-obligations-fulfillable.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container, expect_error=False)

    # Assert that the decrypted file matches the original plaintext file
    assert filecmp.cmp(
        pt_file, rt_file
    ), f"Decrypted file {rt_file} does not match original {pt_file}"


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

    # Encrypt the file with the attribute
    ct_file = tmp_dir / "test-obligations-fulfillable.ztdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        attr_values=[attr.values[0].fqn],
        container=container,
    )

    obligations_pattern = obligation_value.fqn
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
    assert set([kao.kid for kao in manifest.encryptionInformation.keyAccess]) == {
        attribute_allof_with_two_managed_keys[1][0],
        attribute_allof_with_two_managed_keys[1][1],
    }
    assert set([kao.url for kao in manifest.encryptionInformation.keyAccess]) == {
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
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")

    from test_legacy import get_golden_file

    golden_file_name = "golden_file_no_split_key_management"
    ct_file = get_golden_file(f"{golden_file_name}.tdf")
    rt_file = tmp_dir / f"{golden_file_name}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 5 * 2**10
    expected_bytes = bytes([0] * 1024)
    with rt_file.open("rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


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
