"""Offline tests for regenerating dropped TDF segments (DSPX-5547).

No platform, no SDK. The synthetic TDF is really encrypted: AES-GCM segments
under a known DEK, split two ways, each share RSA-wrapped for a throwaway
KAS key. The golden one is real java output, with its key in extra-keys.json.
"""

import base64
import hmac
import itertools
import json
import random
import urllib.request
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import rangeserve
import regenerate
from rangeserve import PAYLOAD_GCM_OVERHEAD as GCM
from regenerate import RegeneratingSource, RegenerationError

SEG = 1000
PT_LEN = 4 * SEG + 300  # four whole segments and a short fifth
PT = random.Random(5547).randbytes(PT_LEN)
DEK = random.Random(1).randbytes(32)
#: What the platform's KAS unwraps ``wrapped`` keys with.
OAEP = padding.OAEP(
    mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None
)

Kept = tuple[rangeserve.ExtentStore, regenerate.SegmentTable]


def plaintext(offset: int, length: int) -> bytes:
    return PT[offset : offset + length]


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def keep(
    directory: Path,
    tdf: Path,
    ranges: Sequence[tuple[int, int]],
    chunk: int,
    **layout: int,
) -> Kept:
    """Stream ``tdf`` through a sparse sink and a segment recorder."""
    data = tdf.read_bytes()
    layout["payload_start"] = rangeserve.payload_start(tdf)
    plan = rangeserve.retention_plan(ranges, **layout)
    sink = rangeserve.SparseSink(directory, plan, tail_ceiling=1 << 16)
    recorder = regenerate.SegmentRecorder(directory, **layout)
    for i in range(0, len(data), chunk):
        sink.write(data[i : i + chunk])
        recorder.write(data[i : i + chunk])
    return sink.close(), recorder.close()


@pytest.fixture(scope="module")
def kas_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_tdf(path: Path, kas_key: rsa.RSAPrivateKey) -> None:
    rng = random.Random(4886)
    aead = AESGCM(DEK)
    payload, tags = [], []
    for off in range(0, PT_LEN, SEG):
        iv = rng.randbytes(regenerate.IV_SIZE)
        sealed = aead.encrypt(iv, plaintext(off, SEG), None)
        payload.append(iv + sealed)
        tags.append(sealed[-regenerate.TAG_SIZE :])
    share = rng.randbytes(32)
    kaos = [
        {
            "type": "wrapped",
            "url": "http://localhost:8080/kas",
            "protocol": "kas",
            "wrappedKey": b64(kas_key.public_key().encrypt(s, OAEP)),
            "policyBinding": "",
            "sid": sid,
        }
        for sid, s in [
            ("s1", share),
            ("s2", bytes(a ^ b for a, b in zip(DEK, share, strict=True))),
        ]
    ]
    root = hmac.digest(DEK, b"".join(tags), "sha256")
    manifest = {
        "schemaVersion": "4.3.0",
        "payload": {
            "type": "reference",
            "url": "0.payload",
            "protocol": "zip",
            "isEncrypted": True,
        },
        "encryptionInformation": {
            "type": "split",
            "policy": "",
            "keyAccess": kaos,
            "method": {"algorithm": "AES-256-GCM"},
            "integrityInformation": {
                "rootSignature": {"alg": "HS256", "sig": b64(root)},
                "segmentHashAlg": "GMAC",
                "segmentSizeDefault": SEG,
                "encryptedSegmentSizeDefault": SEG + GCM,
                "segments": [{"hash": b64(t)} for t in tags],
            },
        },
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("0.payload", b"".join(payload))
        z.writestr("0.manifest.json", json.dumps(manifest))


@pytest.fixture
def synthetic(
    tmp_path: Path, kas_key: rsa.RSAPrivateKey
) -> Iterator[tuple[bytes, rangeserve.ExtentStore, regenerate.SegmentTable]]:
    """The TDF, and what streaming it kept: head, segment 1, tail, IVs and tags."""
    tdf = tmp_path / "t.tdf"
    make_tdf(tdf, kas_key)
    # 7-byte writes split IVs and tags across calls.
    store, table = keep(
        tmp_path,
        tdf,
        [(SEG + 1, SEG + 2)],
        7,
        segment_size=SEG,
        plaintext_length=PT_LEN,
    )
    yield tdf.read_bytes(), store, table
    store.close()
    table.close()


def test_every_range_matches_the_original(synthetic, kas_key: rsa.RSAPrivateKey):
    data, store, table = synthetic
    assert store.physical_size < len(data) - 3 * (SEG + GCM)
    pem = kas_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    dek = regenerate.unwrap_dek(regenerate.read_manifest(store), [pem])
    assert dek == DEK
    source = RegeneratingSource(store, table, dek, plaintext)

    edges = {0, len(data)}
    for i in range(5):
        s, e = table.layout.extent(i)
        for x in (s, s + regenerate.IV_SIZE, e - regenerate.TAG_SIZE, e):
            edges |= {x - 1, x, x + 1}
    edges = sorted(x for x in edges if 0 <= x <= len(data))
    for a, b in itertools.combinations(edges, 2):
        assert source.read(a, b) == data[a:b], f"bytes {a}-{b}"
    with rangeserve.serve(source) as (url, _):
        with urllib.request.urlopen(url, timeout=10) as r:
            assert r.read() == data


def test_wrong_dek_or_iv_raises(synthetic):
    _, store, table = synthetic
    with pytest.raises(RegenerationError, match="root signature"):
        RegeneratingSource(store, table, bytes(32), plaintext)

    source = RegeneratingSource(store, table, DEK, plaintext)
    with table.ivs_path.open("r+b") as f:  # segment 3 was dropped
        f.seek(3 * regenerate.IV_SIZE)
        f.write(bytes(regenerate.IV_SIZE))
    s, e = table.layout.extent(3)
    with pytest.raises(RegenerationError, match="tag differs"):
        source.read(s, e)


def test_java_golden(tmp_path: Path):
    """Legacy hex hashes, and the empty sixth segment java writes after 10 MiB."""
    here = Path(__file__).parent
    keys = json.loads((here / "extra-keys.json").read_text())
    pem = next(k["privateKey"] for k in keys if k["kid"] == "golden-r1").encode()
    tdf = here / "golden" / "big-java-4.3.0-e0f8caf.tdf"
    store, table = keep(
        tmp_path, tdf, [], 1 << 16, segment_size=2 << 20, plaintext_length=10 << 20
    )
    dek = regenerate.unwrap_dek(regenerate.read_manifest(store), [pem])
    source = RegeneratingSource(store, table, dek, lambda _, n: bytes(n))
    assert store.physical_size < 4096
    assert source.read(0, source.length) == tdf.read_bytes()
    store.close()
    table.close()
