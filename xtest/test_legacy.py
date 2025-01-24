import os

import tdfs


def get_golden_file(golden_file_name: str) -> str:
    xtest_dir = os.path.dirname(os.path.realpath(__file__))
    filename = os.path.join(xtest_dir, "golden", f"{golden_file_name}")
    if os.path.isfile(filename):
        return filename
    raise FileNotFoundError(f"Golden file '{filename}' not found.")


def test_decrypt_small(
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir,
):
    ct_file = get_golden_file("small-java-4.3.0-e0f8caf.tdf")
    rt_file = os.path.join(tmp_dir, "small-java.untdf")
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, fmt="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 5 * 2**10
    expected_bytes = bytes([0] * 1024)
    with open(rt_file, "rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


def test_decrypt_big(
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir,
):
    ct_file = get_golden_file("big-java-4.3.0-e0f8caf.tdf")
    rt_file = os.path.join(tmp_dir, "big-java.untdf")
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, fmt="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 10 * 2**20
    expected_bytes = bytes([0] * 1024)
    with open(rt_file, "rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


def test_decrypt_no_splitid(
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir,
):
    ct_file = get_golden_file("no-splitids-java.tdf")
    rt_file = os.path.join(tmp_dir, "no-splitids-java.untdf")
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, fmt="ztdf")
    file_stats = os.stat(rt_file)
    assert file_stats.st_size == 5 * 2**10
    expected_bytes = bytes([0] * 1024)
    with open(rt_file, "rb") as f:
        while b := f.read(1024):
            assert b == expected_bytes


def test_decrypt_object_statement_value_json(
    decrypt_sdk: tdfs.sdk_type,
    tmp_dir,
):
    ct_file = get_golden_file("with-json-object-assertions-java.tdf")
    rt_file = os.path.join(tmp_dir, "with-json-object-assertions-java.untdf")
    tdfs.decrypt(decrypt_sdk, ct_file, rt_file, fmt="ztdf")
    file_stats = os.stat(rt_file)
    with open(rt_file, "rb") as f:
        assert f.read().decode("utf-8") == "text"
