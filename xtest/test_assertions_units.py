"""Offline tests for the assertion binding checks in assertions.py.

No platform, no SDK, no subprocess. ``assert_bound`` re-derives every binding
the SDKs write; if it quietly accepted a bad one, the assertion tests in
``test_tdf_assertions.py`` would pass for the wrong reason. So each case here
signs a manifest independently, the way the SDKs do, and checks that the
helper accepts it and rejects each kind of damage.
"""

import base64
import copy
import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import assertions

HS256_KEY = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
RSA_PUBLIC_PEM = (
    RSA_KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    .decode()
)
KEYS = assertions.AssertionVerificationKeys(
    keys={
        "hs": assertions.AssertionKey(alg="HS256", key=HS256_KEY),
        "rs": assertions.AssertionKey(alg="RS256", key=RSA_PUBLIC_PEM),
    }
)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sign(alg: str, claims: dict[str, str]) -> str:
    header = _b64url(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    if alg == "HS256":
        sig = hmac.new(HS256_KEY.encode(), signing_input, hashlib.sha256).digest()
    else:
        sig = RSA_KEY.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(sig)}"


def _manifest(schema_version: str | None) -> dict[str, Any]:
    """A manifest with two segments and an HS256 and an RS256 assertion."""
    digests = [hashlib.sha256(b"one").digest(), hashlib.sha256(b"two").digest()]
    if schema_version is None:
        # 4.2.2 segment hashes are base64 of the hex text.
        digests = [d.hex().encode() for d in digests]
    manifest: dict[str, Any] = {
        "encryptionInformation": {
            "integrityInformation": {
                "segments": [{"hash": base64.b64encode(d).decode()} for d in digests]
            }
        },
        "assertions": [],
    }
    if schema_version:
        manifest["schemaVersion"] = schema_version
    for id, alg in (("hs", "HS256"), ("rs", "RS256")):
        assertion: dict[str, Any] = {
            "id": id,
            "type": "handling",
            "scope": "tdo",
            "appliesToState": "encrypted",
            "statement": {"format": "json", "schema": "urn:x", "value": '{"a":"b"}'},
        }
        h = assertions.assertion_hash(assertion)
        claims = {
            "assertionHash": h,
            "assertionSig": assertions.assertion_sig(manifest, h),
        }
        assertion["binding"] = {"method": "jws", "signature": _sign(alg, claims)}
        manifest["assertions"].append(assertion)
    return manifest


def _expected(manifest: dict[str, Any]) -> list[assertions.Assertion]:
    return [
        assertions.Assertion.model_validate(
            {k: v for k, v in a.items() if k != "binding"}
        )
        for a in manifest["assertions"]
    ]


@pytest.mark.parametrize("schema_version", ["4.3.0", None])
def test_accepts_a_correct_binding(schema_version: str | None):
    manifest = _manifest(schema_version)
    assertions.assert_bound(manifest, _expected(manifest), KEYS)


def test_legacy_and_current_bind_differently():
    """The schemaVersion switch is load-bearing, not decorative."""
    h = "00" * 32
    current = _manifest("4.3.0")
    legacy = copy.deepcopy(current)
    del legacy["schemaVersion"]
    assert assertions.assertion_sig(current, h) != assertions.assertion_sig(legacy, h)


def _set_statement(m: dict[str, Any]) -> None:
    m["assertions"][0]["statement"]["value"] = "tampered"


def _break_signature(m: dict[str, Any]) -> None:
    binding = m["assertions"][1]["binding"]
    binding["signature"] = binding["signature"][:-4] + "AAAA"


def _leak_key(m: dict[str, Any]) -> None:
    m["assertions"][0]["signingKey"] = {"alg": "HS256", "key": HS256_KEY}


def _drop(m: dict[str, Any]) -> None:
    del m["assertions"][1]


def _drop_binding(m: dict[str, Any]) -> None:
    del m["assertions"][0]["binding"]


def _change_segment(m: dict[str, Any]) -> None:
    segments = m["encryptionInformation"]["integrityInformation"]["segments"]
    segments[0]["hash"] = base64.b64encode(b"\0" * 32).decode()


@pytest.mark.parametrize(
    "damage, message",
    [
        (_set_statement, "altered on write"),
        (_break_signature, "does not verify"),
        (_leak_key, "leaked its signing key"),
        (_drop, "missing from manifest"),
        (_drop_binding, "validation error"),
        (_change_segment, "does not bind this payload"),
    ],
)
def test_rejects_damage(damage: Callable[[dict[str, Any]], None], message: str):
    manifest = _manifest("4.3.0")
    expected = _expected(manifest)
    damage(manifest)
    with pytest.raises((AssertionError, ValueError), match=message):
        assertions.assert_bound(manifest, expected, KEYS)


def test_unkeyed_assertion_must_be_hs256():
    """An assertion with no key of its own is signed with the payload key."""
    manifest = _manifest("4.3.0")
    with pytest.raises(AssertionError, match="must be HS256"):
        assertions.assert_bound(
            manifest,
            _expected(manifest),
            assertions.AssertionVerificationKeys(keys={"hs": KEYS.keys["hs"]}),
        )
