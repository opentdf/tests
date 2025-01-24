import filecmp
import pytest

import tdfs
from xtest.abac import Attribute


cipherTexts: dict[str, str] = {}


def test_autoconfigure_one_attribute(
    attribute_single_kas_grant: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_value1: str,
):
    global counter
    # We have a grant for alpha to localhost kas. Now try to use it...

    skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-one-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}{sample_name}.tdf"
        cipherTexts[sample_name] = ct_file
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=attribute_single_kas_grant.value_fqns,
        )
        cipherTexts[sample_name] = ct_file
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_value1

    rt_file = f"{tmp_dir}test-abac-one-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or(
    attribute_two_kas_grant_or: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_value1: str,
    kas_url_value2: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-two-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                attribute_two_kas_grant_or.value_fqns[0],
                attribute_two_kas_grant_or.value_fqns[1],
            ],
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

    rt_file = f"{tmp_dir}test-abac-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def skip_if_unsupported(sdk: tdfs.sdk_type, *features: tdfs.feature_type):
    for feature in features:
        if not tdfs.supports(sdk, feature):
            pytest.skip(f"{sdk} sdk doesn't yet support [{feature}]")


def skip_hexless_skew(encrypt_sdk: tdfs.sdk_type, decrypt_sdk: tdfs.sdk_type):
    if tdfs.supports(encrypt_sdk, "hexless") and not tdfs.supports(
        decrypt_sdk, "hexless"
    ):
        pytest.skip(
            f"{decrypt_sdk} sdk doesn't yet support [hexless], but {encrypt_sdk} does"
        )


def test_autoconfigure_double_kas_and(
    attribute_two_kas_grant_and: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_value1: str,
    kas_url_value2: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-three-and-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                attribute_two_kas_grant_and.value_fqns[0],
                attribute_two_kas_grant_and.value_fqns[1],
            ],
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
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_attr_grant(
    one_attribute_attr_kas_grant: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_attr: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-one-attr-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                one_attribute_attr_kas_grant.value_fqns[0],
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_attr
    rt_file = f"{tmp_dir}test-abac-one-attr-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_attr_and_value_grant(
    attr_and_value_kas_grants_or: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_attr: str,
    kas_url_value1: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-attr-val-or-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                attr_and_value_kas_grants_or.value_fqns[0],
                attr_and_value_kas_grants_or.value_fqns[1],
            ],
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
    rt_file = f"{tmp_dir}test-abac-attr-val-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_and_attr_and_value_grant(
    attr_and_value_kas_grants_and: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_attr: str,
    kas_url_value1: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-attr-val-and-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                attr_and_value_kas_grants_and.value_fqns[0],
                attr_and_value_kas_grants_and.value_fqns[1],
            ],
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
    rt_file = f"{tmp_dir}test-abac-attr-val-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_ns_grant(
    one_attribute_ns_kas_grant: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_ns: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure", "ns_grants")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-one-ns-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                one_attribute_ns_kas_grant.value_fqns[0],
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url_ns
    rt_file = f"{tmp_dir}test-abac-one-ns-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_ns_and_value_grant(
    ns_and_value_kas_grants_or: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_ns: str,
    kas_url_value1: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure", "ns_grants")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-ns-val-or-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                ns_and_value_kas_grants_or.value_fqns[0],
                ns_and_value_kas_grants_or.value_fqns[1],
            ],
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
    rt_file = f"{tmp_dir}test-abac-ns-val-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_and_ns_and_value_grant(
    ns_and_value_kas_grants_and: Attribute,
    encrypt_sdk: tdfs.sdk_type,
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir: str,
    pt_file: str,
    kas_url_ns: str,
    kas_url_value1: str,
):
    skip_if_unsupported(encrypt_sdk, "autoconfigure", "ns_grants")
    skip_hexless_skew(encrypt_sdk, decrypt_sdk)

    sample_name = f"test-abac-ns-val-and-{encrypt_sdk}"
    if sample_name in cipherTexts:
        ct_file = cipherTexts[sample_name]
    else:
        ct_file = f"{tmp_dir}/{sample_name}.tdf"
        tdfs.encrypt(
            encrypt_sdk,
            pt_file,
            ct_file,
            mime_type="text/plain",
            fmt="ztdf",
            attr_values=[
                ns_and_value_kas_grants_and.value_fqns[0],
                ns_and_value_kas_grants_and.value_fqns[1],
            ],
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
    rt_file = f"{tmp_dir}test-abac-ns-val-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
