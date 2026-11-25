"""DEK maths: combine unwrapped KAO shares and prove the result before it is published.

Offline: the unwrapping itself runs in corpus_gen/dek (see steps.py).
"""

import base64
import glob
import hashlib
import hmac
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

IV_SIZE = 12
TAG_SIZE = 16


class DekError(Exception):
    pass


def xor_shares(shares: Sequence[bytes]) -> bytes:
    if not shares:
        raise ValueError("no shares")
    size = len(shares[0])
    if any(len(s) != size for s in shares):
        raise ValueError("shares differ in length")
    acc = 0
    for s in shares:
        acc ^= int.from_bytes(s)
    return acc.to_bytes(size)


def combine(kao_shares: Sequence[tuple[str, bytes]]) -> tuple[bytes, dict[str, bytes]]:
    """DEK and share per split id from (sid, share) per KAO.

    KAOs with the same sid hold the same share, so each sid counts once.
    """
    by_sid: dict[str, bytes] = {}
    for sid, share in kao_shares:
        if by_sid.setdefault(sid, share) != share:
            raise DekError(f"KAOs with split id {sid!r} unwrap to different shares")
    return xor_shares(list(by_sid.values())), by_sid


_SID = re.compile(r"[A-Za-z0-9._-]+")


def share_files(stem: str, shares: dict[str, bytes], kaos: int) -> dict[str, str]:
    """`<stem>.<sid>.share` for every split id, even on a single KAO.

    A lone KAO without a sid gets none; several KAOs must each have one.
    """
    files: dict[str, str] = {}
    for sid, share in shares.items():
        if not sid:
            if kaos > 1:
                raise DekError(f"{kaos} KAOs but one has no split id")
            continue
        if not _SID.fullmatch(sid) or sid in (".", ".."):
            raise DekError(f"split id {sid!r} cannot name a key file")
        files[f"{stem}.{sid}.share"] = share.hex() + "\n"
    return files


def remove_key_files(keys_dir: Path, stem: str) -> list[str]:
    """Delete keys/<stem>.* (DEK, shares, public keys); returns the names removed."""
    if not keys_dir.is_dir():
        return []
    removed: list[str] = []
    for p in sorted(keys_dir.glob(f"{glob.escape(stem)}.*")):
        p.unlink()
        removed.append(p.name)
    return removed


def _matches(mac: hmac.HMAC, encoded: str) -> bool:
    """A base64 HMAC in raw or hex-then-base64 form."""
    try:
        got = base64.b64decode(encoded, validate=True)
    except ValueError:
        return False
    return hmac.compare_digest(got, mac.digest()) or hmac.compare_digest(
        got, mac.hexdigest().encode()
    )


def check_binding(share: bytes, kao: dict[str, Any], policy: str) -> None:
    """The KAO's policy binding must be HMAC-SHA256(share, policy)."""
    binding = kao.get("policyBinding")
    encoded = binding.get("hash") if isinstance(binding, dict) else binding
    if not isinstance(encoded, str):
        raise DekError("KAO has no policy binding")
    if not _matches(hmac.new(share, policy.encode(), hashlib.sha256), encoded):
        raise DekError("policy binding does not match the unwrapped share")


def segment_sizes(integrity: dict[str, Any]) -> list[tuple[int, int]]:
    plain = integrity.get("segmentSizeDefault")
    enc = integrity.get("encryptedSegmentSizeDefault")
    return [
        (s.get("segmentSize", plain), s.get("encryptedSegmentSize", enc))
        for s in integrity["segments"]
    ]


def verify_dek(
    dek: bytes, manifest: dict[str, Any], payload: bytes, plaintext: bytes
) -> None:
    """Decrypt the first segment and compare it with the plaintext's first bytes.

    A file with no segments (an empty plaintext) is checked by its root
    signature, HMAC-SHA256 of the empty segment-hash aggregate.
    """
    integrity = manifest["encryptionInformation"]["integrityInformation"]
    segments = segment_sizes(integrity)
    if not segments:
        if plaintext:
            raise DekError("manifest has no segments but the plaintext is not empty")
        mac = hmac.new(dek, b"", hashlib.sha256)
        if not _matches(mac, integrity["rootSignature"]["sig"]):
            raise DekError("root signature does not match the DEK")
        return
    size, enc_size = segments[0]
    if enc_size != size + IV_SIZE + TAG_SIZE or len(payload) < enc_size:
        raise DekError(f"first segment sizes {size}/{enc_size} do not fit the payload")
    segment = payload[:enc_size]
    try:
        got = AESGCM(dek).decrypt(segment[:IV_SIZE], segment[IV_SIZE:], None)
    except InvalidTag:
        raise DekError("first segment fails AES-GCM under the DEK") from None
    if got != plaintext[:size]:
        raise DekError("first segment decrypts to bytes other than the plaintext's")
