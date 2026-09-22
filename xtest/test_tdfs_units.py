"""Offline tests for tdfs.py's anti-vacuous-green machinery (DSPX-4592, DSPX-4638).

No platform, no SDK, no subprocess. ``_parse_forced_supports``,
``zip64_reader_is_broken``, and ``skip_chunky_skew`` are all safeguards built
specifically to stop a real regression from hiding behind a skip or a stale
xfail -- so they are worth testing on their own, the same way the ZIP64
parser they sit next to is tested in ``test_zip64_units.py``.

The GMAC root forgery (DSPX-4703) is here for a related reason: an exploit
helper that quietly forges the wrong bytes would make the security tests in
``test_root_signature.py`` pass for the wrong reason.
"""

import base64
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import tdfs

# --- tdfs._parse_forced_supports ---------------------------------------------


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

    def test_platform_only_name_is_rejected_by_the_sdk_override(self):
        """Naming the wrong variable is the same no-op as a typo, so it fails the same.

        XT_FORCE_SUPPORTS=kas_uri_from_kao would otherwise parse, force the
        feature on for every SDK, and leave the platform gate the tests actually
        consult untouched -- a green run that tested nothing.
        """
        with pytest.raises(ValueError, match="XT_FORCE_PLATFORM_SUPPORTS instead"):
            tdfs._parse_forced_supports("kas_uri_from_kao")

    def test_platform_only_name_is_accepted_by_the_platform_override(self):
        assert tdfs._parse_forced_supports(
            "kas_uri_from_kao",
            source="XT_FORCE_PLATFORM_SUPPORTS",
            allowed=tdfs.ALL_FEATURES,
        ) == frozenset({"kas_uri_from_kao"})

    def test_both_sided_features_stay_forceable_from_either_side(self):
        """The exclusion is narrow on purpose; ecwrap needs both sides to cooperate."""
        assert "ecwrap" in tdfs.SDK_FORCEABLE_FEATURES
        assert tdfs._parse_forced_supports("ecwrap") == frozenset({"ecwrap"})
        assert tdfs._parse_forced_supports(
            "ecwrap",
            source="XT_FORCE_PLATFORM_SUPPORTS",
            allowed=tdfs.ALL_FEATURES,
        ) == frozenset({"ecwrap"})

    def test_a_typo_is_reported_as_unknown_not_as_misdirected(self):
        """The two failures have different fixes, so they must not share a message."""
        with pytest.raises(ValueError, match="unknown feature") as excinfo:
            tdfs._parse_forced_supports("kas_uri_from_ka0")
        assert "XT_FORCE_PLATFORM_SUPPORTS instead" not in str(excinfo.value)

    def test_the_sdk_valid_list_does_not_advertise_platform_only_names(self):
        """A rejection that then lists the rejected name as valid is a dead end."""
        with pytest.raises(ValueError, match="unknown feature") as excinfo:
            tdfs._parse_forced_supports("hexles")
        assert "kas_uri_from_kao" not in str(excinfo.value)


# --- Platform forced support ------------------------------------------------


@pytest.mark.parametrize("platform_version", ["0.12.0", "main", ""])
@pytest.mark.parametrize("forced", [False, True])
def test_platform_forced_supports(
    monkeypatch: pytest.MonkeyPatch, platform_version: str, forced: bool
):
    monkeypatch.setenv("PLATFORM_VERSION", platform_version)
    # A source tag alone must not imply feature support.
    monkeypatch.setenv("PLATFORM_TAG", "main")
    monkeypatch.setattr(tdfs, "FORCED_SUPPORTS", tdfs._parse_forced_supports("dpop"))
    monkeypatch.setattr(
        tdfs,
        "FORCED_PLATFORM_SUPPORTS",
        tdfs._parse_forced_supports("dpop_nonce_challenge" if forced else ""),
    )
    monkeypatch.setattr(tdfs, "_fetch_well_known", lambda: None)

    features = tdfs.PlatformFeatureSet()
    assert ("dpop_nonce_challenge" in features.features) is forced
    # An SDK override must not force the corresponding platform feature.
    assert "dpop" not in features.features


def test_platform_forced_supports_do_not_leak(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_VERSION", "main")
    monkeypatch.setattr(
        tdfs,
        "FORCED_PLATFORM_SUPPORTS",
        tdfs._parse_forced_supports("dpop_nonce_challenge"),
    )
    forced = tdfs.PlatformFeatureSet()
    monkeypatch.setattr(tdfs, "FORCED_PLATFORM_SUPPORTS", frozenset())
    unforced = tdfs.PlatformFeatureSet()
    assert "dpop_nonce_challenge" in forced.features
    assert "dpop_nonce_challenge" not in unforced.features


def test_platform_override_does_not_override_sdk(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tdfs, "FORCED_SUPPORTS", frozenset())
    monkeypatch.setattr(
        tdfs,
        "FORCED_PLATFORM_SUPPORTS",
        tdfs._parse_forced_supports("dpop_nonce_challenge"),
    )
    sdk = object.__new__(tdfs.SDK)
    sdk._supports = {"dpop_nonce_challenge": False}
    assert not sdk.supports("dpop_nonce_challenge")


def test_unknown_platform_override_names_source():
    with pytest.raises(ValueError, match="XT_FORCE_PLATFORM_SUPPORTS names unknown"):
        tdfs._parse_forced_supports("dpop_typo", source="XT_FORCE_PLATFORM_SUPPORTS")


# --- Checkout-scoped unreleased platform features ----------------------------


class TestUnreleasedPlatformFeatures:
    @pytest.fixture(autouse=True)
    def isolate_platform(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PLATFORM_DIR", raising=False)
        monkeypatch.setenv("PLATFORM_VERSION", "0.26.0")
        monkeypatch.setattr(tdfs, "FORCED_PLATFORM_SUPPORTS", frozenset())
        monkeypatch.setattr(tdfs, "FORCED_SUPPORTS", frozenset())
        monkeypatch.setattr(tdfs, "_fetch_well_known", lambda: None)
        monkeypatch.setattr(tdfs, "_algs_from_km1_log", set)
        monkeypatch.setattr(tdfs, "_kas_supports_algorithm", lambda _: False)

    @pytest.fixture
    def manifest(self, tmp_path: Path) -> Path:
        manifest = tmp_path / "implementing-platform" / "test" / "xtest-features.yaml"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            "supported-unreleased-platform-features:\n  - kas_uri_from_kao\n"
        )
        return manifest

    @pytest.mark.parametrize("platform_tag", ["pull-4056", "main", "v0.27.0"])
    def test_support_follows_checkout_not_version_or_tag(
        self,
        monkeypatch: pytest.MonkeyPatch,
        manifest: Path,
        tmp_path: Path,
        platform_tag: str,
    ):
        # A PR, its merged main build, and a release all retain the declaration.
        # Another checkout with the same reported version must not inherit it.
        monkeypatch.setenv("PLATFORM_TAG", platform_tag)
        monkeypatch.setenv("PLATFORM_DIR", str(manifest.parent.parent))
        assert "kas_uri_from_kao" in tdfs.PlatformFeatureSet().features

        old_platform = tmp_path / "old-platform"
        old_platform.mkdir()
        monkeypatch.setenv("PLATFORM_DIR", str(old_platform))
        features = tdfs.PlatformFeatureSet().features
        assert "kas_uri_from_kao" not in features
        assert "key_management" in features

    def test_unset_platform_dir_does_not_read_caller_manifest(
        self,
        monkeypatch: pytest.MonkeyPatch,
        manifest: Path,
    ):
        monkeypatch.chdir(manifest.parent.parent)
        assert "kas_uri_from_kao" not in tdfs.PlatformFeatureSet().features

    def test_relative_platform_dir_and_manual_override_are_combined(
        self,
        monkeypatch: pytest.MonkeyPatch,
        manifest: Path,
        tmp_path: Path,
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PLATFORM_DIR", "implementing-platform")
        monkeypatch.setenv("PLATFORM_VERSION", "main")
        monkeypatch.setattr(
            tdfs, "FORCED_PLATFORM_SUPPORTS", frozenset({"dpop_nonce_challenge"})
        )
        features = tdfs.PlatformFeatureSet().features
        assert {"kas_uri_from_kao", "dpop_nonce_challenge"} <= features

        sdk = object.__new__(tdfs.SDK)
        sdk._supports = {"kas_uri_from_kao": False, "dpop_nonce_challenge": False}
        assert not sdk.supports("kas_uri_from_kao")
        assert not sdk.supports("dpop_nonce_challenge")

    def test_empty_list_preserves_version_detection(
        self,
        monkeypatch: pytest.MonkeyPatch,
        manifest: Path,
    ):
        manifest.write_text("supported-unreleased-platform-features: []\n")
        monkeypatch.setenv("PLATFORM_DIR", str(manifest.parent.parent))
        monkeypatch.setenv("PLATFORM_VERSION", "0.9.0")
        features = tdfs.PlatformFeatureSet().features
        assert "kas_uri_from_kao" not in features
        assert "key_management" in features

    @pytest.mark.parametrize(
        "content",
        [
            "",
            "{}",
            "[]",
            "supported-unreleased-platform-features: [",
            "supported-unreleased-platform-features: kas_uri_from_kao",
            "supported-unreleased-platform-features: null",
            "supported-unreleased-platform-features: [false]",
            "supported-unreleased-platform-features: [kas_uri_from_ka0]",
            "supported-platform-features: [kas_uri_from_kao]",
            "supported-unreleased-platform-features: []\nunexpected: true",
        ],
    )
    def test_invalid_declaration_fails_with_source_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        manifest: Path,
        content: str,
    ):
        manifest.write_text(content)
        monkeypatch.setenv("PLATFORM_DIR", str(manifest.parent.parent))
        with pytest.raises(
            ValueError, match="Invalid platform feature declaration"
        ) as exc:
            tdfs.PlatformFeatureSet()
        assert str(manifest) in str(exc.value)


# --- tdfs.zip64_reader_is_broken ----------------------------------------------


def _stub_sdk(sdk: str, semver: tuple[int, int, int] | None) -> tdfs.SDK:
    """A duck-typed stand-in exposing only what zip64_reader_is_broken reads."""
    return cast(tdfs.SDK, SimpleNamespace(sdk=sdk, semver=lambda: semver))


class TestZip64ReaderIsBroken:
    """Which decryptors ``test_zip64.py`` requires a decrypt failure from.

    Only java before #393, and only when it reports a release version. Each
    "False" here is a build the test holds to a successful roundtrip, so a
    predicate that were too generous would turn a real regression into an
    expected failure.
    """

    def test_pre_fix_java_is_broken(self):
        assert tdfs.zip64_reader_is_broken(_stub_sdk("java", (0, 18, 0)))

    def test_the_fix_release_itself_is_not(self):
        """Boundary: the constant names the first release *with* the fix."""
        assert not tdfs.zip64_reader_is_broken(
            _stub_sdk("java", tdfs.JAVA_ZIP64_READER_FIX)
        )

    def test_a_later_java_is_not(self):
        major, minor, patch = tdfs.JAVA_ZIP64_READER_FIX
        assert not tdfs.zip64_reader_is_broken(
            _stub_sdk("java", (major, minor, patch + 1))
        )

    def test_another_sdk_is_never_broken(self):
        """The defect is java's ZipReader; an old go is not a stand-in for it."""
        assert not tdfs.zip64_reader_is_broken(_stub_sdk("go", (0, 1, 0)))

    def test_a_branch_build_is_not(self):
        """A branch build (e.g. 'main') has no semver and is expected to carry the fix.

        If it does not, the cell fails loudly -- which is the correct report
        for a branch that has regressed, and is exactly what happened on the
        first live run against java@main.
        """
        assert not tdfs.zip64_reader_is_broken(_stub_sdk("java", None))


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


# --- tdfs.forge_gmac_root_signature (DSPX-4703) -------------------------------


def _integrity_manifest(
    hashes: list[bytes], *, schema_version: str | None = "4.3.0"
) -> tdfs.Manifest:
    """A manifest carrying the given raw segment hashes, encoded as the wire does.

    ``segment.hash`` and ``rootSignature.sig`` hold the base64 *text*, so the
    fixture encodes once here and the helper under test must decode exactly
    once. Legacy (4.2.2) containers hex-encode before base64.
    """
    legacy = schema_version is None

    def encode(raw: bytes) -> str:
        return base64.b64encode(raw.hex().encode() if legacy else raw).decode()

    return tdfs.Manifest.model_validate(
        {
            "encryptionInformation": {
                "type": "split",
                "policy": "",
                "keyAccess": [],
                "method": {"algorithm": "AES-256-GCM"},
                "integrityInformation": {
                    "rootSignature": {"alg": "HS256", "sig": "aG9uZXN0"},
                    "segmentHashAlg": "GMAC",
                    "segments": [{"hash": encode(h)} for h in hashes],
                },
            },
            "payload": {
                "type": "reference",
                "url": "0.payload",
                "protocol": "zip",
                "isEncrypted": True,
            },
            "schemaVersion": schema_version,
        }
    )


class TestForgeGMACRootSignature:
    def test_sig_is_the_trailing_16_bytes_of_the_aggregate(self):
        """No key involved: the forged root is a slice of the segment hashes."""
        hashes = [bytes([i]) * 16 for i in range(1, 4)]
        m = tdfs.forge_gmac_root_signature(_integrity_manifest(hashes))

        root = m.encryptionInformation.integrityInformation.rootSignature
        assert root.alg == "GMAC"
        # Segment hashes are 16 bytes each, so the trailing 16 bytes of the
        # aggregate are exactly the last segment hash -- the finding in one line.
        assert base64.b64decode(root.sig) == hashes[-1]

    def test_decodes_segment_hashes_exactly_once(self):
        """Guards the double-decode trap in the pydantic models.

        ``segment.hash`` is the base64 text as ``bytes``. Decoding it twice
        would still produce *some* 16 bytes for many inputs, so the check has
        to be against the known aggregate rather than against a length.
        """
        hashes = [b"\x00\x11\x22\x33" * 4, b"\xaa\xbb\xcc\xdd" * 4]
        m = tdfs.forge_gmac_root_signature(_integrity_manifest(hashes))

        assert tdfs.aggregate_hash(m) == b"".join(hashes)
        root = m.encryptionInformation.integrityInformation.rootSignature
        assert base64.b64decode(root.sig) == b"".join(hashes)[-16:]

    def test_legacy_container_hex_encodes_before_base64(self):
        """4.2.2 runs the signature through hex first; the aggregate does not.

        Readers build the aggregate by base64-decoding each hash and appending,
        which for a legacy file yields a run of ASCII hex. Only the resulting
        signature gets the extra hex step.
        """
        hashes = [bytes([i]) * 16 for i in range(1, 4)]
        m = tdfs.forge_gmac_root_signature(
            _integrity_manifest(hashes, schema_version=None)
        )

        aggregate = b"".join(h.hex().encode() for h in hashes)
        assert tdfs.aggregate_hash(m) == aggregate
        root = m.encryptionInformation.integrityInformation.rootSignature
        assert base64.b64decode(root.sig) == aggregate[-16:].hex().encode()

    def test_casing_is_preserved(self):
        m = tdfs.forge_gmac_root_signature(_integrity_manifest([b"\x01" * 16]), "GMac")
        assert m.encryptionInformation.integrityInformation.rootSignature.alg == "GMac"

    def test_too_short_an_aggregate_raises(self):
        """Better a loud error than a silently unforgeable signature."""
        with pytest.raises(ValueError, match="aggregate hash"):
            tdfs.forge_gmac_root_signature(_integrity_manifest([b"\x01" * 4]))


class TestEncryptedSegmentSizes:
    def test_falls_back_to_the_manifest_default(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "elides.tdf", elides=True)
        m = tdfs.manifest(ct_file)
        m.encryptionInformation.integrityInformation.encryptedSegmentSizeDefault = 1028
        assert tdfs.encrypted_segment_sizes(m) == [1028, 1028]

    def test_uses_the_per_segment_override(self, tmp_path: Path):
        ct_file = _manifest_zip(tmp_path, "full.tdf", elides=False)
        assert tdfs.encrypted_segment_sizes(tdfs.manifest(ct_file)) == [1028, 1028]
