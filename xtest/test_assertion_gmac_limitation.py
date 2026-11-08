"""A known limitation, demonstrated: GMAC segments do not bind content to a
holder of the payload key (spec Section 10.7; DSPX-1561, deferred).

This is not a rejection test, and no release claims to catch it. With GMAC
segment integrity, the default, a segment's hash is its AES-GCM tag. Anyone
holding the payload key also knows the GHASH key ``H``, so they can change
one ciphertext block and change a later one to cancel it out of GHASH. The
tag survives, and with it the segment hash, the aggregate hash, the root
signature, and every assertion binding, an RS256 one included. The manifest
is byte-for-byte unchanged and the reader accepts the altered plaintext.

The case keeps exposing the limitation until a separately versioned wire
format binds assertions to a collision-resistant digest of the content; then
its expectation changes. HS256 segment integrity, where the segment hash is
an HMAC over the ciphertext, does not have the limitation, so a writer that
chose it is skipped.

Getting the payload key needs the local KAS private key: ``PLATFORM_DIR``
(set by ``otdf-local env``) must hold the ``r1`` key, ``kas-private.pem``,
and the default KAS must wrap with it rather than with a managed key.
"""

import base64
import filecmp
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import assertions
import tdfs
from abac import Attribute

#: Exactly one AES block each, so the change stays in the first block.
ORIGINAL = b"classification=A"
CHANGED = b"classification=B"
#: 128 bytes: eight blocks, the last full, in one segment.
PLAINTEXT = ORIGINAL + b"\n" + b"x" * 111
#: The block that absorbs the change, two blocks after the first.
COMPENSATING_BLOCK = 2

IV_BYTES = 12
TAG_BYTES = 16
BLOCK = 16

# GCM's reduction constant, for GF(2^128) in its reflected bit order.
_R = 0xE1 << 120


def gf128_mul(x: int, y: int) -> int:
    """Multiplication in GCM's GF(2^128) (NIST SP 800-38D, Algorithm 1)."""
    z, v = 0, y
    for i in range(127, -1, -1):
        if (x >> i) & 1:
            z ^= v
        v = (v >> 1) ^ _R if v & 1 else v >> 1
    return z


def ghash_key(dek: bytes) -> int:
    encryptor = Cipher(algorithms.AES(dek), modes.ECB()).encryptor()
    return int.from_bytes(encryptor.update(b"\0" * BLOCK) + encryptor.finalize())


def compensate(ciphertext: bytes, dek: bytes) -> bytes:
    """Turn ORIGINAL into CHANGED in block 0 without changing the GCM tag.

    With no additional data, GHASH is the sum over ciphertext blocks of
    ``C_i * H^(n+2-i)``. Adding ``d`` to block ``i`` and ``d * H^(j-i)`` to a
    later block ``j`` adds the same term twice, which cancels.
    """
    h = ghash_key(dek)
    delta = int.from_bytes(bytes(a ^ b for a, b in zip(ORIGINAL, CHANGED, strict=True)))
    factor = 1 << 127  # the field's one: x^0 is the leftmost bit
    for _ in range(COMPENSATING_BLOCK):
        factor = gf128_mul(factor, h)
    out = bytearray(ciphertext)
    for block, d in ((0, delta), (COMPENSATING_BLOCK, gf128_mul(delta, factor))):
        start = block * BLOCK
        changed = int.from_bytes(out[start : start + BLOCK]) ^ d
        out[start : start + BLOCK] = changed.to_bytes(BLOCK)
    return bytes(out)


def unwrap_payload_key(manifest: dict[str, Any]) -> bytes:
    """The DEK, unwrapped with the local KAS ``r1`` key, or skip."""
    platform_dir = os.getenv("PLATFORM_DIR")
    key_file = Path(platform_dir or "") / "kas-private.pem"
    if not platform_dir or not key_file.is_file():
        pytest.skip("needs PLATFORM_DIR with kas-private.pem (eval $(otdf-local env))")
    private = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    assert isinstance(private, rsa.RSAPrivateKey)
    dek = bytes(32)
    for kao in manifest["encryptionInformation"]["keyAccess"]:
        if kao.get("type") != "wrapped":
            pytest.skip(f"key access object of type {kao.get('type')!r}")
        wrapped = base64.b64decode(kao["wrappedKey"])
        for digest in (hashes.SHA1(), hashes.SHA256()):
            try:
                share = private.decrypt(
                    wrapped,
                    padding.OAEP(padding.MGF1(digest), digest, None),
                )
                break
            except ValueError:
                continue
        else:
            pytest.skip("the payload key is not wrapped with the local r1 key")
        dek = bytes(a ^ b for a, b in zip(dek, share, strict=True))
    return dek


def test_gmac_payload_change_keeps_bindings(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    tmp_dir: Path,
    assertion_file_rs_and_hs_keys: str,
    assertion_verification_file_rs_and_hs_keys: str,
    attribute_default_rsa: Attribute,
):
    """A payload-key holder changes the plaintext; every binding still verifies."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    pfs = tdfs.get_platform_features()
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, pfs)
    if not encrypt_sdk.supports("assertions"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet support assertions")
    decrypt_sdk.skip_if_unsupported("assertion_verification")

    pt_file = tmp_dir / "gmac-limitation.txt"
    pt_file.write_bytes(PLAINTEXT)
    ct_file = tmp_dir / f"gmac-limitation-{encrypt_sdk}-{decrypt_sdk}.tdf"
    encrypt_sdk.encrypt(
        pt_file,
        ct_file,
        mime_type="text/plain",
        attr_values=attribute_default_rsa.value_fqns,
        assert_value=assertion_file_rs_and_hs_keys,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    manifest = tdfs.manifest_json(ct_file)
    integrity = manifest["encryptionInformation"]["integrityInformation"]
    if integrity["segmentHashAlg"].upper() != "GMAC":
        pytest.skip(f"{encrypt_sdk} wrote {integrity['segmentHashAlg']} segment hashes")
    assert len(integrity["segments"]) == 1
    (rs256,) = [a for a in manifest["assertions"] if a["id"] == "assertion2"]
    assert assertions.parse_jws(rs256["binding"]["signature"]).header["alg"] == "RS256"

    dek = unwrap_payload_key(manifest)
    with zipfile.ZipFile(ct_file) as z:
        segment = z.read("0.payload")
    iv, ciphertext, tag = (
        segment[:IV_BYTES],
        segment[IV_BYTES:-TAG_BYTES],
        segment[-TAG_BYTES:],
    )
    assert AESGCM(dek).decrypt(iv, ciphertext + tag, None) == PLAINTEXT
    assert (
        tdfs.decode_integrity_value(
            integrity["segments"][0]["hash"].encode(),
            tdfs.is_legacy_manifest(tdfs.manifest(ct_file)),
        )
        == tag
    ), "the GMAC segment hash is not the segment's tag"

    altered = compensate(ciphertext, dek)
    try:
        changed_plaintext = AESGCM(dek).decrypt(iv, altered + tag, None)
    except InvalidTag:
        raise AssertionError("compensation did not preserve the tag") from None
    assert changed_plaintext.startswith(CHANGED) and changed_plaintext != PLAINTEXT

    altered_file = tdfs.update_payload(
        f"gmac-compensated-{decrypt_sdk}", ct_file, lambda _: iv + altered + tag
    )
    with zipfile.ZipFile(ct_file) as a, zipfile.ZipFile(altered_file) as b:
        assert a.read("0.manifest.json") == b.read("0.manifest.json")

    expected = tmp_dir / f"gmac-limitation-changed-{decrypt_sdk}.txt"
    expected.write_bytes(changed_plaintext)
    rt_file = tmp_dir / f"gmac-limitation-{encrypt_sdk}-{decrypt_sdk}.untdf"
    decrypt_sdk.decrypt(
        altered_file, rt_file, "ztdf", assertion_verification_file_rs_and_hs_keys
    )
    assert filecmp.cmp(expected, rt_file), "reader did not return the changed plaintext"
