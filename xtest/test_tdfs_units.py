"""Offline tests for tdfs.py's XT_FORCE_SUPPORTS override and chunky gating (DSPX-4638, DSPX-4589).

No platform, no SDK, no subprocess. ``_parse_forced_supports`` and
``skip_chunky_skew`` are both safeguards built specifically to stop a real
regression from hiding behind a skip -- so they are worth testing on their
own.
"""

import json
import zipfile
from pathlib import Path
from typing import cast

import pytest

import tdfs


class TestParseForcedSupports:
    def test_parses_comma_and_whitespace_separated_names(self):
        assert tdfs._parse_forced_supports(" hexless, dpop ,ecwrap") == frozenset(
            {"hexless", "dpop", "ecwrap"}
        )

    def test_empty_string_yields_empty_set(self):
        assert tdfs._parse_forced_supports("") == frozenset()
        assert tdfs._parse_forced_supports("   ") == frozenset()

    def test_unknown_name_raises(self):
        """The whole point of this function: a typo must not be a silent no-op."""
        with pytest.raises(ValueError, match="unknown feature"):
            tdfs._parse_forced_supports("hexles")


# --- tdfs.elides_segment_sizes / tdfs.skip_chunky_skew ------------------------


def _manifest_zip(tmp_path: Path, name: str, *, elides: bool) -> Path:
    """A minimal container with just enough manifest to exercise elides_segment_sizes."""
    segments = [
        {
            "hash": "aaaa",
            "segmentSize": None if elides else 1000,
            "encryptedSegmentSize": None if elides else 1028,
        },
        {"hash": "bbbb", "segmentSize": 1000, "encryptedSegmentSize": 1028},
    ]
    manifest = {
        "encryptionInformation": {
            "type": "split",
            "policy": "",
            "keyAccess": [
                {
                    "type": "wrapped",
                    "url": "http://kas.example/kas",
                    "protocol": "kas",
                    "wrappedKey": "x",
                    "policyBinding": "y",
                }
            ],
            "method": {"algorithm": "AES-256-GCM"},
            "integrityInformation": {
                "rootSignature": {"sig": "sig"},
                "segmentHashAlg": "GMAC",
                "segments": segments,
            },
        },
        "payload": {
            "type": "reference",
            "url": "0.payload",
            "protocol": "zip",
            "isEncrypted": True,
        },
    }
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("0.manifest.json", json.dumps(manifest))
        z.writestr("0.payload", b"")
    return p


class _StubDecryptSDK:
    """A duck-typed stand-in for the one method skip_chunky_skew calls."""

    def __init__(self, supports_chunky: bool) -> None:
        self._supports_chunky = supports_chunky

    def supports(self, feature: str) -> bool:
        assert feature == "chunky"
        return self._supports_chunky

    def __str__(self) -> str:
        return "stub@main"


class TestElidesSegmentSizes:
    def test_true_when_any_segment_omits_a_size(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "elides.tdf", elides=True)
        assert tdfs.elides_segment_sizes(ct_file)

    def test_false_when_every_segment_is_fully_sized(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "full.tdf", elides=False)
        assert not tdfs.elides_segment_sizes(ct_file)


class TestSkipChunkySkew:
    def test_skips_when_needed_and_unsupported(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "elides.tdf", elides=True)
        decrypt_sdk = cast(tdfs.SDK, _StubDecryptSDK(supports_chunky=False))
        with pytest.raises(pytest.skip.Exception):
            tdfs.skip_chunky_skew(ct_file, decrypt_sdk)

    def test_does_not_skip_when_reader_supports_chunky(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "elides.tdf", elides=True)
        decrypt_sdk = cast(tdfs.SDK, _StubDecryptSDK(supports_chunky=True))
        tdfs.skip_chunky_skew(ct_file, decrypt_sdk)

    def test_does_not_skip_when_container_does_not_elide(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "full.tdf", elides=False)
        decrypt_sdk = cast(tdfs.SDK, _StubDecryptSDK(supports_chunky=False))
        tdfs.skip_chunky_skew(ct_file, decrypt_sdk)
