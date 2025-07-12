import filecmp
import subprocess
import pytest
from pathlib import Path

import tdfs
from abac import Attribute


cipherTexts: dict[str, Path] = {}


def test_or_attributes_success(
    attribute_with_or_type: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if container == "ztdf-ecwrap":
        if not encrypt_sdk.supports("ecwrap"):
            pytest.skip(f"{encrypt_sdk} sdk doesn't yet support ecwrap bindings")
        if "ecwrap" not in pfs.features:
            pytest.skip(
                f"{pfs.version} opentdf platform doesn't yet support ecwrap bindings"
            )
        # Unlike javascript, Java and Go don't support ecwrap if on older versions since they don't pass on the ephemeral public key
        if decrypt_sdk.sdk != "js" and not decrypt_sdk.supports("ecwrap"):
            pytest.skip(
                f"{decrypt_sdk} sdk doesn't support ecwrap bindings for decrypt"
            )

    attrs = attribute_with_or_type.values
    assert attrs and len(attrs) == 2, "Expected exactly two attributes for OR type"
    (alpha, beta) = attrs
    samples = [
        ([alpha], True),
        ([beta], False),
        ([alpha, beta], True),
    ]

    for vals_to_use, expect_success in samples:
        assert len([v.fqn for v in vals_to_use if v.fqn is None]) == 0
        fqns = [v.fqn for v in vals_to_use if v.fqn is not None]
        assert len(fqns) == len(vals_to_use)
        short_names = [v.value for v in vals_to_use]
        assert len(fqns) == len(vals_to_use)
        sample_name = f"pt-or-{'-'.join(short_names)}-{encrypt_sdk}.{container}"
        if sample_name in cipherTexts:
            ct_file = cipherTexts[sample_name]
        else:
            ct_file = tmp_dir / f"{sample_name}"
            # Currently, we only support rsa:2048 and ec:secp256r1
            encrypt_sdk.encrypt(
                pt_file,
                ct_file,
                mime_type="text/plain",
                container=container,
                attr_values=fqns,
                target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
            )
            cipherTexts[sample_name] = ct_file

        rt_file = tmp_dir / f"{sample_name}.returned"
        if expect_success:
            decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
            assert filecmp.cmp(pt_file, rt_file)
        else:
            try:
                decrypt_sdk.decrypt(ct_file, rt_file, "ztdf", expect_error=True)
                assert False, "decrypt succeeded unexpectedly"
            except subprocess.CalledProcessError as exc:
                assert b"forbidden" in exc.output or exc.stderr


def test_and_attributes_success(
    attribute_with_and_type: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
):
    """
    Test AND attribute policy type.

    The user only has alpha assigned (not beta), so should be able to access files
    with only alpha but not files with beta or both alpha and beta.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if container == "ztdf-ecwrap":
        if not encrypt_sdk.supports("ecwrap"):
            pytest.skip(f"{encrypt_sdk} sdk doesn't yet support ecwrap bindings")
        if "ecwrap" not in pfs.features:
            pytest.skip(
                f"{pfs.version} opentdf platform doesn't yet support ecwrap bindings"
            )
        if decrypt_sdk.sdk != "js" and not decrypt_sdk.supports("ecwrap"):
            pytest.skip(
                f"{decrypt_sdk} sdk doesn't support ecwrap bindings for decrypt"
            )

    attrs = attribute_with_and_type.values
    assert attrs and len(attrs) == 2, "Expected exactly two attributes for AND type"
    (alpha, beta) = attrs
    samples = [
        ([alpha], True),  # Should succeed: user has alpha assigned
        ([beta], False),  # Should fail: user doesn't have beta assigned
        ([alpha, beta], False),  # Should fail: user only has alpha assigned, not both
    ]

    for vals_to_use, expect_success in samples:
        assert len([v.fqn for v in vals_to_use if v.fqn is None]) == 0
        fqns = [v.fqn for v in vals_to_use if v.fqn is not None]
        assert len(fqns) == len(vals_to_use)
        short_names = [v.value for v in vals_to_use]
        assert len(fqns) == len(vals_to_use)
        sample_name = f"pt-and-{'-'.join(short_names)}-{encrypt_sdk}.{container}"
        if sample_name in cipherTexts:
            ct_file = cipherTexts[sample_name]
        else:
            ct_file = tmp_dir / f"{sample_name}"
            encrypt_sdk.encrypt(
                pt_file,
                ct_file,
                mime_type="text/plain",
                container=container,
                attr_values=fqns,
                target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
            )
            cipherTexts[sample_name] = ct_file

        rt_file = tmp_dir / f"{sample_name}.returned"
        if expect_success:
            decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
            assert filecmp.cmp(pt_file, rt_file)
        else:
            try:
                decrypt_sdk.decrypt(ct_file, rt_file, "ztdf", expect_error=True)
                assert False, "decrypt succeeded unexpectedly"
            except subprocess.CalledProcessError as exc:
                assert b"forbidden" in exc.output or exc.stderr


def test_hierarchy_attributes_success(
    attribute_with_hierarchy_type: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
):
    """
    Test HIERARCHY attribute policy type.

    The hierarchy is alpha (highest) > beta > gamma (lowest).
    The user has beta assigned, so should be able to access files with beta or gamma,
    but not files with alpha.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    if container == "ztdf-ecwrap":
        if not encrypt_sdk.supports("ecwrap"):
            pytest.skip(f"{encrypt_sdk} sdk doesn't yet support ecwrap bindings")
        if "ecwrap" not in pfs.features:
            pytest.skip(
                f"{pfs.version} opentdf platform doesn't yet support ecwrap bindings"
            )
        if decrypt_sdk.sdk != "js" and not decrypt_sdk.supports("ecwrap"):
            pytest.skip(
                f"{decrypt_sdk} sdk doesn't support ecwrap bindings for decrypt"
            )

    attrs = attribute_with_hierarchy_type.values
    assert (
        attrs and len(attrs) == 3
    ), "Expected exactly three attributes for HIERARCHY type"
    (alpha, beta, gamma) = attrs
    samples = [
        ([alpha], False),  # Should fail: user has beta, not alpha (higher level)
        ([beta], True),  # Should succeed: user has beta assigned
        ([gamma], True),  # Should succeed: user has beta which is higher than gamma
    ]

    for vals_to_use, expect_success in samples:
        assert len([v.fqn for v in vals_to_use if v.fqn is None]) == 0
        fqns = [v.fqn for v in vals_to_use if v.fqn is not None]
        assert len(fqns) == len(vals_to_use)
        short_names = [v.value for v in vals_to_use]
        assert len(fqns) == len(vals_to_use)
        sample_name = f"pt-hierarchy-{'-'.join(short_names)}-{encrypt_sdk}.{container}"
        if sample_name in cipherTexts:
            ct_file = cipherTexts[sample_name]
        else:
            ct_file = tmp_dir / f"{sample_name}"
            encrypt_sdk.encrypt(
                pt_file,
                ct_file,
                mime_type="text/plain",
                container=container,
                attr_values=fqns,
                target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
            )
            cipherTexts[sample_name] = ct_file

        rt_file = tmp_dir / f"{sample_name}.returned"
        if expect_success:
            decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
            assert filecmp.cmp(pt_file, rt_file)
        else:
            try:
                decrypt_sdk.decrypt(ct_file, rt_file, "ztdf", expect_error=True)
                assert False, "decrypt succeeded unexpectedly"
            except subprocess.CalledProcessError as exc:
                assert b"forbidden" in exc.output or exc.stderr
