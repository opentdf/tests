import filecmp
import pytest
from pathlib import Path

import tdfs
from abac import Attribute


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
            if v.endswith("/e1") or v.endswith("/r1") or v.endswith("/r4")
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
        ["r1", "e1", "r4"]
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
