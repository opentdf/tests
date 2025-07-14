import filecmp
import logging
import subprocess
import pytest
import sys
from pathlib import Path

import tdfs
from abac import Attribute


cipherTexts: dict[str, Path] = {}

# Improved logging configuration
logger = logging.getLogger("xtest")
# Configure logging to ensure we see everything
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,  # Ensure output goes to stdout for pytest capture
)
# Make sure our logger is set to DEBUG level
logger.setLevel(logging.DEBUG)

# Configure subprocess logging if needed
logging.getLogger("subprocess").setLevel(logging.DEBUG)


def skip_rts_as_needed(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if container == "nano-with-ecdsa" and not encrypt_sdk.supports("nano_ecdsa"):
        pytest.skip(
            f"{encrypt_sdk} sdk doesn't yet support ecdsa bindings for nanotdfs"
        )
    if (container == "nano" or container == "nano-with-ecdsa") and encrypt_sdk.supports(
        "nano_attribute_bug"
    ):
        # This is a bug in the nano sdk that was fixed in 0.4.1
        pytest.skip(f"{encrypt_sdk} sdk fails to add attributes to nanotdfs properly")

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


def test_or_attributes_success(
    attribute_with_or_type: Attribute,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    pt_file: Path,
    container: tdfs.container_type,
    in_focus: set[tdfs.SDK],
):
    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container, in_focus)

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
        decrypt_or_dont(
            decrypt_sdk, pt_file, container, expect_success, ct_file, rt_file
        )


def decrypt_or_dont(
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    container: tdfs.container_type,
    expect_success: bool,
    ct_file: Path,
    rt_file: Path,
):
    if expect_success:
        output = decrypt_sdk.decrypt(ct_file, rt_file, container)
        assert filecmp.cmp(pt_file, rt_file)
        # Log successful output for debugging
        if output and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Successful decrypt output: {output.decode(errors='replace')}"
            )
    else:
        try:
            output = decrypt_sdk.decrypt(ct_file, rt_file, container, expect_error=True)
            assert False, "decrypt succeeded unexpectedly"
        except subprocess.CalledProcessError as exc:
            output_content = getattr(exc, "output", b"").decode(errors="replace")
            stderr_content = getattr(exc, "stderr", b"").decode(errors="replace")

            # Make sure we have complete output for debugging
            logger.debug(
                f"Command failed as expected. Return code: {exc.returncode}\n"
                f"Output: {output_content}\n"
                f"Stderr: {stderr_content}"
            )

            # Verify it failed for the expected reason
            if not any(
                e in (exc.output or b"") or e in (exc.stderr or b"")
                for e in [b"forbidden", b"unable to reconstruct split key"]
            ):
                logger.warning(
                    f"Failed to decrypt {ct_file} with {decrypt_sdk} in {container}: {exc}\n"
                    f"Output: {output_content}\n"
                    f"Stderr: {stderr_content}"
                )
                assert False, f"decrypt failed with unexpected error: {exc}"


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
    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container, in_focus)

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
        decrypt_or_dont(
            decrypt_sdk, pt_file, container, expect_success, ct_file, rt_file
        )


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
    skip_rts_as_needed(encrypt_sdk, decrypt_sdk, container, in_focus)

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
        decrypt_or_dont(
            decrypt_sdk, pt_file, container, expect_success, ct_file, rt_file
        )
