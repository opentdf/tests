import os
from pathlib import Path

import pytest

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


# test decryption of legacy tdf created with Java SDK v0_7_5 which is used in the DSP v2.0.2 and DSP v2.0.3 (Gateway)
def test_decrypt_SDKv0_7_5(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("xstext-java-v0.7.5-94b161d53-DSP2.0.2_and_2.0.3.tdf")
    rt_file = tmp_dir / "0.7.5-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 102


# test decryption of legacy tdf created with Java SDK v0_7_8 which is used in the DSP v2.0.4 (Gateway)
def test_decrypt_SDKv0_7_8(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("xstext-java-v0.7.8-7f487c2-DSP2.0.4.tdf")
    rt_file = tmp_dir / "0.7.8-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 92


# test decryption of legacy tdf created with Java SDK v0_9_0 which is used in the DSP v2.0.5.1 and DSP v2.0.6 (Gateway)
def test_decrypt_SDKv0_9_0(
    decrypt_sdk: tdfs.SDK,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
):
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    if not decrypt_sdk.supports("hexless"):
        pytest.skip("Decrypting hexless files is not supported")
    ct_file = get_golden_file("xstext-java-v0.9.0-2de6a49-DSP2.0.5.1_and_2.0.6.tdf")
    rt_file = tmp_dir / "0.9.0-java.untdf"
    decrypt_sdk.decrypt(ct_file, rt_file, container="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 92


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
