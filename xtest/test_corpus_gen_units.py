"""Offline checks for the corpus generator: variants, DEK maths and tamper recipes."""

import base64
import dataclasses
import hashlib
import hmac
import json
import os
import shutil
import sys
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import assertions
import corpus
import zipinspect  # noqa: F401
import zipmutate
from corpus_gen import deks, pki, sidecars, steps, tamper, variants, verdicts, zipcases

# Suffixes of the source corpus's sdk-<sdk>-* names. Hard-coded: the source
# corpus is not available in CI.
SOURCE_GO = {
    "assertion-rs256",
    "assertion-system-hs256",
    "attributes",
    "basic",
    "ec-wrapped",
    "empty",
    "hybrid-p256-mlkem768",
    "hybrid-p384-mlkem1024",
    "hybrid-xwing",
    "legacy-v4.2.2",
    "metadata-mimetype",
    "mlkem1024",
    "mlkem768",
    "multi-segment",
    "split-allof-two-kas",
    "split-anyof-two-kas",
    "split-two-kao",
}
SOURCE_JAVA = SOURCE_GO | {"assertion-rs256-x5c"}
SOURCE_WEB = SOURCE_GO - {
    "hybrid-p256-mlkem768",
    "hybrid-p384-mlkem1024",
    "hybrid-xwing",
}


def test_variant_names_match_source():
    assert set(variants.VARIANTS) == SOURCE_JAVA
    assert set(variants.WRITERS["go"]) == SOURCE_GO


def test_writers_matrix():
    assert {sdk: len(names) for sdk, names in variants.WRITERS.items()} == {
        "go": 17,
        "java": 18,
        "web": 14,
    }
    assert set(variants.WRITERS["java"]) == SOURCE_JAVA
    assert set(variants.WRITERS["web"]) == SOURCE_WEB


def test_tamper_bases():
    assert set(variants.TAMPER_BASES) == {
        "go-basic",
        "go-assertion-hs256",
        "go-assertion-rs256",
        "web-basic",
        "web-multi-segment",
    }
    sizes = {n: b.size for n, b in variants.TAMPER_BASES.items()}
    assert sizes["go-basic"] == 132
    assert sizes["web-basic"] == sizes["web-multi-segment"] == 165
    multi = variants.TAMPER_BASES["web-multi-segment"].job(corpus.kas_keys())
    assert multi.get("segment_size") == 64


def test_plaintext_is_deterministic_and_sized():
    assert variants.plaintext("sdk-go-empty", 0) == b""
    a = variants.plaintext("sdk-go-basic", 1024)
    assert len(a) == 1024
    assert a == variants.plaintext("sdk-go-basic", 1024)
    assert a != variants.plaintext("sdk-java-basic", 1024)
    assert variants.plaintext_size("multi-segment") == 40 * 1024
    assert variants.plaintext_size("empty") == 0


@pytest.mark.parametrize("sdk", sorted(variants.WRITERS))
def test_jobs_fit_writer_limits(sdk: str):
    keys = corpus.kas_keys()
    for name in variants.WRITERS[sdk]:
        job = variants.job_for(sdk, name, keys)
        kas = job.get("kas", [])
        assert bool(kas) != bool(job.get("attributes")), name
        for k in kas:
            assert k["kid"] in keys, name
        split = job.get("split", [])
        if len(kas) == 1:
            assert not split, name
        if sdk == "java":
            assert all("sid" not in s for s in split), name
        if sdk == "web":
            assert all(not k["alg"].startswith("hpqt:") for k in kas), name


def _handling(job: variants.WriteJob) -> variants.AssertionSpec:
    (a,) = [a for a in job.get("assertions", []) if a["kind"] == "handling"]
    return a


def test_handling_assertions_reproduce_source_shape():
    keys = corpus.kas_keys()
    jobs = {
        "assertion-rs256": variants.VARIANTS["assertion-rs256"](keys),
        "assertion-rs256-x5c": variants.VARIANTS["assertion-rs256-x5c"](keys),
        "go-assertion-rs256": variants.TAMPER_BASES["go-assertion-rs256"].job(keys),
    }
    want = {
        "assertion-rs256": ("handling-rs256", '{"caveat":"conformance"}'),
        "assertion-rs256-x5c": ("handling-rs256-x5c", '{"caveat":"x5c"}'),
        "go-assertion-rs256": ("handling-rs256", '{"caveat":"corpus"}'),
    }
    for name, job in jobs.items():
        a = _handling(job)
        assert a.get("alg") == "RS256", name
        assert a.get("scope") == "payload", name
        assert a.get("applies_to_state") == "unencrypted", name
        assert (a.get("id"), a.get("statement")) == (
            want[name][0],
            {
                "format": "json",
                "schema": "urn:example:handling",
                "value": want[name][1],
            },
        ), name
        assert ("x5c" in a) == (name == "assertion-rs256-x5c"), name


def test_share_files():
    a, b = bytes(range(32)), bytes(range(32, 64))
    assert deks.share_files("f", {"s-0": a, "s-1": b}, 2) == {
        "f.s-0.share": a.hex() + "\n",
        "f.s-1.share": b.hex() + "\n",
    }
    # A single KAO gets a share file when it carries a split id, else none.
    assert deks.share_files("f", {"1": a}, 1) == {"f.1.share": a.hex() + "\n"}
    assert deks.share_files("f", {"": a}, 1) == {}
    with pytest.raises(deks.DekError):
        deks.share_files("f", {"": a, "s-1": b}, 2)
    with pytest.raises(deks.DekError):
        deks.share_files("f", {"../x": a}, 1)


def test_xor_shares():
    a = bytes.fromhex("0f" * 16 + "f0" * 16)
    b = bytes.fromhex("ff" * 32)
    assert deks.xor_shares([a, b]) == bytes.fromhex("f0" * 16 + "0f" * 16)
    assert deks.xor_shares([a]) == a
    with pytest.raises(ValueError):
        deks.xor_shares([a, b[:16]])


def test_combine_groups_kaos_by_split_id():
    a, b = bytes(range(32)), bytes(range(32, 64))
    dek, shares = deks.combine([("s-0", a), ("s-1", b)])
    assert dek == deks.xor_shares([a, b])
    assert shares == {"s-0": a, "s-1": b}
    # Two KAOs sharing a split id carry the same share (an ANY_OF split).
    dek, shares = deks.combine([("1", a), ("1", a)])
    assert dek == a and shares == {"1": a}
    with pytest.raises(deks.DekError):
        deks.combine([("1", a), ("1", b)])


def _tdf(dek: bytes, plaintext: bytes, seg: int) -> tuple[dict, bytes]:
    payload, segments = b"", []
    for i in range(0, len(plaintext), seg):
        chunk = plaintext[i : i + seg]
        iv = hashlib.sha256(chunk).digest()[:12]
        payload += iv + AESGCM(dek).encrypt(iv, chunk, None)
        segments.append(
            {"segmentSize": len(chunk), "encryptedSegmentSize": len(chunk) + 28}
        )
    # Omitted sizes fall back to the defaults, as the Web SDK writes them.
    segments[0] = {}
    manifest = {
        "encryptionInformation": {
            "integrityInformation": {
                "segmentSizeDefault": seg,
                "encryptedSegmentSizeDefault": seg + 28,
                "segments": segments,
            }
        }
    }
    return manifest, payload


def test_verify_dek_decrypts_first_segment():
    dek = bytes(range(32))
    plaintext = b"corpus segment one" * 4
    manifest, payload = _tdf(dek, plaintext, 32)
    deks.verify_dek(dek, manifest, payload, plaintext)
    with pytest.raises(deks.DekError):
        deks.verify_dek(bytes(32), manifest, payload, plaintext)
    with pytest.raises(deks.DekError):
        deks.verify_dek(dek, manifest, payload, b"X" + plaintext[1:])


def test_verify_dek_without_segments_checks_root_signature():
    dek = bytes(range(32))
    mac = hmac.new(dek, b"", hashlib.sha256).digest()
    manifest = {
        "encryptionInformation": {
            "integrityInformation": {
                "segments": [],
                "rootSignature": {
                    "alg": "HS256",
                    "sig": base64.b64encode(mac).decode(),
                },
            }
        }
    }
    deks.verify_dek(dek, manifest, b"", b"")
    with pytest.raises(deks.DekError):
        deks.verify_dek(bytes(32), manifest, b"", b"")


@pytest.mark.parametrize("form", ["hex-base64", "base64"])
def test_check_binding(form: str):
    share = bytes(range(32))
    policy = base64.b64encode(json.dumps({"uuid": "x"}).encode()).decode()
    mac = hmac.new(share, policy.encode(), hashlib.sha256)
    raw = mac.hexdigest().encode() if form == "hex-base64" else mac.digest()
    kao = {"policyBinding": {"alg": "HS256", "hash": base64.b64encode(raw).decode()}}
    deks.check_binding(share, kao, policy)
    with pytest.raises(deks.DekError):
        deks.check_binding(bytes(32), kao, policy)


def test_rewrite_clears_stale_key_files(tmp_path: Path):
    by_name = {p.name: p for p in steps.plan(corpus.kas_keys(), tmp_path)}
    p = by_name["sdk-java-split-two-kao.tdf"]
    keys = tmp_path / "stage" / "keys"
    keys.mkdir(parents=True)
    stale = [
        "sdk-java-split-two-kao.dek",
        "sdk-java-split-two-kao.0b1d.share",
        "sdk-java-split-two-kao.9f3e.share",
    ]
    kept = [
        "sdk-java-split-anyof-two-kas.dek",
        "sdk-java-split-anyof-two-kas.1c2d.share",
        "sdk-go-split-two-kao.s-0.share",
        "sdk-java-assertion-rs256.pub.pem",
    ]
    for n in stale + kept:
        (keys / n).write_text("00\n")
    p.out.write_bytes(b"old fixture")

    steps.prepare(p, tmp_path)

    assert sorted(f.name for f in keys.iterdir()) == sorted(kept)
    assert not p.out.exists()
    plaintext = Path(p.job.get("plaintext", ""))
    assert plaintext.read_bytes() == variants.plaintext(p.key_stem, p.size)
    # A stem never matches a longer stem that extends it.
    (keys / "sdk-java-assertion-rs256-x5c.leaf.pub.pem").write_text("00\n")
    assert deks.remove_key_files(keys, "sdk-java-assertion-rs256") == [
        "sdk-java-assertion-rs256.pub.pem"
    ]
    assert deks.remove_key_files(tmp_path / "absent", "x") == []


# The source corpus's tamper-* names. Hard-coded: the source corpus is not
# available in CI.
SOURCE_TAMPER = {
    "tamper-assertion-binding-dropped",
    "tamper-assertion-hs256-statement",
    "tamper-assertion-rs256-statement",
    "tamper-assertion-rs256-statement-keyed",
    "tamper-assertion-x5c-forged",
    "tamper-binding-hex-bitflip",
    "tamper-binding-hexless-bitflip",
    "tamper-binding-hexless-control",
    "tamper-ciphertext-body",
    "tamper-deflate",
    "tamper-duplicate-kao",
    "tamper-encrypted-segment-size",
    "tamper-gmac-root-lower",
    "tamper-gmac-root-mixed",
    "tamper-gmac-root-upper",
    "tamper-identity-go-assertion-hs256",
    "tamper-identity-go-assertion-rs256",
    "tamper-identity-go-basic",
    "tamper-identity-web-multi-segment",
    "tamper-kas-url-malicious",
    "tamper-multi-segment-duplicate",
    "tamper-multi-segment-reverse",
    "tamper-multi-segment-truncate",
    "tamper-payload-in-place",
    "tamper-payload-tag",
    "tamper-policy-body",
    "tamper-root-signature",
    "tamper-root-signature-keyless",
    "tamper-segment-hash",
}


def test_recipe_names_match_source():
    assert len(SOURCE_TAMPER) == 29
    assert set(tamper.RECIPES) == SOURCE_TAMPER
    bases = {r.base for r in tamper.RECIPES.values()}
    assert bases <= set(variants.TAMPER_BASES) | {"sdk-java-assertion-rs256-x5c"}


def test_rezip_stored_roundtrip(tmp_path: Path):
    payload = bytes(range(256)) * 3
    src = tmp_path / "src.zip"
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("0.payload", payload)
        z.writestr("0.manifest.json", b'{"a":1}')
    dest = tmp_path / "out.zip"
    tamper.rezip_stored(src, dest, {"0.manifest.json": b'{"a":2}'})
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert [i.filename for i in z.infolist()] == ["0.payload", "0.manifest.json"]
        assert {i.compress_type for i in z.infolist()} == {zipfile.ZIP_STORED}
        assert z.read("0.payload") == payload
        assert z.read("0.manifest.json") == b'{"a":2}'
    with pytest.raises(tamper.TamperError):
        tamper.rezip_stored(src, dest, {"1.payload": b""})


def test_edit_manifest_text_requires_single_match():
    text = '{"a":"x","b":"y"}'
    assert tamper.edit_manifest_text(text, '"x"', '"z"') == '{"a":"z","b":"y"}'
    with pytest.raises(tamper.TamperError):
        tamper.edit_manifest_text(text, '"q"', '"z"')
    with pytest.raises(tamper.TamperError):
        tamper.edit_manifest_text('{"a":"x","b":"x"}', '"x"', '"z"')
    # Overlapping occurrences count too.
    with pytest.raises(tamper.TamperError):
        tamper.edit_manifest_text("aaa", "aa", "b")


# Synthetic bases: the shapes the generator's bases have, with a known DEK.
_DEK = bytes(range(32))


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _compact(v: object) -> str:
    return json.dumps(v, separators=(",", ":"))


Signer = Callable[[bytes], bytes]


def _jws(header: dict[str, Any], claims: dict[str, Any], sign: Signer) -> str:
    head, body = (_b64url(_compact(p).encode()) for p in (header, claims))
    return f"{head}.{body}.{_b64url(sign(f'{head}.{body}'.encode()))}"


def _rsa_signer(key_pem: str) -> Signer:
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    return lambda data: key.sign(data, padding.PKCS1v15(), hashes.SHA256())


def _der_b64(pem: str) -> str:
    cert = x509.load_pem_x509_certificate(pem.encode())
    return _b64(cert.public_bytes(serialization.Encoding.DER))


def _bound(
    assertion: dict[str, Any],
    manifest: dict[str, Any],
    header: dict[str, Any],
    sign: Signer,
) -> dict[str, Any]:
    h = assertions.assertion_hash(assertion)
    claims = {"assertionHash": h, "assertionSig": assertions.assertion_sig(manifest, h)}
    assertion["binding"] = {"method": "jws", "signature": _jws(header, claims, sign)}
    return assertion


def _handling_assertion(caveat: str, id: str) -> dict[str, Any]:
    return {
        "id": id,
        "type": "handling",
        "scope": "payload",
        "appliesToState": "unencrypted",
        "statement": {
            "format": "json",
            "schema": "urn:example:handling",
            "value": _compact({"caveat": caveat}),
        },
    }


def _write_base(
    path: Path,
    size: int = 132,
    segment: int = 2097152,
    web: bool = False,
    assertion: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> Path:
    plaintext = variants.plaintext(path.stem, size)
    payload, segments = b"", []
    for i in range(0, size, segment):
        chunk = plaintext[i : i + segment]
        iv = hashlib.sha256(chunk).digest()[:12]
        ct = AESGCM(_DEK).encrypt(iv, chunk, None)
        payload += iv + ct
        seg: dict[str, Any] = {"hash": _b64(ct[-16:])}
        if not web or len(chunk) != segment:
            seg |= {"segmentSize": len(chunk), "encryptedSegmentSize": len(chunk) + 28}
        segments.append(seg)
    aggregate = b"".join(base64.b64decode(s["hash"]) for s in segments)
    body = {"dataAttributes": None, "dissem": None}
    uuid = "8a68b078-0000-4000-8000-000000000000"
    policy = _b64(_compact({"uuid": uuid, "body": body}).encode())
    binding = hmac.new(_DEK, policy.encode(), hashlib.sha256).hexdigest()
    root = hmac.new(_DEK, aggregate, hashlib.sha256).digest()
    manifest: dict[str, Any] = {
        "encryptionInformation": {
            "type": "split",
            "policy": policy,
            "keyAccess": [
                {
                    "type": "wrapped",
                    "url": "http://localhost:8585",
                    "protocol": "kas",
                    "wrappedKey": _b64(b"w" * 256),
                    "policyBinding": {"alg": "HS256", "hash": _b64(binding.encode())},
                    "kid": "corpus-r2048",
                    "schemaVersion": "1.0",
                }
            ],
            "method": {"algorithm": "AES-256-GCM", "iv": "", "isStreamable": True},
            "integrityInformation": {
                "rootSignature": {"alg": "HS256", "sig": _b64(root)},
                "segmentHashAlg": "GMAC",
                "segmentSizeDefault": segment,
                "encryptedSegmentSizeDefault": segment + 28,
                "segments": segments,
            },
        },
        "payload": {
            "type": "reference",
            "url": "0.payload",
            "protocol": "zip",
            "mimeType": "application/octet-stream",
            "isEncrypted": True,
        },
    }
    if assertion:
        # Bound as a 4.3.0 manifest, with the key order the Go SDK writes.
        manifest["assertions"] = [assertion({**manifest, "schemaVersion": "4.3.0"})]
    manifest["schemaVersion"] = "4.3.0"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("0.payload", payload)
        z.writestr("0.manifest.json", _compact(manifest))
    return path


@pytest.fixture(scope="module")
def tamper_bases(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("tamper-bases")
    chain = pki.x5c_chain(d / "pki")
    signer = pki.signer_key(d / "pki", "rs256")

    def system_metadata(m: dict[str, Any]) -> dict[str, Any]:
        # Not "darwin": recipes must read the OS from the base.
        value = {"tdf_spec_version": "4.3.0", "operating_system": "linux"}
        a = {
            "id": "system-metadata",
            "type": "other",
            "scope": "payload",
            "appliesToState": "unencrypted",
            "statement": {
                "format": "json",
                "schema": "system-metadata-v1",
                "value": _compact(value),
            },
        }
        hs = {"alg": "HS256", "typ": "JWT"}
        return _bound(a, m, hs, lambda b: hmac.new(_DEK, b, hashlib.sha256).digest())

    def rs256(m: dict[str, Any]) -> dict[str, Any]:
        a = _handling_assertion("corpus", "handling-rs256")
        return _bound(a, m, {"alg": "RS256", "typ": "JWT"}, _rsa_signer(signer))

    def x5c(m: dict[str, Any]) -> dict[str, Any]:
        x5c = [_der_b64(chain.leaf), _der_b64(chain.intermediate)]
        a = _handling_assertion("x5c", "handling-rs256-x5c")
        header = {"x5c": x5c, "alg": "RS256"}
        return _bound(a, m, header, _rsa_signer(chain.leaf_key))

    return {
        "go-basic": _write_base(d / "go-basic.tdf"),
        "go-assertion-hs256": _write_base(d / "hs256.tdf", assertion=system_metadata),
        "go-assertion-rs256": _write_base(d / "rs256.tdf", assertion=rs256),
        "web-basic": _write_base(d / "web-basic.tdf", size=165, web=True),
        "web-multi-segment": _write_base(d / "web-ms.tdf", 165, 64, web=True),
        "sdk-java-assertion-rs256-x5c": _write_base(d / "x5c.tdf", assertion=x5c),
    }


Derive = Callable[[str], tuple[Path, Path]]


@pytest.fixture
def derive(
    tamper_bases: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Derive:
    """Apply a recipe to its synthetic base, returning (base, output)."""
    monkeypatch.setenv("XT_TMP_DIR", str(tmp_path / "scratch"))

    def run(name: str) -> tuple[Path, Path]:
        r = tamper.RECIPES[name]
        out = tmp_path / f"{name}.tdf"
        r.apply(tamper_bases[r.base], out, {})
        return tamper_bases[r.base], out

    return run


def _read(tdf: Path, entry: str) -> bytes:
    with zipfile.ZipFile(tdf) as z:
        return z.read(entry)


def _manifest(tdf: Path) -> dict[str, Any]:
    return json.loads(_read(tdf, "0.manifest.json"))


def _leaves(v: object, path: str = "") -> Iterator[tuple[str, object]]:
    if isinstance(v, dict) and v:
        for k, x in v.items():
            yield from _leaves(x, f"{path}.{k}" if path else k)
    elif isinstance(v, list) and v:
        for i, x in enumerate(v):
            yield from _leaves(x, f"{path}[{i}]")
    else:
        yield path, v


def _under(path: str, touch: str) -> bool:
    return path == touch or path.startswith((f"{touch}.", f"{touch}["))


MANIFEST_RECIPES = sorted(n for n, r in tamper.RECIPES.items() if r.touches)


@pytest.mark.parametrize("name", MANIFEST_RECIPES)
def test_recipe_changes_only_intended_field(name: str, derive: Derive):
    base, out = derive(name)
    before, after = dict(_leaves(_manifest(base))), dict(_leaves(_manifest(out)))
    gone = object()
    changed = {
        p
        for p in before.keys() | after.keys()
        if before.get(p, gone) != after.get(p, gone)
    }
    touches = tamper.RECIPES[name].touches
    assert {p for p in changed if not any(_under(p, t) for t in touches)} == set()
    assert {t for t in touches if not any(_under(p, t) for p in changed)} == set()


@pytest.mark.parametrize("name", sorted(tamper.RECIPES))
def test_derived_output_passes_check(name: str, derive: Derive):
    base, out = derive(name)
    tamper.check_derived(tamper.RECIPES[name], base, out)


def test_check_derived_rejects_undeclared_changes(derive: Derive):
    base, url = derive("tamper-kas-url-malicious")
    with pytest.raises(tamper.TamperError, match="keyAccess"):
        tamper.check_derived(tamper.RECIPES["tamper-root-signature"], base, url)
    _, same = derive("tamper-identity-go-basic")
    with pytest.raises(tamper.TamperError):
        tamper.check_derived(tamper.RECIPES["tamper-payload-tag"], base, same)
    with pytest.raises(tamper.TamperError):
        tamper.check_derived(tamper.RECIPES["tamper-deflate"], base, same)
    with pytest.raises(tamper.TamperError):
        tamper.check_derived(tamper.RECIPES["tamper-payload-in-place"], base, same)


def test_identity_rezips_unchanged(derive: Derive):
    for name in sorted(n for n in tamper.RECIPES if n.startswith("tamper-identity-")):
        base, out = derive(name)
        for entry in ("0.manifest.json", "0.payload"):
            assert _read(out, entry) == _read(base, entry), name


def _binding_hash(tdf: Path) -> bytes:
    kao = _manifest(tdf)["encryptionInformation"]["keyAccess"][0]
    return base64.b64decode(kao["policyBinding"]["hash"])


def _bits(a: bytes, b: bytes) -> int:
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b, strict=True))


def test_binding_recipes(derive: Derive):
    base, hexed = derive("tamper-binding-hex-bitflip")
    policy = _manifest(base)["encryptionInformation"]["policy"]
    mac = hmac.new(_DEK, policy.encode(), hashlib.sha256).digest()
    # Still lowercase hex, one bit of the HMAC flipped.
    flipped = _binding_hash(hexed).decode()
    assert flipped == flipped.lower()
    assert _bits(bytes.fromhex(flipped), mac) == 1
    _, control = derive("tamper-binding-hexless-control")
    assert _binding_hash(control) == mac
    _, hexless = derive("tamper-binding-hexless-bitflip")
    assert _bits(_binding_hash(hexless), mac) == 1


def _integrity(tdf: Path) -> dict[str, Any]:
    return _manifest(tdf)["encryptionInformation"]["integrityInformation"]


def test_root_and_segment_hash_recipes(derive: Derive):
    base, out = derive("tamper-root-signature")
    _, keyless = derive("tamper-root-signature-keyless")
    assert out.read_bytes() == keyless.read_bytes()
    sig = base64.b64decode(_integrity(base)["rootSignature"]["sig"])
    inverted = sig[:-3] + bytes(b ^ 0xFF for b in sig[-3:])
    assert base64.b64decode(_integrity(out)["rootSignature"]["sig"]) == inverted
    _, seg = derive("tamper-segment-hash")
    before = base64.b64decode(_integrity(base)["segments"][0]["hash"])
    after = base64.b64decode(_integrity(seg)["segments"][0]["hash"])
    assert _bits(after, before) == 1


@pytest.mark.parametrize(
    "casing,alg", [("lower", "gmac"), ("mixed", "GMac"), ("upper", "GMAC")]
)
def test_gmac_root_recipes(casing: str, alg: str, derive: Derive):
    base, out = derive(f"tamper-gmac-root-{casing}")
    segments = _integrity(base)["segments"]
    aggregate = b"".join(base64.b64decode(s["hash"]) for s in segments)
    root = _integrity(out)["rootSignature"]
    assert root == {"alg": alg, "sig": _b64(aggregate[-16:])}


def _policy(tdf: Path) -> dict[str, Any]:
    return json.loads(
        base64.b64decode(_manifest(tdf)["encryptionInformation"]["policy"])
    )


def test_policy_and_kao_recipes(derive: Derive):
    base, out = derive("tamper-policy-body")
    before = _policy(base)
    dissem = {**before["body"], "dissem": ["mallory@example.com"]}
    assert _policy(out) == {**before, "body": dissem}
    kao = _manifest(base)["encryptionInformation"]["keyAccess"][0]
    _, dup = derive("tamper-duplicate-kao")
    assert _manifest(dup)["encryptionInformation"]["keyAccess"] == [kao, kao]
    _, url = derive("tamper-kas-url-malicious")
    got = _manifest(url)["encryptionInformation"]["keyAccess"][0]
    assert got == {**kao, "url": "https://kas.attacker.example/kas"}
    _, size = derive("tamper-encrypted-segment-size")
    assert _integrity(size)["segments"][0]["encryptedSegmentSize"] == 159


def _statement(tdf: Path) -> dict[str, Any]:
    (a,) = _manifest(tdf)["assertions"]
    return json.loads(a["statement"]["value"])


def test_statement_recipes(derive: Derive):
    base, out = derive("tamper-assertion-hs256-statement")
    assert _statement(out) == {**_statement(base), "operating_system": "plan9"}
    _, rs = derive("tamper-assertion-rs256-statement")
    _, keyed = derive("tamper-assertion-rs256-statement-keyed")
    assert rs.read_bytes() == keyed.read_bytes()
    assert _statement(rs) == {"caveat": "none"}
    _, dropped = derive("tamper-assertion-binding-dropped")
    (a,) = _manifest(dropped)["assertions"]
    assert "binding" not in a


def test_payload_recipes(derive: Derive):
    base, body = derive("tamper-ciphertext-body")
    before, after = _read(base, "0.payload"), _read(body, "0.payload")
    assert [i for i in range(len(before)) if before[i] != after[i]] == [17]
    assert _bits(before, after) == 1
    _, tag = derive("tamper-payload-tag")
    assert _read(tag, "0.payload") == before[:-3] + bytes(b ^ 0xFF for b in before[-3:])
    _, deflated = derive("tamper-deflate")
    with zipfile.ZipFile(deflated) as z:
        assert {i.compress_type for i in z.infolist()} == {zipfile.ZIP_DEFLATED}
        assert z.read("0.payload") == before
    # Flipped inside the base's own archive, so the CRC is stale.
    _, in_place = derive("tamper-payload-in-place")
    raw, flipped = base.read_bytes(), in_place.read_bytes()
    (at,) = [i for i in range(len(raw)) if raw[i] != flipped[i]]
    assert flipped[at] == raw[at] ^ 1
    assert raw[at - 17 : at - 17 + len(before)] == before
    with zipfile.ZipFile(in_place) as z:
        assert z.testzip() == "0.payload"


def _chunks(tdf: Path) -> list[bytes]:
    payload, out = _read(tdf, "0.payload"), []
    for _, size in deks.segment_sizes(_integrity(tdf)):
        out.append(payload[:size])
        payload = payload[size:]
    assert payload == b""
    return out


def test_multi_segment_recipes(derive: Derive):
    base, rev = derive("tamper-multi-segment-reverse")
    segments = _integrity(base)["segments"]
    assert len(segments) == 3
    assert _integrity(rev)["segments"] == segments[::-1]
    assert _chunks(rev) == _chunks(base)[::-1]
    _, dup = derive("tamper-multi-segment-duplicate")
    assert _integrity(dup)["segments"] == segments[:1] + segments
    assert _chunks(dup) == _chunks(base)[:1] + _chunks(base)
    _, trunc = derive("tamper-multi-segment-truncate")
    assert _integrity(trunc)["segments"] == segments[:-1]
    assert _read(trunc, "0.payload") == _read(base, "0.payload")


def test_x5c_forged(derive: Derive):
    base, out = derive("tamper-assertion-x5c-forged")
    assert _statement(out) == {"caveat": "forged"}
    m = _manifest(out)
    (a,) = m["assertions"]
    jws = assertions.parse_jws(a["binding"]["signature"])
    h = assertions.assertion_hash(a)
    assert jws.claims == {
        "assertionHash": h,
        "assertionSig": assertions.assertion_sig(m, h),
    }
    (der,) = jws.header["x5c"]
    forged = x509.load_der_x509_certificate(base64.b64decode(der))
    (genuine,) = _manifest(base)["assertions"]
    header = assertions.parse_jws(genuine["binding"]["signature"]).header
    leaf = x509.load_der_x509_certificate(base64.b64decode(header["x5c"][0]))
    # The real leaf's subject on a self-signed certificate with its own key.
    assert forged.subject == leaf.subject == forged.issuer
    assert forged.public_key() != leaf.public_key()
    forged.verify_directly_issued_by(forged)
    pem = forged.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key = assertions.AssertionKey(alg="RS256", key=pem.decode())
    assertions.verify_jws_signature(jws, key)


# The source corpus's zip-* names, each with the trailer fields it changes.
# Hard-coded for the same reason.
SOURCE_ZIP: dict[str, set[str]] = {
    "zip-adversarial-directory-offset-past-eof": {
        "cd_offset_override",
        "force_zip64_eocd",
    },
    "zip-adversarial-entry-count-overstated": {"entry_count_override"},
    "zip-adversarial-extra-length-overrun": {
        "entries[1].extra_override",
        "entries[1].force_zip64_offset",
        "entries[1].version_needed_to_extract",
    },
    "zip-adversarial-header-offset-int64": {
        "entries[1].local_header_offset",
        "entries[1].force_zip64_offset",
        "entries[1].version_needed_to_extract",
    },
    "zip-adversarial-impossible-entry-count": {
        "entry_count_override",
        "force_zip64_eocd",
    },
    "zip-adversarial-manifest-size-past-eof": {
        "entries[1].compressed_size",
        "entries[1].force_zip64_compressed_size",
        "entries[1].version_needed_to_extract",
    },
    "zip-adversarial-payload-overlaps-directory": {
        "entries[0].compressed_size",
        "entries[0].uncompressed_size",
    },
    "zip-legal-comment-with-fake-cd-record": {"comment"},
    "zip-legal-entry-comment": {"entries[0].comment"},
    "zip-legal-trailer-rebuilt": set(),
    "zip-legal-zip64-entry-sentinels": set(),  # checked on its own below
    "zip-legal-zip64-eocd-count-sentinel": {"force_zip64_eocd", "zip64_eocd_fields"},
    "zip-legal-zip64-extra-not-first": {
        "entries[1].force_zip64_offset",
        "entries[1].extra_prefix",
        "entries[1].version_needed_to_extract",
    },
}
LEGAL = sorted(n for n in SOURCE_ZIP if n.startswith("zip-legal-"))
ADVERSARIAL = sorted(n for n in SOURCE_ZIP if n.startswith("zip-adversarial-"))


def test_zip_case_names_match_source():
    assert len(SOURCE_ZIP) == 13
    assert set(zipcases.ZIP_CASES) == set(SOURCE_ZIP)
    assert len(LEGAL) == 6 and len(ADVERSARIAL) == 7


def _trailer_diff(a: zipmutate.MutableTrailer, b: zipmutate.MutableTrailer) -> set[str]:
    """Trailer and entry fields that differ, entries as ``entries[i].field``."""
    out = {
        f.name
        for f in dataclasses.fields(a)
        if f.name != "entries" and getattr(a, f.name) != getattr(b, f.name)
    }
    assert len(a.entries) == len(b.entries)
    for i, (x, y) in enumerate(zip(a.entries, b.entries, strict=True)):
        out |= {
            f"entries[{i}].{f.name}"
            for f in dataclasses.fields(x)
            if getattr(x, f.name) != getattr(y, f.name)
        }
    return out


@pytest.fixture
def zip_base(tamper_bases: dict[str, Path]) -> Path:
    return tamper_bases["web-basic"]


def _build(name: str, base: Path, tmp_path: Path) -> Path:
    out = tmp_path / f"{name}.tdf"
    zipcases.ZIP_CASES[name](base, out)
    return out


@pytest.mark.parametrize("name", LEGAL)
def test_legal_cases_stay_readable(name: str, zip_base: Path, tmp_path: Path):
    out = _build(name, zip_base, tmp_path)
    zipcases.check_derived(name, zip_base, out)
    if name == "zip-legal-comment-with-fake-cd-record":
        return  # spec-legal, but expected invalid: the Go SDK refuses a comment
    for entry in ("0.manifest.json", "0.payload"):
        assert zipcases.entry_bytes(out, entry) == _read(zip_base, entry)


@pytest.mark.parametrize("name", ADVERSARIAL)
def test_adversarial_cases_contradict(name: str, zip_base: Path, tmp_path: Path):
    out = _build(name, zip_base, tmp_path)
    zipcases.check_derived(name, zip_base, out)
    base_trailer, _ = zipmutate.load_trailer(zip_base)
    trailer = zipcases.ZIP_TRAILERS[name](zip_base)
    assert _trailer_diff(base_trailer, trailer) == SOURCE_ZIP[name]


def test_zip_entry_sentinels_defer_every_field(zip_base: Path):
    trailer = zipcases.ZIP_TRAILERS["zip-legal-zip64-entry-sentinels"](zip_base)
    assert trailer.force_zip64_eocd and len(trailer.entries) == 2
    for e in trailer.entries:
        assert e.force_zip64_compressed_size
        assert e.force_zip64_uncompressed_size
        assert e.force_zip64_offset
        assert e.extra_prefix == zipmutate.FOREIGN_EXTRA_TLV


def test_zip_cases_keep_local_bytes(zip_base: Path, tmp_path: Path):
    _, cd_offset = zipmutate.load_trailer(zip_base)
    for name in zipcases.ZIP_CASES:
        out = _build(name, zip_base, tmp_path)
        assert out.read_bytes()[:cd_offset] == zip_base.read_bytes()[:cd_offset]


# --- sidecars and install ----------------------------------------------------


def test_key_stem():
    assert tamper.key_stem("go-basic") == "tamper-go-basic"
    assert tamper.key_stem(tamper.X5C_BASE) == tamper.X5C_BASE
    for p in steps.plan(corpus.kas_keys(), Path("scratch")):
        if p.kind == "base":
            base = p.name.removeprefix("tamper-base-").removesuffix(".tdf")
            assert p.key_stem == tamper.key_stem(base)


def test_renames_cover_unprefixed_source():
    assert len(sidecars.RENAMES) == 19
    for old, new in sidecars.RENAMES.items():
        assert new == f"synthetic-{old}"
        assert not old.startswith(corpus.PREFIXES)


def test_comment_tables_cover_every_fixture():
    assert set(sidecars.TAMPER_CHANGES) == set(tamper.RECIPES)
    assert set(sidecars.ZIP_CHANGES) == set(zipcases.ZIP_CASES)
    assert set(sidecars.SYNTHETIC_TEXT) == set(sidecars.RENAMES.values())
    # The file has no keyAccess, so its comment must not describe a KAO.
    assert "KAO" not in sidecars.SYNTHETIC_TEXT["synthetic-no-keyaccess.tdf"]


def _old_sidecar(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "old.tdf.expect.toml"
    path.write_text(text)
    return path


def _parse(text: str, tmp_path: Path) -> dict[str, Any]:
    path = tmp_path / "new.tdf.expect.toml"
    path.write_text(text)
    return corpus.load_sidecar(path).raw


OLD_TAMPER = """\
# Base: valid-tdf.tdf, re-signed. See keys/tamper-go-basic.dek.
expect = "invalid"
format = "tdf"
verify_crypto = true
key = "keys/tamper-go-basic.dek"
must_contain = ["TDF.CRYPTO.ROOT_SIGNATURE_INVALID"]
note = "Derived from valid-tdf.tdf; keyed root check fails."
"""


def test_carry_rewrites_key_paths_and_names(tmp_path: Path):
    src = _old_sidecar(tmp_path, OLD_TAMPER)
    refs = sidecars.KeyRefs(key="keys/tamper-web-basic.dek")
    text = sidecars.carry_sidecar(src, ["Base: synthetic-valid-tdf.tdf."], refs)
    raw = _parse(text, tmp_path)
    assert raw["key"] == "keys/tamper-web-basic.dek"
    assert (
        raw["note"] == "Derived from synthetic-valid-tdf.tdf; keyed root check fails."
    )
    assert "tamper-go-basic" not in text
    assert "valid-tdf.tdf" not in text.replace("synthetic-valid-tdf.tdf", "")
    assert text.startswith("# Base: synthetic-valid-tdf.tdf.\n")


def test_carry_drops_private_refs(tmp_path: Path):
    # Stand-ins: the real identifiers must not appear anywhere in xtest/.
    old = """\
# Written against a local platform on localhost:8080 (ticket ABC-1234), per
# notes kept elsewhere.
expect = "valid"
format = "tdf"
key = "keys/old.dek"
note = "Go SDK v0.34.0: two KAS hosts (localhost:8080 key r1, localhost:8282 key b1)."
"""
    refs = sidecars.KeyRefs(key="keys/sdk-go-split-allof-two-kas.dek")
    text = sidecars.carry_sidecar(
        _old_sidecar(tmp_path, old), ["Fresh."], refs, writer="Go SDK v0.36.0"
    )
    for gone in ("ABC-1234", "notes kept elsewhere", "localhost:8080", "8282"):
        assert gone not in text
    assert _parse(text, tmp_path)["note"] == (
        "Go SDK v0.36.0: two KAS hosts (localhost:8585 key corpus-r2048,"
        " localhost:8686 key corpus-r2048-b)."
    )


@pytest.mark.parametrize(
    "note",
    ["See DSPX-0000.", "Written against localhost:9999.", "KAS key q7 (unknown)."],
)
def test_carry_refuses_notes_it_cannot_rewrite(note: str, tmp_path: Path):
    src = _old_sidecar(tmp_path, f'expect = "valid"\nnote = "{note}"\n')
    with pytest.raises(sidecars.SidecarGenError):
        sidecars.carry_sidecar(src, [], sidecars.KeyRefs())


def test_carry_preserves_validator_fields(tmp_path: Path):
    old = """\
expect = "invalid"
format = "tdf"
strict = true
verify_crypto = true
key = "keys/old.dek"
must_contain = ["TDF.SEMANTIC.SEGMENT_SIZE_MISMATCH", "TDF.CRYPTO.ROOT_SIGNATURE_INVALID"]
must_not_contain = []
note = "Multi-segment: last segment dropped."
"""
    src = _old_sidecar(tmp_path, old)
    refs = sidecars.KeyRefs(key="keys/tamper-web-multi-segment.dek")
    raw = _parse(sidecars.carry_sidecar(src, ["c"], refs), tmp_path)
    before = corpus.load_sidecar(src).raw
    fields = ["expect", "format", "strict", "verify_crypto"]
    tail = ["must_contain", "must_not_contain", "note"]
    for field in fields + tail:
        assert raw[field] == before[field], field
    assert list(raw) == [*fields, "key", *tail]


def test_carry_key_fields_follow_the_old_sidecar(tmp_path: Path):
    keyless = _old_sidecar(tmp_path, 'expect = "valid"\nverify_crypto = true\n')
    staged = sidecars.KeyRefs(
        key="keys/a.dek",
        share_keys=("1=keys/a.1.share",),
        assertion_keys=("keys/a.leaf.pub.pem",),
    )
    raw = _parse(sidecars.carry_sidecar(keyless, [], staged), tmp_path)
    assert raw == {"expect": "valid", "verify_crypto": True}

    # Staged shares join a keyed check the old sidecar gave none.
    dek_only = _old_sidecar(tmp_path, 'expect = "valid"\nkey = "keys/x.dek"\n')
    raw = _parse(sidecars.carry_sidecar(dek_only, [], staged), tmp_path)
    assert raw == {
        "expect": "valid",
        "key": "keys/a.dek",
        "share_keys": ["1=keys/a.1.share"],
    }

    keyed = _old_sidecar(
        tmp_path,
        'expect = "valid"\nkey = "keys/x.dek"\n'
        'share_keys = ["u=keys/x.u.share"]\nassertion_keys = ["keys/x.pub.pem"]\n',
    )
    raw = _parse(sidecars.carry_sidecar(keyed, [], staged), tmp_path)
    assert raw["key"] == "keys/a.dek"
    assert raw["share_keys"] == ["1=keys/a.1.share"]
    assert raw["assertion_keys"] == ["keys/a.leaf.pub.pem"]
    for missing in (
        dataclasses.replace(staged, key=None),
        dataclasses.replace(staged, share_keys=()),
        dataclasses.replace(staged, assertion_keys=()),
    ):
        with pytest.raises(sidecars.SidecarGenError):
            sidecars.carry_sidecar(keyed, [], missing)


SDK_TABLE = (
    "[sdk]\n"
    "# A comment the table keeps.\n"
    f'plaintext_sha256 = "{"ab" * 32}"\n'
    'go = [{ verdict = "reject", before = "0.42.0" }, { verdict = "decrypt" }]\n'
    'java = "decrypt"\n'
    'js = "reject"\n'
    'note = "Kept as written."\n'
)


@pytest.mark.parametrize("header", ["[sdk]  # hand-edited", "  [sdk]", "[ sdk ]"])
def test_sidecars_keep_sdk_table_under_any_header(tmp_path: Path, header: str):
    src = _old_sidecar(tmp_path, f"{OLD_TAMPER}\n{SDK_TABLE.replace('[sdk]', header)}")
    refs = sidecars.KeyRefs(key="keys/tamper-web-basic.dek")
    out = tmp_path / "new.tdf.expect.toml"
    out.write_text(sidecars.carry_sidecar(src, ["c"], refs))
    carried = corpus.load_sidecar(out).sdk
    assert carried is not None
    assert carried == corpus.load_sidecar(src).sdk


def test_sidecars_refuse_an_sdk_table_they_cannot_carry(tmp_path: Path):
    src = _old_sidecar(
        tmp_path, f"{OLD_TAMPER}\n{SDK_TABLE.replace('[sdk]', '["sdk"]')}"
    )
    with pytest.raises(sidecars.SidecarGenError, match="cannot carry"):
        sidecars.carry_sidecar(src, ["c"], sidecars.KeyRefs(key="keys/x.dek"))


def test_sidecars_keep_sdk_table(tmp_path: Path):
    src = _old_sidecar(tmp_path, f"{OLD_TAMPER}\n{SDK_TABLE}")
    refs = sidecars.KeyRefs(key="keys/tamper-web-basic.dek")
    text = sidecars.carry_sidecar(src, ["c"], refs)
    assert text.endswith(f'"\n\n{SDK_TABLE}')
    assert _parse(text, tmp_path)["key"] == "keys/tamper-web-basic.dek"
    assert (
        sidecars.carry_sidecar(_old_sidecar(tmp_path, OLD_TAMPER), [], refs).count(
            "[sdk]"
        )
        == 0
    )

    # The forged fixture's sidecar is written afresh, but keeps its table too.
    scratch, src_dir = tmp_path / "scratch", tmp_path / "src"
    keys_dir = scratch / "stage" / "keys"
    keys_dir.mkdir(parents=True)
    src_dir.mkdir()
    for suffix in (".dek", ".leaf.pub.pem"):
        (keys_dir / f"{tamper.X5C_BASE}{suffix}").write_text("00\n")
    (src_dir / f"{sidecars.FORGED}.tdf.expect.toml").write_text(
        f'expect = "invalid"\n\n{SDK_TABLE}'
    )
    entry = {"sdk": "java", "version": "0.20.0"}
    ctx = sidecars._Context(
        scratch,
        src_dir,
        {f"{tamper.X5C_BASE}.tdf": entry},
        {},
        {("java", "0.20.0"): "Java SDK 0.20.0"},
    )
    text = sidecars.sidecar_text(ctx, f"{sidecars.FORGED}.tdf")
    assert text.endswith(f'"\n\n{SDK_TABLE}')
    assert _parse(text, tmp_path)["expect"] == "invalid"


def test_rewrite_note_writer_prefix():
    main = "Web SDK main (0b5a0dea, after 0.23.0)"
    assert sidecars.rewrite_note("Web SDK 0.22.0: Defaults.", main) == (
        f"{main}: Defaults."
    )
    assert sidecars.rewrite_note(f"{main}: Defaults.", "Web SDK 0.24.0") == (
        "Web SDK 0.24.0: Defaults."
    )
    assert sidecars.rewrite_note("Go SDK v0.34.0: x.") == "Go SDK v0.34.0: x."


def test_provenance_from_describe():
    describe = sidecars.provenance_from_describe
    assert describe("Java SDK", "0.20.0", "v", "v0.20.0-0-g0658fd0") == (
        "Java SDK 0.20.0"
    )
    assert describe("Web SDK", "0.23.0", "sdk-v", "sdk-v0.23.0-17-g0b5a0dea") == (
        "Web SDK main (0b5a0dea, after 0.23.0)"
    )
    with pytest.raises(sidecars.SidecarGenError):
        describe("Web SDK", "0.24.0", "sdk-v", "sdk-v0.23.0-1-gabc")


def test_staged_refs(tmp_path: Path):
    for name in (
        "s.dek",
        "s.u-1.share",
        "s.u-2.share",
        "s.leaf.pub.pem",
        "s-x5c.dek",
        "s-x5c.pub.pem",
    ):
        (tmp_path / name).write_text("00\n")
    assert sidecars.staged_refs(tmp_path, "s") == sidecars.KeyRefs(
        key="keys/s.dek",
        share_keys=("u-1=keys/s.u-1.share", "u-2=keys/s.u-2.share"),
        assertion_keys=("keys/s.leaf.pub.pem",),
    )
    assert sidecars.staged_refs(tmp_path, "none") == sidecars.KeyRefs()


def test_forged_sidecar(tmp_path: Path):
    refs = sidecars.KeyRefs(
        key="keys/sdk-java-assertion-rs256-x5c.dek",
        assertion_keys=("keys/sdk-java-assertion-rs256-x5c.leaf.pub.pem",),
    )
    raw = _parse(sidecars.forged_sidecar(["c"], refs), tmp_path)
    assert {k: v for k, v in raw.items() if k != "note"} == {
        "expect": "invalid",
        "format": "tdf",
        "verify_crypto": True,
        "key": "keys/sdk-java-assertion-rs256-x5c.dek",
        "assertion_keys": ["keys/sdk-java-assertion-rs256-x5c.leaf.pub.pem"],
        "must_contain": ["TDF.CRYPTO.ASSERTION_SIGNATURE_INVALID"],
    }
    assert "SDK" not in raw.get("note", "")


def test_clear_outputs_removes_sidecars_and_synthetic_copies(tmp_path: Path):
    stage = tmp_path / "stage"
    for name in (
        "sdk-a.tdf",
        "sdk-a.tdf.expect.toml",
        "synthetic-x.tdf",
        "synthetic-x.tdf.expect.toml",
        "keys/sdk-a.dek",
        "keys/synthetic-x.dek",
    ):
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).write_text("x")
    sidecars.clear_outputs(stage)
    sidecars.clear_outputs(stage)
    assert sorted(_tree(stage)) == ["keys/sdk-a.dek", "sdk-a.tdf"]


# A fake scratch with one sdk fixture and one tamper fixture plus its base, and
# a corpus holding a golden, other files and an earlier generator output.
SDK_FIXTURE = "sdk-go-basic.tdf"
TAMPER_FIXTURE = "tamper-identity-go-basic.tdf"
FAKE_EXPECTED = [SDK_FIXTURE, TAMPER_FIXTURE]


def _touch(path: Path, mtime: int, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (mtime, mtime))


@pytest.fixture
def fake(tmp_path: Path) -> tuple[Path, Path]:
    scratch, dest = tmp_path / "scratch", tmp_path / "corpus"
    stage = scratch / "stage"
    _touch(scratch / "bases" / "tamper-base-go-basic.tdf", 100)
    _touch(stage / SDK_FIXTURE, 100)
    _touch(stage / TAMPER_FIXTURE, 200)
    _touch(stage / "keys" / "sdk-go-basic.dek", 300)
    _touch(stage / "keys" / "tamper-go-basic.dek", 300)
    for name, stem in (
        (SDK_FIXTURE, "sdk-go-basic"),
        (TAMPER_FIXTURE, "tamper-go-basic"),
    ):
        sidecar = f'expect = "valid"\nkey = "keys/{stem}.dek"\n'
        _touch(stage / f"{name}.expect.toml", 400, sidecar)
    for name in (
        "golden-a.tdf",
        "golden-a.tdf.expect.toml",
        "keys/golden-a.dek",
        "kas-keys.json",
        "README.md",
        "notes.txt",
        "sdk-old.tdf",
        "sdk-old.tdf.expect.toml",
        "keys/sdk-old.u-1.share",
    ):
        _touch(dest / name, 50, f"old {name}")
    return scratch, dest


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_install_replaces_generator_outputs(fake: tuple[Path, Path]):
    scratch, dest = fake
    before = _tree(dest)
    sidecars.install(scratch, dest, FAKE_EXPECTED)
    after = _tree(dest)
    kept = [
        "golden-a.tdf",
        "golden-a.tdf.expect.toml",
        "keys/golden-a.dek",
        "kas-keys.json",
        "README.md",
        "notes.txt",
    ]
    new = [
        SDK_FIXTURE,
        f"{SDK_FIXTURE}.expect.toml",
        TAMPER_FIXTURE,
        f"{TAMPER_FIXTURE}.expect.toml",
        "keys/sdk-go-basic.dek",
        "keys/tamper-go-basic.dek",
    ]
    assert sorted(after) == sorted(kept + new)
    assert {k: after[k] for k in kept} == {k: before[k] for k in kept}


def _refused(scratch: Path, dest: Path, match: str) -> None:
    before = _tree(dest)
    with pytest.raises(sidecars.InstallRefused) as e:
        sidecars.install(scratch, dest, FAKE_EXPECTED)
    assert any(match in p for p in e.value.problems), e.value.problems
    assert match in str(e.value)
    assert _tree(dest) == before


def test_install_refuses_missing_sidecar(fake: tuple[Path, Path]):
    scratch, dest = fake
    (scratch / "stage" / f"{SDK_FIXTURE}.expect.toml").unlink()
    _refused(scratch, dest, f"{SDK_FIXTURE}: no sidecar")


def test_install_refuses_missing_key(fake: tuple[Path, Path]):
    scratch, dest = fake
    (scratch / "stage" / "keys" / "tamper-go-basic.dek").unlink()
    _refused(
        scratch, dest, f"{TAMPER_FIXTURE}: missing key file keys/tamper-go-basic.dek"
    )


def test_install_refuses_stale_key(fake: tuple[Path, Path]):
    scratch, dest = fake
    os.utime(scratch / "stage" / "keys" / "sdk-go-basic.dek", (90, 90))
    _refused(scratch, dest, f"{SDK_FIXTURE}: keys/sdk-go-basic.dek is older than")


def test_install_refuses_tamper_older_than_base(fake: tuple[Path, Path]):
    scratch, dest = fake
    os.utime(scratch / "bases" / "tamper-base-go-basic.tdf", (250, 250))
    _refused(scratch, dest, f"{TAMPER_FIXTURE}: older than its base")


def test_install_refuses_missing_fixture(fake: tuple[Path, Path]):
    scratch, dest = fake
    (scratch / "stage" / TAMPER_FIXTURE).unlink()
    _refused(scratch, dest, f"{TAMPER_FIXTURE}: not staged")


def test_expected_fixtures_include_failed_writes():
    # A failed writer job is dropped from manifest.json; install must still
    # expect its fixture, so it refuses rather than deleting the old copy.
    planned = {
        p.name
        for p in steps.plan(corpus.kas_keys(), Path("scratch"))
        if p.kind == "sdk"
    }
    assert planned <= set(sidecars.expected_fixtures())


# --- verdicts ----------------------------------------------------------------

D1, D2, D3, D4 = ("11" * 32, "22" * 32, "33" * 32, "44" * 32)
BUILDS = (
    ("go", "main"),
    ("go", "v0.41.0"),
    ("java", "main"),
    ("js", "main"),
    ("js", "v0.23.0"),
)
PLATFORMS = ("main", "v0.31.0")
GOOD = {"go": "decrypt", "java": "decrypt", "js": "decrypt"}
NONE = {"go": "reject", "java": "reject", "js": "reject"}
HYBRID = "sdk-go-hybrid-xwing.tdf"
FORGED_TDF = f"{sidecars.FORGED}.tdf"


def _semver(tag: str) -> list[int] | None:
    return [int(p) for p in tag[1:].split(".")] if tag.startswith("v") else None


def _row(
    fixture: str, sdk: str, version: str, platform: str, outcome: str, sha: str | None
) -> dict[str, Any]:
    return {
        "fixture": fixture,
        "sdk": sdk,
        "version": version,
        "sdk_semver": _semver(version),
        "platform_tag": platform,
        "platform_version": "0.31.0",
        "platform_semver": _semver(platform),
        "outcome": outcome,
        "output_sha256": sha if outcome == "decrypt" else None,
        "stderr_tail": "",
    }


def _rows(
    fixture: str,
    outcomes: dict[str, str],
    sha: str | None = None,
    skip: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """A row per build and platform. ``outcomes`` is keyed by sdk, sdk@version
    or sdk@version/platform; the most specific key wins."""
    out = []
    for sdk, version in BUILDS:
        if sdk in skip:
            continue
        for platform in PLATFORMS:
            outcome = next(
                outcomes[k]
                for k in (f"{sdk}@{version}/{platform}", f"{sdk}@{version}", sdk)
                if k in outcomes
            )
            out.append(_row(fixture, sdk, version, platform, outcome, sha))
    return out


def _cells(rows: list[dict[str, Any]]) -> list[verdicts.Cell]:
    return [verdicts.Cell.from_row(r) for r in rows]


def _fake_rows(
    replace: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Rows for every fake fixture; js is skipped on the hybrid."""
    rows = {
        "sdk-go-basic.tdf": _rows("sdk-go-basic.tdf", GOOD, D1),
        HYBRID: _rows(HYBRID, GOOD, D2, skip=("js",)),
        "tamper-identity-go-basic.tdf": _rows("tamper-identity-go-basic.tdf", GOOD, D3),
        FORGED_TDF: _rows(FORGED_TDF, GOOD, D4),
        "synthetic-no-manifest.tdf": _rows("synthetic-no-manifest.tdf", NONE),
        "synthetic-valid-tdf.tdf": _rows("synthetic-valid-tdf.tdf", NONE),
        "synthetic-trailing-data.tdf": _rows("synthetic-trailing-data.tdf", NONE),
        "synthetic-not-a-tdf.bin": _rows("synthetic-not-a-tdf.bin", NONE),
        "synthetic-no-keyaccess.tdf": _rows("synthetic-no-keyaccess.tdf", NONE),
    }
    rows.update(replace or {})
    return [r for rs in rows.values() for r in rs]


def _record(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / f"rec-{len(list(tmp_path.glob('rec-*')))}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


FAKE_SIDECARS = {
    "golden-a.tdf": '# A golden.\nexpect = "valid"\n',
    "sdk-go-basic.tdf": '# Written by the Go SDK.\nexpect = "valid"\nnote = "Defaults."\n',
    HYBRID: 'expect = "valid"\n',
    "tamper-identity-go-basic.tdf": 'expect = "valid"\n',
    FORGED_TDF: 'expect = "invalid"\n',
    "synthetic-no-manifest.tdf": (
        'expect = "invalid"\nmust_contain = ["TDF.STRUCTURE.MISSING_MANIFEST"]\n'
    ),
    "synthetic-valid-tdf.tdf": 'expect = "valid"\nmust_contain = []\n',
    "synthetic-trailing-data.tdf": (
        'expect = "invalid"\nmust_contain = ["TDF.CONTAINER.AMBIGUOUS_LAYOUT"]\n'
    ),
    "synthetic-not-a-tdf.bin": (
        'expect = "unknown-format"\nmust_contain = ["CORE.DETECT.UNKNOWN_FORMAT"]\n'
    ),
    "synthetic-no-keyaccess.tdf": (
        'expect = "invalid"\nmust_contain = ["TDF.SEMANTIC.KEY_ACCESS_MISSING"]\n'
    ),
}
STAGED = "sdk-go-basic.tdf.expect.toml"
STAGED_HEAD = '# Staged, newer comments.\nexpect = "valid"\n'


@pytest.fixture
def vcorpus(tmp_path: Path) -> tuple[Path, Path]:
    """A corpus with one fixture of each kind, and a scratch holding the
    generator's plaintext digests."""
    root, scratch = tmp_path / "corpus", tmp_path / "scratch"
    root.mkdir()
    scratch.mkdir()
    xwing = {"kid": "corpus-xwing", "alg": "hpqt:xwing", "kas": "km1"}
    (root / "kas-keys.json").write_text(json.dumps([xwing]))
    (root / "README.md").write_text("readme")
    kao = {"type": "hybrid-wrapped", "kid": "corpus-xwing"}
    with zipfile.ZipFile(root / HYBRID, "w") as z:
        z.writestr(
            "0.manifest.json",
            json.dumps({"encryptionInformation": {"keyAccess": [kao]}}),
        )
    for name, text in FAKE_SIDECARS.items():
        if not (root / name).exists():
            (root / name).write_bytes(b"x")
        (root / f"{name}{corpus.SIDECAR_SUFFIX}").write_text(text)
    digests = {
        "sdk-go-basic.tdf": D1,
        HYBRID: D2,
        "tamper-base-go-basic.tdf": D3,
        f"{tamper.X5C_BASE}.tdf": D4,
    }
    manifest = {n: {"plaintext_sha256": d} for n, d in digests.items()}
    (scratch / "manifest.json").write_text(json.dumps(manifest))
    stale = '\n[sdk]\ngo = "reject"\njava = "reject"\njs = "reject"\n'
    (scratch / "stage").mkdir()
    (scratch / "stage" / STAGED).write_text(STAGED_HEAD + stale)
    return root, scratch


def _table(root: Path, name: str) -> corpus.SdkTable:
    table = corpus.load_sidecar(root / f"{name}{corpus.SIDECAR_SUFFIX}").sdk
    assert table is not None
    return table


def _resolve(table: corpus.SdkTable, sdk: str, version: str) -> str:
    v = _semver(version)
    return corpus.resolve_verdict(table, sdk, (v[0], v[1], v[2]) if v else None, None)


def test_verdicts_collapse_agreeing_cells(vcorpus: tuple[Path, Path], tmp_path: Path):
    assert verdicts.collapse(_cells(_rows("f", NONE, skip=("java", "js")))) == "reject"
    root, scratch = vcorpus
    before = _tree(root)
    rows = _fake_rows()
    recs = [
        _record(tmp_path, [r for r in rows if r["platform_tag"] == p])
        for p in PLATFORMS
    ]
    assert verdicts.run_verdicts(recs, scratch, root) == 0
    after = _tree(root)
    written = [f"{n}{corpus.SIDECAR_SUFFIX}" for n in FAKE_SIDECARS][1:]
    assert sorted(k for k in after if after[k] != before[k]) == sorted(written)
    for name in written:
        # Every line above the table is kept byte for byte.
        assert after[name].startswith(before[name] + b"\n[sdk]\n"), name
    basic = "sdk-go-basic.tdf.expect.toml"
    assert (
        after[basic]
        == before[basic]
        + (
            f'\n[sdk]\nplaintext_sha256 = "{D1}"\n'
            'go = "decrypt"\njava = "decrypt"\njs = "decrypt"\n'
        ).encode()
    )
    assert _table(root, "tamper-identity-go-basic.tdf").plaintext_sha256 == D3
    for name, note in (
        ("synthetic-no-manifest.tdf", "Synthetic: no usable manifest."),
        ("synthetic-not-a-tdf.bin", "Synthetic: no usable manifest."),
        ("synthetic-valid-tdf.tdf", "Synthetic: no KAS holds this key."),
        ("synthetic-trailing-data.tdf", "Synthetic: no KAS holds this key."),
        ("synthetic-no-keyaccess.tdf", "Synthetic: no key access object."),
    ):
        table = _table(root, name)
        assert (table.plaintext_sha256, table.note) == (None, note)
        assert {_resolve(table, sdk, v) for sdk, v in BUILDS} == {"reject"}
    forged = after[f"{FORGED_TDF}{corpus.SIDECAR_SUFFIX}"].decode()
    forged = forged.replace("\n# ", " ")
    assert "with go main and v0.41.0, java main, js main and v0.23.0;" in forged
    assert (
        "expected to change with pending SDK assertion-verification work.\n" in forged
    )
    assert "assertion error" not in forged
    # A second run replaces the tables it wrote.
    assert verdicts.run_verdicts(recs, scratch, root) == 0
    assert _tree(root) == after


def test_verdicts_report_disagreement(
    vcorpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    by_platform = {"go": "decrypt", "go@main/v0.31.0": "reject"}
    with pytest.raises(verdicts.VerdictError, match="v0.31.0"):
        verdicts.collapse(_cells(_rows("f", by_platform, D1, skip=("java", "js"))))
    releases = _rows("f", NONE, skip=("java", "js")) + [
        _row("f", "go", "v0.40.0", p, "decrypt", D1) for p in PLATFORMS
    ]
    with pytest.raises(verdicts.VerdictError, match="v0.40.0"):
        verdicts.collapse(_cells(releases))

    root, scratch = vcorpus
    bad = _rows("sdk-go-basic.tdf", {**GOOD, "js@v0.23.0/main": "reject"}, D1)
    rec = _record(tmp_path, _fake_rows({"sdk-go-basic.tdf": bad}))
    before = _tree(tmp_path)
    assert verdicts.run_verdicts([rec], scratch, root) == 1
    err = capsys.readouterr().err
    assert "sdk-go-basic.tdf" in err
    assert "js@v0.23.0" in err
    assert _tree(tmp_path) == before


def test_verdicts_bound_main_against_release(
    vcorpus: tuple[Path, Path], tmp_path: Path
):
    rows = _rows("sdk-go-basic.tdf", {**GOOD, "go@v0.41.0": "reject"}, D1)
    assert verdicts.collapse(_cells([r for r in rows if r["sdk"] == "go"])) == [
        {"verdict": "reject", "before": "0.42.0"},
        {"verdict": "decrypt"},
    ]
    root, scratch = vcorpus
    rec = _record(tmp_path, _fake_rows({"sdk-go-basic.tdf": rows}))
    assert verdicts.run_verdicts([rec], scratch, root) == 0
    text = (root / "sdk-go-basic.tdf.expect.toml").read_text()
    assert (
        'go = [{ verdict = "reject", before = "0.42.0" }, { verdict = "decrypt" }]\n'
        in text
    )
    table = _table(root, "sdk-go-basic.tdf")
    assert _resolve(table, "go", "v0.41.0") == "reject"
    assert _resolve(table, "go", "v0.42.0") == "decrypt"
    assert _resolve(table, "go", "main") == "decrypt"


@pytest.mark.parametrize("outcome", ["decrypt", "reject"])
def test_verdicts_skipped_sdk_takes_agreed_outcome(
    outcome: str, vcorpus: tuple[Path, Path], tmp_path: Path
):
    root, scratch = vcorpus
    agreed = _rows(HYBRID, dict.fromkeys(corpus.SDK_NAMES, outcome), D2, skip=("js",))
    rec = _record(tmp_path, _fake_rows({HYBRID: agreed}))
    assert verdicts.run_verdicts([rec], scratch, root) == 0
    table = _table(root, HYBRID)
    assert _resolve(table, "js", "main") == outcome
    assert _resolve(table, "go", "main") == outcome
    assert table.note == (
        "The js cell is skipped because js lacks mechanism-xwing;"
        " js takes the other SDKs' verdict."
    )


def test_verdicts_skipped_sdk_refusals(
    vcorpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    root, scratch = vcorpus
    before = _tree(root), _tree(scratch)
    # The SDKs that ran disagree, so the skipped one has no verdict to take.
    split = _rows(HYBRID, {**GOOD, "java": "reject"}, D2, skip=("js",))
    rec = _record(tmp_path, _fake_rows({HYBRID: split}))
    assert verdicts.run_verdicts([rec], scratch, root) == 1
    err = capsys.readouterr().err
    assert f"{HYBRID}: no js cells, and the SDKs that ran disagree" in err
    assert "java@main on platform main: reject" in err

    # No capability explains a missing sdk-go-basic cell.
    gap = _rows("sdk-go-basic.tdf", GOOD, D1, skip=("js",))
    rec2 = _record(tmp_path, _fake_rows({"sdk-go-basic.tdf": gap}))
    assert verdicts.run_verdicts([rec2], scratch, root) == 1
    assert "sdk-go-basic.tdf: no js cells" in capsys.readouterr().err
    assert (_tree(root), _tree(scratch)) == before


def test_verdicts_refuse_a_fixture_no_sdk_ran(
    vcorpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Every SDK skipping a fixture points at the platform or env, not the SDKs."""
    root, scratch = vcorpus
    before = _tree(root), _tree(scratch)
    rec = _record(tmp_path, _fake_rows({HYBRID: []}))
    assert verdicts.run_verdicts([rec], scratch, root) == 1
    err = capsys.readouterr().err
    assert f"{HYBRID}: no SDK recorded a cell" in err
    assert "PLATFORM_VERSION" in err
    assert (_tree(root), _tree(scratch)) == before
    with pytest.raises(verdicts.VerdictError, match="no SDK recorded a cell"):
        verdicts.table_text(HYBRID, {}, {}, D2, ["mechanism-xwing"])


@pytest.mark.parametrize("scratch_state", ["absent", "lacks-fixtures"])
def test_verdicts_without_generator_scratch(
    scratch_state: str, vcorpus: tuple[Path, Path], tmp_path: Path
):
    """Digests come from the sidecars' own [sdk] tables when the generator's
    manifest is gone or does not list the fixture."""
    root, scratch = vcorpus
    rec = _record(tmp_path, _fake_rows())
    assert verdicts.run_verdicts([rec], scratch, root) == 0
    first = _tree(root)
    if scratch_state == "absent":
        shutil.rmtree(scratch)
    else:
        (scratch / "manifest.json").write_text("{}")
    assert verdicts.run_verdicts([rec], scratch, root) == 0
    assert _tree(root) == first
    assert _table(root, "tamper-identity-go-basic.tdf").plaintext_sha256 == D3


def test_verdicts_refuse_without_any_digest(
    vcorpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    root, scratch = vcorpus
    (scratch / "manifest.json").unlink()
    before = _tree(root), _tree(scratch)
    assert verdicts.run_verdicts([_record(tmp_path, _fake_rows())], scratch, root) == 1
    err = capsys.readouterr().err
    assert (
        "sdk-go-basic.tdf: go@main on platform main: decrypt, but no plaintext" in err
    )
    # Synthetic fixtures need no digest.
    assert "synthetic-" not in err
    assert (_tree(root), _tree(scratch)) == before


@pytest.mark.parametrize(
    ("fixture", "rows"),
    [
        ("sdk-go-basic.tdf", _rows("sdk-go-basic.tdf", GOOD, D2)),
        (
            "sdk-go-basic.tdf",
            _rows("sdk-go-basic.tdf", {**GOOD, "java": "wrong-plaintext"}, D1),
        ),
        ("synthetic-valid-tdf.tdf", _rows("synthetic-valid-tdf.tdf", GOOD, D1)),
    ],
    ids=["mismatch", "wrong-plaintext", "synthetic-decrypt"],
)
def test_verdicts_refuse_plaintext_mismatch(
    fixture: str,
    rows: list[dict[str, Any]],
    vcorpus: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    root, scratch = vcorpus
    rec = _record(tmp_path, _fake_rows({fixture: rows}))
    before = _tree(tmp_path)
    assert verdicts.run_verdicts([rec], scratch, root) == 1
    assert fixture in capsys.readouterr().err
    assert _tree(tmp_path) == before


def test_verdicts_bound_at_the_newest_release():
    rows = _rows("f", {"go": "reject", "go@main": "decrypt"}, D1, skip=("java", "js"))
    rows += [_row("f", "go", "v0.40.0", p, "reject", None) for p in PLATFORMS]
    assert verdicts.collapse(_cells(rows)) == [
        {"verdict": "reject", "before": "0.42.0"},
        {"verdict": "decrypt"},
    ]


# Gives go@main on platform v0.31.0 its own verdict, which collapse cannot.
HAND_WRITTEN = (
    '[{ verdict = "reject", since = "0.42.0", platform_before = "0.32.0" },'
    ' { verdict = "decrypt" }]'
)


@pytest.mark.parametrize("good", [True, False], ids=["gives-every-cell", "wrong"])
def test_verdicts_keep_hand_written_entry(
    good: bool,
    vcorpus: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    root, scratch = vcorpus
    entry = HAND_WRITTEN if good else HAND_WRITTEN.replace("0.32.0", "0.31.0")
    path = root / "sdk-go-basic.tdf.expect.toml"
    head = path.read_text()
    path.write_text(
        f'{head}\n[sdk]\nplaintext_sha256 = "{D1}"\ngo = {entry}\n'
        'java = "reject"\njs = "reject"\nnote = "Hand-written."\n'
    )
    split = _rows("sdk-go-basic.tdf", {**GOOD, "go@main/v0.31.0": "reject"}, D1)
    rec = _record(tmp_path, _fake_rows({"sdk-go-basic.tdf": split}))
    before = _tree(tmp_path)
    rc = verdicts.run_verdicts([rec], scratch, root)
    out, err = capsys.readouterr()
    if not good:
        assert rc == 1
        assert "go@main on platform v0.31.0: reject" in err
        assert _tree(tmp_path) == before
        return
    assert rc == 0
    assert "kept earlier entries: sdk-go-basic.tdf go" in out
    # The go entry is kept as written; java and js come from the cells.
    assert path.read_text() == (
        f'{head}\n[sdk]\nplaintext_sha256 = "{D1}"\ngo = {HAND_WRITTEN}\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )


def test_verdicts_update_staged_copies(vcorpus: tuple[Path, Path], tmp_path: Path):
    root, scratch = vcorpus
    assert verdicts.run_verdicts([_record(tmp_path, _fake_rows())], scratch, root) == 0
    _, table = sidecars.split_sdk_table((root / STAGED).read_text())
    assert (scratch / "stage" / STAGED).read_text() == f"{STAGED_HEAD}\n{table}"
    assert sorted(p.name for p in (scratch / "stage").iterdir()) == [STAGED]


@pytest.mark.parametrize("bad", ["../x.tdf", "/etc/x.tdf", "stage/../../x.tdf"])
def test_writer_output_path_outside_scratch_is_refused(tmp_path: Path, bad: str):
    with pytest.raises(steps.StepError, match="outside"):
        steps._output_path(tmp_path, bad)


def test_writer_output_path_inside_scratch_passes(tmp_path: Path):
    ok = tmp_path / "stage" / "sdk-go-x.tdf"
    assert steps._output_path(tmp_path, str(ok)) == ok.resolve()
    base = tmp_path / "bases" / "tamper-base-x.tdf"
    assert steps._output_path(tmp_path, str(base)) == base.resolve()


def _fake_writer(tmp_path: Path, out: str, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "w.py"
    rec = {"out": out, "sdk": "s", "version": "v"}
    script.write_text(f"import json\nprint(json.dumps({rec!r}))\n")
    monkeypatch.setattr(
        steps.runtime, "writer_cmd", lambda sdk: [sys.executable, str(script)]
    )
    monkeypatch.setattr(steps.runtime, "XTEST", tmp_path)


def _planned(out: Path) -> Any:
    return steps.Planned("a.tdf", "sdk", "go", "a", 0, {}, out)  # type: ignore[arg-type]


def test_run_writers_refuses_escaping_writer_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _fake_writer(tmp_path, "../x.tdf", monkeypatch)
    p = _planned(tmp_path / "stage" / "a.tdf")
    with pytest.raises(steps.StepError, match="outside"):
        steps._run_writers({"go": [p]}, tmp_path, dict(os.environ))


def test_run_writers_accepts_planned_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    out = (tmp_path / "stage" / "a.tdf").resolve()
    _fake_writer(tmp_path, str(out), monkeypatch)
    written, failed = steps._run_writers(
        {"go": [_planned(out)]}, tmp_path, dict(os.environ)
    )
    assert failed == [] and written[str(out)]["sdk"] == "s"


@pytest.mark.parametrize(
    "entry",
    [
        {"plaintext": "/etc/hosts", "job": {"out": "x"}},
        {"plaintext": "../p.txt", "job": {"out": "x"}},
        {"plaintext": "p.txt", "job": {"out": "../../x.tdf"}},
    ],
)
def test_manifest_paths_outside_scratch_are_refused(
    tmp_path: Path, entry: dict[str, Any]
):
    (tmp_path / "plaintexts").mkdir()
    (tmp_path / "plaintexts" / "p.txt").write_bytes(b"")
    entry["plaintext_sha256"] = hashlib.sha256(b"").hexdigest()
    with pytest.raises((ValueError, steps.StepError), match="outside|escapes"):
        steps._key_files(entry, lambda kao: b"", tmp_path)  # type: ignore[arg-type]


def test_inside_allows_nested_and_refuses_escape(tmp_path: Path):
    assert steps.runtime.inside(tmp_path, "a/b.txt") == (tmp_path / "a/b.txt").resolve()
    with pytest.raises(steps.runtime.PathEscapeError):
        steps.runtime.inside(tmp_path, "../b.txt")


def test_scratch_dir_defaults_under_xtest(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("XT_TMP_DIR", raising=False)
    expect = steps.runtime.XTEST / "tmp" / "corpus_gen"
    assert steps.runtime.scratch_dir() == expect.resolve()
    monkeypatch.setenv("XT_TMP_DIR", "/tmp/xt-custom")
    assert steps.runtime.scratch_dir() == Path("/tmp/xt-custom/corpus_gen").resolve()


@pytest.mark.parametrize("stem", ["../x", "/etc/x", "a/../../x"])
def test_staged_refs_refuses_escaping_key_stem(tmp_path: Path, stem: str):
    with pytest.raises(steps.runtime.PathEscapeError):
        sidecars.staged_refs(tmp_path / "keys", stem)


def test_staged_refs_accepts_plain_key_stem(tmp_path: Path):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "sdk-go-x.dek").write_text("00\n")
    assert sidecars.staged_refs(keys, "sdk-go-x").key == "keys/sdk-go-x.dek"
