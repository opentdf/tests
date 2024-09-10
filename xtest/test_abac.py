import filecmp
import pytest

import tdfs


cipherTexts = {}


def test_autoconfigure_one_attribute(
    attribute_single_kas_grant, encrypt_sdk, decrypt_sdk, tmp_dir, pt_file
):
    global counter
    # We have a grant for alpha to localhost kas. Now try to use it...

    if encrypt_sdk not in ["go", "java"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

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
            attr_values=[attribute_single_kas_grant.values[0].fqn],
        )
        cipherTexts[sample_name] = ct_file
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1

    rt_file = f"{tmp_dir}test-abac-one-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or(
    attribute_two_kas_grant_or,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url1: str,
    kas_url2: str,
):
    if encrypt_sdk not in ["go", "java"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

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
                attribute_two_kas_grant_or.values[0].fqn,
                attribute_two_kas_grant_or.values[1].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file
    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set([kas_url1, kas_url2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )

    rt_file = f"{tmp_dir}test-abac-or-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_double_kas_and(
    attribute_two_kas_grant_and,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url1: str,
    kas_url2: str,
):
    if encrypt_sdk not in ["go", "java"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

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
                attribute_two_kas_grant_and.values[0].fqn,
                attribute_two_kas_grant_and.values[1].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set([kas_url1, kas_url2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_attr_grant(
    one_attribute_attr_kas_grant,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url2: str,
):
    if encrypt_sdk not in ["go", "java"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

    # We have a grant for letra to localhost kas. Now try to use it...

    print(one_attribute_attr_kas_grant.values)

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
                one_attribute_attr_kas_grant.values[0].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    print(manifest.encryptionInformation.keyAccess)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url2
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_attr_and_value_grant(
    attr_and_value_kas_grants_or,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url1: str,
    kas_url2: str,
):
    if encrypt_sdk not in ["go", "java"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

    # We have a grant for letra to localhost kas. Now try to use it...

    print(attr_and_value_kas_grants_or.values)

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
                attr_and_value_kas_grants_or.values[0].fqn,
                attr_and_value_kas_grants_or.values[1].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    print(manifest.encryptionInformation.keyAccess)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set([kas_url1, kas_url2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_and_attr_and_value_grant(
    attr_and_value_kas_grants_and,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url1: str,
    kas_url2: str,
):
    if encrypt_sdk not in ["go", "java"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

    # We have a grant for letra to localhost kas. Now try to use it...

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
                attr_and_value_kas_grants_and.values[0].fqn,
                attr_and_value_kas_grants_and.values[1].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set([kas_url1, kas_url2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_one_attribute_ns_grant(
    one_attribute_ns_kas_grant,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url2: str,
):
    if encrypt_sdk not in ["go"]:
        pytest.skip(
            f"sdk doesn't yet support autoconfigure or namespace grants [{encrypt_sdk}]"
        )

    # We have a grant for letra to localhost kas. Now try to use it...

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
                one_attribute_ns_kas_grant.values[0].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 1
    assert manifest.encryptionInformation.keyAccess[0].url == kas_url2
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_or_ns_and_value_grant(
    ns_and_value_kas_grants_or,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url1: str,
    kas_url2: str,
):
    if encrypt_sdk not in ["go"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

    # We have a grant for letra to localhost kas. Now try to use it...

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
                ns_and_value_kas_grants_or.values[0].fqn,
                ns_and_value_kas_grants_or.values[1].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        == manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set([kas_url1, kas_url2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


def test_autoconfigure_two_kas_and_ns_and_value_grant(
    ns_and_value_kas_grants_and,
    encrypt_sdk,
    decrypt_sdk,
    tmp_dir,
    pt_file,
    kas_url1: str,
    kas_url2: str,
):
    if encrypt_sdk not in ["go"]:
        pytest.skip(f"sdk doesn't yet support autoconfigure [{encrypt_sdk}]")

    # We have a grant for letra to localhost kas. Now try to use it...

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
                ns_and_value_kas_grants_and.values[0].fqn,
                ns_and_value_kas_grants_and.values[1].fqn,
            ],
        )
        cipherTexts[sample_name] = ct_file

    manifest = tdfs.manifest(ct_file)
    assert len(manifest.encryptionInformation.keyAccess) == 2
    assert (
        manifest.encryptionInformation.keyAccess[0].sid
        != manifest.encryptionInformation.keyAccess[1].sid
    )
    assert set([kas_url1, kas_url2]) == set(
        [kao.url for kao in manifest.encryptionInformation.keyAccess]
    )
    rt_file = f"{tmp_dir}test-abac-and-{encrypt_sdk}-{decrypt_sdk}.untdf"
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)
