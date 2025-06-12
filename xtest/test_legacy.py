import pytest
import os
from pathlib import Path

import tdfs


def get_golden_file(golden_file_name: str) -> Path:
    xtest_dir = Path(__file__).parent
    filename = xtest_dir / "golden" / golden_file_name
    if filename.is_file():
        return filename
    raise FileNotFoundError(f"Golden file '{filename}' not found.")


def test_decrypt_small(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("small-java-4.3.0-e0f8caf.tdf")
    rt_file = tmp_dir / "small-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 5 * 2**10
    expected_bytes = bytes([0] * 1024)
    with rt_file.open("rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes

def test_decrypt_SDKv0_7_5(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("java-v0.7.5-94b161d53-DSP2.0.2_and_2.0.3.tdf")
    rt_file = tmp_dir / "0.7.5-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    # print file_stats.st_size value in the output
    print(f"Print file stats: {file_stats}")
    print(f"Decrypted file size: {file_stats.st_size} bytes")

    assert file_stats.st_size == 5 * 2**10
    expected_bytes = bytes([0] * 1024)
    with rt_file.open("rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


def test_decrypt_big(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("big-java-4.3.0-e0f8caf.tdf")
    rt_file = tmp_dir / "big-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 10 * 2**20
    expected_bytes = bytes([0] * 1024)
    with rt_file.open("rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


def test_decrypt_no_splitid(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("no-splitids-java.tdf")
    rt_file = tmp_dir / "no-splitids-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 5 * 2**10
    expected_bytes = bytes([0] * 1024)
    with rt_file.open("rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


def test_decrypt_object_statement_value_json(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("assertion_verification"):
        pytest.skip("assertion_verification is not supported")
    ct_file = get_golden_file("with-json-object-assertions-java.tdf")
    rt_file = tmp_dir / "with-json-object-assertions-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf", verify_assertions=False)
    with rt_file.open("rb") as f:
        assert f.read().decode("utf-8") == "text"
