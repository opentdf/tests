"""A manifest with no key access objects is malformed (DSPX-1561 Phase 0).

``encryptionInformation.keyAccess: []`` names no KAS, so no reader can obtain
a payload key from it. Every reader must refuse such a manifest when it is
loaded, before any KAS call, integrity check, or assertion check, with its
malformed-TDF error; the message contains ``no key access objects``. No path
may reconstruct a key from zero splits.

The fixture is built here rather than by an SDK, since no writer emits it. It
is internally consistent under an all-zero payload key -- segment, segment
hash, HS256 root signature, and an HS256 payload-key assertion -- and is
checked in Python before any reader sees it, so a passing cell means the
reader refused it, not that the fixture was broken.
"""

import base64
import hashlib
import hmac
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import assertions
import tdfs

ZERO_KEY = bytes(32)
PLAINTEXT = b"A TDF that names no key access server.\n" * 4
IV = hashlib.sha256(b"xtest: empty key access iv").digest()[:12]
TAG_BYTES = 16
POLICY = {
    "uuid": "00000000-0000-4000-8000-000000000000",
    "body": {"dataAttributes": [], "dissem": []},
}


def build_manifest_and_payload() -> tuple[dict[str, Any], bytes]:
    """The manifest and payload segment, all bound under the all-zero key."""
    sealed = AESGCM(ZERO_KEY).encrypt(IV, PLAINTEXT, None)
    segment = IV + sealed
    aggregate = sealed[-TAG_BYTES:]  # one GMAC segment: its hash is its tag
    root = hmac.new(ZERO_KEY, aggregate, hashlib.sha256).digest()
    label = {
        "id": "classification",
        "type": "handling",
        "scope": "tdo",
        "appliesToState": "encrypted",
        "statement": {"format": "string", "schema": "urn:x", "value": "SECRET"},
    }
    manifest = {
        "encryptionInformation": {
            "type": "split",
            "policy": base64.b64encode(json.dumps(POLICY).encode()).decode(),
            "keyAccess": [],
            "method": {"algorithm": "AES-256-GCM", "iv": "", "isStreamable": True},
            "integrityInformation": {
                "rootSignature": {
                    "alg": "HS256",
                    "sig": base64.b64encode(root).decode(),
                },
                "segmentHashAlg": "GMAC",
                "segmentSizeDefault": len(PLAINTEXT),
                "encryptedSegmentSizeDefault": len(segment),
                "segments": [
                    {
                        "hash": base64.b64encode(aggregate).decode(),
                        "segmentSize": len(PLAINTEXT),
                        "encryptedSegmentSize": len(segment),
                    }
                ],
            },
        },
        "payload": {
            "type": "reference",
            "url": "0.payload",
            "protocol": "zip",
            "mimeType": "application/octet-stream",
            "isEncrypted": True,
        },
        "schemaVersion": "4.3.0",
        "assertions": [
            assertions.sign_assertion(
                label, ZERO_KEY, aggregate=aggregate, legacy=False, alg="HS256"
            )
        ],
    }
    return manifest, segment


def write_tdf(path: Path) -> None:
    manifest, segment = build_manifest_and_payload()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for name, data in (
            ("0.payload", segment),
            ("0.manifest.json", json.dumps(manifest).encode()),
        ):
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data)


def check_consistent_under_zero_key(path: Path) -> None:
    """Under the all-zero key the fixture decrypts and every binding verifies."""
    with zipfile.ZipFile(path) as z:
        raw = z.read("0.manifest.json")
        segment = z.read("0.payload")
    manifest = assertions.parse_manifest(raw)  # passes Section 3 parsing
    assert manifest["encryptionInformation"]["keyAccess"] == []
    assert AESGCM(ZERO_KEY).decrypt(segment[:12], segment[12:], None) == PLAINTEXT
    integrity = manifest["encryptionInformation"]["integrityInformation"]
    aggregate = assertions.manifest_aggregate(manifest)
    assert aggregate == segment[-TAG_BYTES:]
    root = hmac.new(ZERO_KEY, aggregate, hashlib.sha256).digest()
    assert base64.b64decode(integrity["rootSignature"]["sig"]) == root
    for a in manifest["assertions"]:
        assertions.verify_assertion_binding(
            a, assertions.VerificationKey("HS256", ZERO_KEY), aggregate, legacy=False
        )


def test_fixture_is_consistent_under_the_zero_key(tmp_path: Path):
    """Offline: the fixture is well formed apart from its empty keyAccess."""
    tdf = tmp_path / "empty-key-access.tdf"
    write_tdf(tdf)
    check_consistent_under_zero_key(tdf)


@pytest.mark.parametrize(
    "verify_assertions", [True, False], ids=["verify", "no-verify"]
)
def test_empty_key_access_is_refused(
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    tmp_dir: Path,
    verify_assertions: bool,
):
    """No key access objects: refused at load, whatever assertion verification says."""
    if not in_focus & {decrypt_sdk}:
        pytest.skip("Not in focus")
    decrypt_sdk.skip_if_unsupported("reject_empty_key_access")
    ct_file = tmp_dir / "empty-key-access.tdf"
    write_tdf(ct_file)
    check_consistent_under_zero_key(ct_file)
    mode = "verify" if verify_assertions else "no-verify"
    rt_file = tmp_dir / f"empty-key-access-{decrypt_sdk}-{mode}.untdf"
    rt_file.unlink(missing_ok=True)
    try:
        decrypt_sdk.decrypt(
            ct_file,
            rt_file,
            "ztdf",
            verify_assertions=verify_assertions,
            expect_error=True,
        )
    except subprocess.CalledProcessError as exc:
        assert b"no key access objects" in exc.output, (
            f"{decrypt_sdk} refused the TDF without 'no key access objects': "
            f"{exc.output[-4000:]!r}"
        )
        # A CLI may create its output file before reading; it must stay empty.
        assert not rt_file.exists() or rt_file.stat().st_size == 0, (
            f"{decrypt_sdk} wrote output for a TDF with no key access objects"
        )
        return
    pytest.fail(f"{decrypt_sdk} decrypted a TDF with no key access objects")
