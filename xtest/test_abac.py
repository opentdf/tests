import filecmp
import re
import subprocess
import pytest
from pathlib import Path

import tdfs
from abac import Attribute, ObligationValue
from test_policytypes import skip_rts_as_needed


cipherTexts: dict[str, Path] = {}


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
        output = (exc.output or b'').decode(errors='replace')
        stderr = (exc.stderr or b'').decode(errors='replace')
        combined_output = output + stderr

        for pattern in expected_patterns:
            assert re.search(pattern, combined_output, re.IGNORECASE), \
                f"Expected pattern '{pattern}' not found in output.\nSTDOUT: {output}\nSTDERR: {stderr}"

        if unexpected_patterns:
            for pattern in unexpected_patterns:
                assert not re.search(pattern, combined_output, re.IGNORECASE), \
                    f"Unexpected pattern '{pattern}' found in output.\nSTDOUT: {output}\nSTDERR: {stderr}"


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
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_obligation_test(decrypt_sdk, pfs)
    
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

    rewrap_403_pattern = "tdf: rewrap request 403"
    obligations_pattern = "required\\s+obligations"
    rt_file = tmp_dir / "test-obligations.untdf"
    assert_decrypt_fails_with_patterns(decrypt_sdk=decrypt_sdk,
                                       ct_file=ct_file,
                                       rt_file=rt_file,
                                       container=container,
                                       expected_patterns=[rewrap_403_pattern],
                                       unexpected_patterns=[obligations_pattern])

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
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_obligation_test(decrypt_sdk, pfs)
    
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

    rewrap_403_pattern = "tdf: rewrap request 403"
    obligations_pattern = obligation_value.fqn
    rt_file = tmp_dir / "test-obligations-fulfillable.untdf"
    assert_decrypt_fails_with_patterns(decrypt_sdk=decrypt_sdk,
                                       ct_file=ct_file,
                                       rt_file=rt_file,
                                       container=container,
                                       expected_patterns=[obligations_pattern, rewrap_403_pattern])
