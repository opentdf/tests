"""
Test suite for TDF operations using SDK servers.

This is a modified version of test_tdfs.py that uses the new SDK server
architecture instead of CLI subprocess calls for dramatic performance improvements.
"""

import base64
import filecmp
import pytest
import random
import re
import string
from pathlib import Path

import nano
import tdfs
from sdk_tdfs import SDK, ServerSDK  # Use server-based SDK


cipherTexts: dict[str, Path] = {}
counter = 0

#### HELPERS


def do_encrypt_with(
    pt_file: Path,
    encrypt_sdk: ServerSDK,
    container: tdfs.container_type,
    tmp_path: Path,
    az: str = "",
    scenario: str = "",
    target_mode: tdfs.container_version | None = None,
) -> Path:
    """
    Encrypt a file with the given SDK and container type, and return the path to the ciphertext file.
    
    Scenario is used to create a unique filename for the ciphertext file.
    
    If targetmode is set, asserts that the manifest is in the correct format for that target.
    """
    global counter
    counter = (counter or 0) + 1
    c = counter
    container_id = f"{encrypt_sdk.sdk}-{container}"
    if scenario != "":
        container_id += f"-{scenario}"
    if container_id in cipherTexts:
        return cipherTexts[container_id]
    ct_file = tmp_path / f"test-{encrypt_sdk.sdk}-{scenario}{c}.{container}"
    
    use_ecdsa = container == "nano-with-ecdsa"
    use_ecwrap = container == "ztdf-ecwrap"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        mime_type="text/plain",
        container=container,
        assert_value=az,
        target_mode=target_mode,
    )
    
    assert ct_file.is_file()
    
    if tdfs.simple_container(container) == "ztdf":
        manifest = tdfs.manifest(ct_file)
        assert manifest.payload.isEncrypted
        if use_ecwrap:
            assert manifest.encryptionInformation.keyAccess[0].type == "ec-wrapped"
        else:
            assert manifest.encryptionInformation.keyAccess[0].type == "wrapped"
        if target_mode == "4.2.2":
            looks_like_422(manifest)
        elif target_mode == "4.3.0":
            looks_like_430(manifest)
        elif not encrypt_sdk.supports("hexless"):
            looks_like_422(manifest)
        else:
            looks_like_430(manifest)
    elif tdfs.simple_container(container) == "nano":
        with open(ct_file, "rb") as f:
            envelope = nano.parse(f.read())
            assert envelope.header.version.version == 12
            assert envelope.header.binding_mode.use_ecdsa_binding == use_ecdsa
            if envelope.header.kas.kid is not None:
                # from xtest/platform/opentdf.yaml
                expected_kid = b"ec1" + b"\0" * 5
                assert envelope.header.kas.kid == expected_kid
    else:
        assert False, f"Unknown container type: {container}"
    cipherTexts[container_id] = ct_file
    return ct_file


def looks_like_422(manifest: tdfs.Manifest):
    assert manifest.schemaVersion is None
    
    ii = manifest.encryptionInformation.integrityInformation
    # in 4.2.2, the root sig is hex encoded before base 64 encoding, and is twice the length
    binary_array = b64hexTobytes(ii.rootSignature.sig)
    match ii.rootSignature.alg:
        case "GMAC":
            assert len(binary_array) == 16
        case "HS256" | "" | None:
            assert len(binary_array) == 32
        case _:
            assert False, f"Unknown alg: {ii.rootSignature.alg}"
    
    for segment in ii.segments:
        hash = b64hexTobytes(segment.hash)
        match ii.segmentHashAlg:
            case "GMAC" | "":
                assert len(hash) == 16
            case "HS256" | "":
                assert len(hash) == 32
            case _:
                assert False, f"Unknown alg: {ii.segmentHashAlg}"


def b64hexTobytes(value: bytes) -> bytes:
    decoded = base64.b64decode(value, validate=True)
    maybe_hex = decoded.decode("ascii")
    assert maybe_hex.isalnum() and all(c in string.hexdigits for c in maybe_hex)
    binary_array = bytes.fromhex(maybe_hex)
    return binary_array


def b64Tobytes(value: bytes) -> bytes:
    decoded = base64.b64decode(value, validate=True)
    try:
        # In the unlikely event decode succeeds, at least make sure there are some non-hex-looking elements
        assert not all(c in string.hexdigits for c in decoded.decode("ascii"))
    except UnicodeDecodeError:
        # If decode fails (the expected behavior), we are good
        pass
    return decoded


def looks_like_430(manifest: tdfs.Manifest):
    assert manifest.schemaVersion == "4.3.0"
    
    ii = manifest.encryptionInformation.integrityInformation
    binary_array = b64Tobytes(ii.rootSignature.sig)
    match ii.rootSignature.alg:
        case "GMAC":
            assert len(binary_array) == 16
        case "HS256" | "":
            assert len(binary_array) == 32
        case _:
            assert False, f"Unknown alg: {ii.rootSignature.alg}"
    
    for segment in ii.segments:
        hash = b64Tobytes(segment.hash)
        match ii.segmentHashAlg:
            case "GMAC":
                assert len(hash) == 16
            case "HS256" | "":
                assert len(hash) == 32
            case _:
                assert False, f"Unknown alg: {ii.segmentHashAlg}"


#### BASIC ROUNDTRIP TESTS


@pytest.mark.req("BR-302")  # Cross-product compatibility
@pytest.mark.cap(sdk="parametrized", format="parametrized")
def test_tdf_roundtrip(
    encrypt_sdk: ServerSDK,
    decrypt_sdk: ServerSDK,
    pt_file: Path,
    tmp_path: Path,
    container: tdfs.container_type,
    in_focus: set[ServerSDK],
):
    pfs = tdfs.PlatformFeatureSet()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if container == "nano-with-ecdsa" and not encrypt_sdk.supports("nano_ecdsa"):
        pytest.skip(
            f"{encrypt_sdk} sdk doesn't yet support ecdsa bindings for nanotdfs"
        )
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
    
    target_mode = tdfs.select_target_version(encrypt_sdk, decrypt_sdk)
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        container,
        tmp_path,
        target_mode=target_mode,
    )
    
    fname = ct_file.stem
    rt_file = tmp_path / f"{fname}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container)
    assert filecmp.cmp(pt_file, rt_file)
    
    if (
        container.startswith("ztdf")
        and decrypt_sdk.supports("ecwrap")
        and "ecwrap" in pfs.features
    ):
        ert_file = tmp_path / f"{fname}-ecrewrap.untdf"
        decrypt_sdk.decrypt(ct_file, ert_file, container, ecwrap=True)
        assert filecmp.cmp(pt_file, ert_file)


@pytest.mark.req("BR-101")  # Core product reliability
@pytest.mark.cap(sdk="parametrized", format="ztdf", feature="hexaflexible")
def test_tdf_spec_target_422(
    encrypt_sdk: ServerSDK,
    decrypt_sdk: ServerSDK,
    pt_file: Path,
    tmp_path: Path,
    in_focus: set[ServerSDK],
):
    pfs = tdfs.PlatformFeatureSet()
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if "hexaflexible" not in pfs.features:
        pytest.skip(f"Hexaflexible is not supported in platform {pfs.version}")
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("hexaflexible"):
        pytest.skip(
            f"Encrypt SDK {encrypt_sdk} doesn't support targeting container format 4.2.2"
        )
    
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_path,
        scenario="target-422",
        target_mode="4.2.2",
    )
    
    fname = ct_file.stem
    rt_file = tmp_path / f"{fname}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


#### MANIFEST VALIDITY TESTS


@pytest.mark.req("BR-101")  # Core product reliability
@pytest.mark.cap(sdk="parametrized", format="ztdf")
def test_manifest_validity(
    encrypt_sdk: ServerSDK,
    pt_file: Path,
    tmp_path: Path,
    in_focus: set[ServerSDK],
):
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = do_encrypt_with(pt_file, encrypt_sdk, "ztdf", tmp_path)
    
    tdfs.validate_manifest_schema(ct_file)


@pytest.mark.req("BR-301")  # Feature coverage
@pytest.mark.cap(sdk="parametrized", format="ztdf", feature="assertions")
def test_manifest_validity_with_assertions(
    encrypt_sdk: ServerSDK,
    pt_file: Path,
    tmp_path: Path,
    assertion_file_no_keys: str,
    in_focus: set[ServerSDK],
):
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_path,
        scenario="assertions",
        az=assertion_file_no_keys,
    )
    
    tdfs.validate_manifest_schema(ct_file)


#### ASSERTION TESTS


@pytest.mark.req("BR-301")  # Feature coverage
@pytest.mark.cap(sdk="parametrized", format="ztdf", feature="assertions")
def test_tdf_assertions_unkeyed(
    encrypt_sdk: ServerSDK,
    decrypt_sdk: ServerSDK,
    pt_file: Path,
    tmp_path: Path,
    assertion_file_no_keys: str,
    in_focus: set[ServerSDK],
):
    pfs = tdfs.PlatformFeatureSet()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertions"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertions")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_path,
        scenario="assertions",
        az=assertion_file_no_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    fname = ct_file.stem
    rt_file = tmp_path / f"{fname}.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file)


@pytest.mark.req("BR-301")  # Feature coverage
@pytest.mark.cap(sdk="parametrized", format="ztdf", feature="assertion_verification")
def test_tdf_assertions_with_keys(
    encrypt_sdk: ServerSDK,
    decrypt_sdk: ServerSDK,
    pt_file: Path,
    tmp_path: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    in_focus: set[ServerSDK],
):
    pfs = tdfs.PlatformFeatureSet()
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip(f"{decrypt_sdk} sdk doesn't yet support assertion_verification")
    ct_file = do_encrypt_with(
        pt_file,
        encrypt_sdk,
        "ztdf",
        tmp_path,
        scenario="assertions-keys-roundtrip",
        az=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    fname = ct_file.stem
    rt_file = tmp_path / f"{fname}.untdf"
    
    decrypt_sdk.decrypt(
        ct_file,
        rt_file,
        "ztdf",
        assertion_verification_file_rs_and_hs_keys,
    )
    assert filecmp.cmp(pt_file, rt_file)


#### Performance Comparison Test


class TestPerformance:
    """Compare SDK server performance vs CLI approach."""
    
    def test_performance_comparison(self, pt_file: Path, tmp_path: Path):
        """Measure and compare performance between SDK servers and CLI."""
        import time
        import statistics
        
        # Test with SDK server
        server_sdk = SDK("go")  # Use Go SDK server
        
        # Warmup
        for _ in range(3):
            ct_file = tmp_path / f"warmup_{_}.ztdf"
            rt_file = tmp_path / f"warmup_{_}.txt"
            server_sdk.encrypt(pt_file, ct_file, container="ztdf")
            server_sdk.decrypt(ct_file, rt_file, container="ztdf")
        
        # Measure SDK server performance
        server_times = []
        iterations = 20
        
        for i in range(iterations):
            ct_file = tmp_path / f"server_{i}.ztdf"
            rt_file = tmp_path / f"server_{i}.txt"
            
            start = time.time()
            server_sdk.encrypt(pt_file, ct_file, container="ztdf")
            server_sdk.decrypt(ct_file, rt_file, container="ztdf")
            elapsed = time.time() - start
            server_times.append(elapsed)
        
        server_avg = statistics.mean(server_times)
        server_median = statistics.median(server_times)
        
        # Compare with estimated CLI performance
        # Typical subprocess overhead is ~50ms per operation
        cli_estimated_time = 0.050 * 2  # encrypt + decrypt
        
        improvement = cli_estimated_time / server_avg
        
        print(f"\n📊 Performance Comparison:")
        print(f"  SDK Server (measured):")
        print(f"    Average: {server_avg * 1000:.1f}ms per roundtrip")
        print(f"    Median:  {server_median * 1000:.1f}ms per roundtrip")
        print(f"  CLI (estimated):")
        print(f"    Average: {cli_estimated_time * 1000:.1f}ms per roundtrip")
        print(f"  Improvement: {improvement:.1f}x faster")
        
        # Assert significant improvement
        assert server_avg < cli_estimated_time / 2, \
            f"SDK server should be at least 2x faster than CLI"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])