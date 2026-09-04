"""Offline tests for the memoized encryption fixture."""

from pathlib import Path
from typing import Any, cast

import tdfs
from fixtures.encryption import EncryptFactory


class RecordingSDK:
    """Small duck-typed SDK that records which plaintexts were encrypted."""

    def __init__(self) -> None:
        self.inputs: list[Path] = []

    def __str__(self) -> str:
        return "fake@main"

    def encrypt(self, pt_file: Path, ct_file: Path, **_: Any) -> None:
        self.inputs.append(pt_file)
        ct_file.write_bytes(pt_file.read_bytes())


def test_cache_distinguishes_plaintexts(tmp_path: Path):
    small = tmp_path / "test-plain-small.txt"
    medium = tmp_path / "test-plain-medium.txt"
    small.write_bytes(b"small")
    medium.write_bytes(b"medium")
    cache: dict[tuple, Path] = {}
    sdk_impl = RecordingSDK()
    sdk = cast(tdfs.SDK, sdk_impl)

    small_ct = EncryptFactory("roundtrip", small, tmp_path, cache)(sdk)
    medium_ct = EncryptFactory("roundtrip", medium, tmp_path, cache)(sdk)

    assert sdk_impl.inputs == [small, medium]
    assert small_ct != medium_ct
    assert "test-plain-small" in small_ct.name
    assert "test-plain-medium" in medium_ct.name
    assert small_ct.read_bytes() == b"small"
    assert medium_ct.read_bytes() == b"medium"


def test_cache_still_shares_identical_plaintext_and_parameters(tmp_path: Path):
    plaintext = tmp_path / "test-plain-small.txt"
    plaintext.write_bytes(b"same input")
    cache: dict[tuple, Path] = {}
    sdk_impl = RecordingSDK()
    sdk = cast(tdfs.SDK, sdk_impl)

    first = EncryptFactory("first-test", plaintext, tmp_path, cache)(sdk)
    second = EncryptFactory("second-test", plaintext, tmp_path, cache)(sdk)

    assert first == second
    assert sdk_impl.inputs == [plaintext]
