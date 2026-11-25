"""The tamper-* fixtures: a real SDK-written base with exactly one deliberate change.

Manifest changes are literal, single-occurrence edits of the raw manifest text,
so key order and formatting stay as the SDK wrote them. Output is re-zipped
STORED with correct CRCs unless the container itself is the change.
check_derived() proves each output differs from its base only where its recipe
says. Offline: nothing here talks to the platform.
"""

import base64
import json
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import assertions
import zipinspect
from corpus_gen import deks, pki, runtime
from corpus_gen.variants import TAMPER_BASES, Keys

MANIFEST = "0.manifest.json"
PAYLOAD = "0.payload"
X5C_BASE = "sdk-java-assertion-rs256-x5c"
ATTACKER_KAS = "https://kas.attacker.example/kas"
# A ciphertext byte of the first segment: past the IV, short of the tag.
CIPHERTEXT_BYTE = 17

Apply = Callable[[Path, Path, Keys], None]
Container = Literal["stored", "deflate", "in-place"]


class TamperError(ValueError):
    pass


@dataclass(frozen=True)
class Recipe:
    base: str  # a TAMPER_BASES name, or X5C_BASE
    touches: tuple[str, ...]  # manifest JSON paths the change may touch
    apply: Apply  # (base file, output file, corpus keys)
    payload: bool = False  # 0.payload bytes change
    # stored: re-zipped STORED; deflate: re-zipped DEFLATE; in-place: one
    # payload byte flipped inside the base's own archive, CRC left stale.
    container: Container = "stored"
    # The payload bytes that change, negative from the end. Empty with
    # ``payload``: the segments are reordered, each with its own bytes.
    payload_bytes: tuple[int, ...] = ()


def edit_manifest_text(text: str, old: str, new: str) -> str:
    """Replace the one occurrence of ``old``; raise unless there is exactly one."""
    first = text.find(old)
    if first < 0 or text.find(old, first + 1) >= 0:
        n = "no" if first < 0 else "more than one"
        raise TamperError(f"{n} occurrence of {old[:80]!r}")
    return text[:first] + new + text[first + len(old) :]


def _rezip(src: Path, dest: Path, replace: dict[str, bytes], method: int) -> None:
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        unknown = set(replace) - {i.filename for i in infos}
        if unknown:
            raise TamperError(f"{src.name} has no entries {sorted(unknown)}")
        entries = [
            (i, replace[i.filename] if i.filename in replace else z.read(i))
            for i in infos
        ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w") as z:
        for info, data in entries:
            # Same name, order, timestamp and mode, so re-runs are byte-identical.
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.compress_type = method
            out.external_attr = info.external_attr or 0o600 << 16
            z.writestr(out, data)


def rezip_stored(src: Path, dest: Path, replace: dict[str, bytes]) -> None:
    """Every entry STORED, in the original order with correct CRCs, substituting
    the entries in ``replace``."""
    _rezip(src, dest, replace, zipfile.ZIP_STORED)


def _read(tdf: Path, entry: str) -> bytes:
    with zipfile.ZipFile(tdf) as z:
        return z.read(entry)


def _compact(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _field(key: str, value: object) -> str:
    """``"key":value`` as compact JSON writes it."""
    return f"{_compact(key)}:{_compact(value)}"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _flip_bit(data: bytes) -> bytes:
    return bytes([data[0] ^ 1]) + data[1:]


def _invert_tail(data: bytes, n: int = 3) -> bytes:
    return data[:-n] + bytes(b ^ 0xFF for b in data[-n:])


# Manifest edits: (manifest text, parsed manifest) -> edited text.
Edit = Callable[[str, dict[str, Any]], str]


def _manifest_edit(edit: Edit) -> Apply:
    def apply(src: Path, dest: Path, _keys: Keys) -> None:
        text = _read(src, MANIFEST).decode()
        rezip_stored(src, dest, {MANIFEST: edit(text, json.loads(text)).encode()})

    return apply


def _kao(m: dict[str, Any]) -> dict[str, Any]:
    (kao,) = m["encryptionInformation"]["keyAccess"]
    return kao


def _integrity(m: dict[str, Any]) -> dict[str, Any]:
    return m["encryptionInformation"]["integrityInformation"]


def _assertion(m: dict[str, Any]) -> dict[str, Any]:
    """The base's only assertion (recipes name it assertions[0])."""
    (a,) = m["assertions"]
    return a


def _binding_hmac(m: dict[str, Any]) -> bytes:
    """The policy binding HMAC, from the SDK's hex-then-base64 form."""
    text = base64.b64decode(_kao(m)["policyBinding"]["hash"], validate=True).decode()
    mac = bytes.fromhex(text)
    if text != mac.hex():
        raise TamperError(f"policy binding is not lowercase hex: {text!r}")
    return mac


def _binding(make: Callable[[bytes], str]) -> Edit:
    def edit(text: str, m: dict[str, Any]) -> str:
        old = _kao(m)["policyBinding"]["hash"]
        new = make(_binding_hmac(m))
        return edit_manifest_text(text, _field("hash", old), _field("hash", new))

    return edit


def _root_signature(text: str, m: dict[str, Any]) -> str:
    old = _integrity(m)["rootSignature"]["sig"]
    new = _b64(_invert_tail(base64.b64decode(old, validate=True)))
    return edit_manifest_text(text, _field("sig", old), _field("sig", new))


def _gmac_root(alg: str) -> Edit:
    def edit(text: str, m: dict[str, Any]) -> str:
        # Imported here: importing tdfs sets the root logger to DEBUG.
        import tdfs

        forged = tdfs.forge_gmac_root_signature(
            tdfs.Manifest.model_validate_json(text), alg
        ).encryptionInformation.integrityInformation.rootSignature
        root = _integrity(m)["rootSignature"]
        new = {**root, "alg": forged.alg, "sig": forged.sig.decode("ascii")}
        return edit_manifest_text(
            text, _field("rootSignature", root), _field("rootSignature", new)
        )

    return edit


def _segment_hash(text: str, m: dict[str, Any]) -> str:
    old = _integrity(m)["segments"][0]["hash"]
    new = _b64(_flip_bit(base64.b64decode(old, validate=True)))
    return edit_manifest_text(text, _field("hash", old), _field("hash", new))


def _encrypted_segment_size(text: str, m: dict[str, Any]) -> str:
    seg = _integrity(m)["segments"][0]
    new = {**seg, "encryptedSegmentSize": seg["encryptedSegmentSize"] - 1}
    return edit_manifest_text(text, _compact(seg), _compact(new))


def _duplicate_kao(text: str, m: dict[str, Any]) -> str:
    kao = _kao(m)
    return edit_manifest_text(
        text, _field("keyAccess", [kao]), _field("keyAccess", [kao, kao])
    )


def _kas_url(text: str, m: dict[str, Any]) -> str:
    old = _kao(m)["url"]
    return edit_manifest_text(text, _field("url", old), _field("url", ATTACKER_KAS))


def _policy_body(text: str, m: dict[str, Any]) -> str:
    old = m["encryptionInformation"]["policy"]
    policy = base64.b64decode(old, validate=True).decode()
    policy = edit_manifest_text(
        policy, '"dissem":null', '"dissem":["mallory@example.com"]'
    )
    new = _b64(policy.encode())
    return edit_manifest_text(text, _field("policy", old), _field("policy", new))


def _edit_statement(text: str, a: dict[str, Any], old: str, new: str) -> str:
    """Edit inside the statement value, a JSON string held in the manifest."""
    value = a["statement"]["value"]
    edited = edit_manifest_text(value, old, new)
    return edit_manifest_text(text, _field("value", value), _field("value", edited))


def _statement(key: str, old: object, new: object) -> Edit:
    def edit(text: str, m: dict[str, Any]) -> str:
        a = _assertion(m)
        return _edit_statement(text, a, _field(key, old), _field(key, new))

    return edit


def _operating_system(text: str, m: dict[str, Any]) -> str:
    # The writer's host OS, so read from the base rather than assumed.
    a = _assertion(m)
    host = json.loads(a["statement"]["value"])["operating_system"]
    if host == "plan9":
        raise TamperError("base operating_system is already plan9")
    return _statement("operating_system", host, "plan9")(text, m)


def _drop_binding(text: str, m: dict[str, Any]) -> str:
    binding = _assertion(m)["binding"]
    return edit_manifest_text(text, "," + _field("binding", binding), "")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _rs256_jws(key_pem: str, cert_pem: str, claims: dict[str, str]) -> str:
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TamperError("forged signer is not an RSA key")
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    der = cert.public_bytes(serialization.Encoding.DER)
    header = {"alg": "RS256", "typ": "JWT", "x5c": [_b64(der)]}
    signing_input = (
        f"{_b64url(_compact(header).encode())}.{_b64url(_compact(claims).encode())}"
    )
    sig = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(sig)}"


def _claims(m: dict[str, Any], a: dict[str, Any]) -> dict[str, str]:
    h = assertions.assertion_hash(a)
    return {"assertionHash": h, "assertionSig": assertions.assertion_sig(m, h)}


def _x5c_forged(text: str, m: dict[str, Any]) -> str:
    """Caveat x5c -> forged, claims recomputed (manifest data only), re-signed
    RS256 by a self-signed certificate with the real leaf's subject, as x5c."""
    a = _assertion(m)
    signature = a["binding"]["signature"]
    jws = assertions.parse_jws(signature)
    if jws.claims != _claims(m, a):
        raise TamperError("base assertion claims do not match their recomputation")
    leaf = x509.load_der_x509_certificate(base64.b64decode(jws.header["x5c"][0]))
    text = _edit_statement(text, a, _field("caveat", "x5c"), _field("caveat", "forged"))
    m = json.loads(text)
    key_pem, cert_pem = pki.forged_signer(runtime.scratch_dir() / "pki", leaf.subject)
    forged = _rs256_jws(key_pem, cert_pem, _claims(m, _assertion(m)))
    return edit_manifest_text(
        text, _field("signature", signature), _field("signature", forged)
    )


def _identity(src: Path, dest: Path, _keys: Keys) -> None:
    rezip_stored(src, dest, {})


def _payload_edit(change: Callable[[bytes, dict[str, Any]], bytes]) -> Apply:
    def apply(src: Path, dest: Path, _keys: Keys) -> None:
        m = json.loads(_read(src, MANIFEST))
        rezip_stored(src, dest, {PAYLOAD: change(_read(src, PAYLOAD), m)})

    return apply


def _ciphertext_body(payload: bytes, m: dict[str, Any]) -> bytes:
    _, first = deks.segment_sizes(_integrity(m))[0]
    if not deks.IV_SIZE <= CIPHERTEXT_BYTE < first - deks.TAG_SIZE:
        raise TamperError(
            f"first segment of {first} bytes has no byte {CIPHERTEXT_BYTE}"
        )
    i = CIPHERTEXT_BYTE
    return payload[:i] + _flip_bit(payload[i : i + 1]) + payload[i + 1 :]


def _payload_in_place(src: Path, dest: Path, _keys: Keys) -> None:
    with zipfile.ZipFile(src) as z:
        if z.getinfo(PAYLOAD).compress_type != zipfile.ZIP_STORED:
            raise TamperError(f"{src.name}: payload is not STORED")
    raw = bytearray(src.read_bytes())
    raw[_payload_offset(src) + CIPHERTEXT_BYTE] ^= 1
    dest.write_bytes(raw)


def _payload_offset(tdf: Path) -> int:
    (entry,) = [
        e for e in zipinspect.central_directory(tdf).entries if e.name == PAYLOAD
    ]
    return zipinspect.local_file_header_data_offset(tdf, entry)


def _deflate(src: Path, dest: Path, _keys: Keys) -> None:
    _rezip(src, dest, {}, zipfile.ZIP_DEFLATED)


Reorder = Callable[[list[Any]], list[Any]]


def _segments(reorder: Reorder, payload: bool) -> Apply:
    """Reorder the manifest's segment list and, with ``payload``, the payload's
    ciphertext segments the same way."""

    def apply(src: Path, dest: Path, _keys: Keys) -> None:
        text = _read(src, MANIFEST).decode()
        integrity = _integrity(json.loads(text))
        segments = integrity["segments"]
        text = edit_manifest_text(
            text, _field("segments", segments), _field("segments", reorder(segments))
        )
        replace = {MANIFEST: text.encode()}
        if payload:
            data, chunks = _read(src, PAYLOAD), []
            sizes = [enc for _, enc in deks.segment_sizes(integrity)]
            if sum(sizes) != len(data):
                raise TamperError(f"segments {sizes} do not fill {len(data)} bytes")
            for size in sizes:
                chunks.append(data[:size])
                data = data[size:]
            replace[PAYLOAD] = b"".join(reorder(chunks))
        rezip_stored(src, dest, replace)

    return apply


_KAO0 = "encryptionInformation.keyAccess[0]"
_II = "encryptionInformation.integrityInformation"
_ROOT = (f"{_II}.rootSignature.alg", f"{_II}.rootSignature.sig")
_STATEMENT = "assertions[0].statement.value"

RECIPES: dict[str, Recipe] = {
    "tamper-assertion-binding-dropped": Recipe(
        "go-assertion-hs256", ("assertions[0].binding",), _manifest_edit(_drop_binding)
    ),
    "tamper-assertion-hs256-statement": Recipe(
        "go-assertion-hs256", (_STATEMENT,), _manifest_edit(_operating_system)
    ),
    # The same bytes; the sidecars differ in whether the signer key is given.
    "tamper-assertion-rs256-statement": Recipe(
        "go-assertion-rs256",
        (_STATEMENT,),
        _manifest_edit(_statement("caveat", "corpus", "none")),
    ),
    "tamper-assertion-rs256-statement-keyed": Recipe(
        "go-assertion-rs256",
        (_STATEMENT,),
        _manifest_edit(_statement("caveat", "corpus", "none")),
    ),
    "tamper-assertion-x5c-forged": Recipe(
        X5C_BASE,
        (_STATEMENT, "assertions[0].binding.signature"),
        _manifest_edit(_x5c_forged),
    ),
    "tamper-binding-hex-bitflip": Recipe(
        "go-basic",
        (f"{_KAO0}.policyBinding.hash",),
        _manifest_edit(_binding(lambda mac: _b64(_flip_bit(mac).hex().encode()))),
    ),
    "tamper-binding-hexless-bitflip": Recipe(
        "go-basic",
        (f"{_KAO0}.policyBinding.hash",),
        _manifest_edit(_binding(lambda mac: _b64(_flip_bit(mac)))),
    ),
    "tamper-binding-hexless-control": Recipe(
        "go-basic", (f"{_KAO0}.policyBinding.hash",), _manifest_edit(_binding(_b64))
    ),
    "tamper-ciphertext-body": Recipe(
        "go-basic",
        (),
        _payload_edit(_ciphertext_body),
        payload=True,
        payload_bytes=(CIPHERTEXT_BYTE,),
    ),
    "tamper-deflate": Recipe("go-basic", (), _deflate, container="deflate"),
    "tamper-duplicate-kao": Recipe(
        "go-basic",
        ("encryptionInformation.keyAccess[1]",),
        _manifest_edit(_duplicate_kao),
    ),
    "tamper-encrypted-segment-size": Recipe(
        "go-basic",
        (f"{_II}.segments[0].encryptedSegmentSize",),
        _manifest_edit(_encrypted_segment_size),
    ),
    "tamper-gmac-root-lower": Recipe(
        "go-basic", _ROOT, _manifest_edit(_gmac_root("gmac"))
    ),
    "tamper-gmac-root-mixed": Recipe(
        "go-basic", _ROOT, _manifest_edit(_gmac_root("GMac"))
    ),
    "tamper-gmac-root-upper": Recipe(
        "go-basic", _ROOT, _manifest_edit(_gmac_root("GMAC"))
    ),
    "tamper-identity-go-assertion-hs256": Recipe("go-assertion-hs256", (), _identity),
    "tamper-identity-go-assertion-rs256": Recipe("go-assertion-rs256", (), _identity),
    "tamper-identity-go-basic": Recipe("go-basic", (), _identity),
    "tamper-identity-web-multi-segment": Recipe("web-multi-segment", (), _identity),
    "tamper-kas-url-malicious": Recipe(
        "go-basic", (f"{_KAO0}.url",), _manifest_edit(_kas_url)
    ),
    "tamper-multi-segment-duplicate": Recipe(
        "web-multi-segment",
        (f"{_II}.segments",),
        _segments(lambda xs: xs[:1] + xs, payload=True),
        payload=True,
    ),
    "tamper-multi-segment-reverse": Recipe(
        "web-multi-segment",
        (f"{_II}.segments",),
        _segments(lambda xs: xs[::-1], payload=True),
        payload=True,
    ),
    # The payload keeps the dropped segment's bytes.
    "tamper-multi-segment-truncate": Recipe(
        "web-multi-segment",
        (f"{_II}.segments[2]",),
        _segments(lambda xs: xs[:-1], payload=False),
    ),
    "tamper-payload-in-place": Recipe(
        "go-basic",
        (),
        _payload_in_place,
        payload=True,
        container="in-place",
        payload_bytes=(CIPHERTEXT_BYTE,),
    ),
    "tamper-payload-tag": Recipe(
        "go-basic",
        (),
        _payload_edit(lambda p, _m: _invert_tail(p)),
        payload=True,
        payload_bytes=(-3, -2, -1),
    ),
    "tamper-policy-body": Recipe(
        "go-basic", ("encryptionInformation.policy",), _manifest_edit(_policy_body)
    ),
    # The same bytes; one sidecar is checked without a key.
    "tamper-root-signature": Recipe(
        "go-basic", (f"{_II}.rootSignature.sig",), _manifest_edit(_root_signature)
    ),
    "tamper-root-signature-keyless": Recipe(
        "go-basic", (f"{_II}.rootSignature.sig",), _manifest_edit(_root_signature)
    ),
    "tamper-segment-hash": Recipe(
        "go-basic", (f"{_II}.segments[0].hash",), _manifest_edit(_segment_hash)
    ),
}


def json_changes(a: object, b: object, path: str = "") -> list[str]:
    """Paths where ``b`` differs from ``a``: a changed value, or a key or list
    index present on one side only."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in [*a, *(k for k in b if k not in a)]:
            p = f"{path}.{k}" if path else str(k)
            if k in a and k in b:
                out += json_changes(a[k], b[k], p)
            else:
                out.append(p)
        return out
    if isinstance(a, list) and isinstance(b, list):
        out = []
        for i in range(max(len(a), len(b))):
            p = f"{path}[{i}]"
            out += json_changes(a[i], b[i], p) if i < min(len(a), len(b)) else [p]
        return out
    return [] if type(a) is type(b) and a == b else [path]


def _under(path: str, touch: str) -> bool:
    return path == touch or path.startswith((f"{touch}.", f"{touch}["))


def _diff(a: bytes, b: bytes) -> list[int]:
    if len(a) != len(b):
        raise TamperError(f"size {len(b)}, base {len(a)}")
    return [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]


def _offsets(recipe: Recipe, size: int) -> list[int]:
    """The recipe's payload_bytes as offsets into a payload of ``size`` bytes."""
    if any(not -size <= i < size for i in recipe.payload_bytes):
        raise TamperError(f"a {size}-byte payload has no bytes {recipe.payload_bytes}")
    return sorted(i % size for i in recipe.payload_bytes)


def _segment_chunks(manifest: bytes, payload: bytes) -> list[tuple[Any, bytes]]:
    """(segment record, its ciphertext bytes), in manifest order."""
    integrity = _integrity(json.loads(manifest))
    sizes = [enc for _, enc in deks.segment_sizes(integrity)]
    if sum(sizes) != len(payload):
        raise TamperError(f"segments {sizes} do not fill {len(payload)} bytes")
    out: list[tuple[Any, bytes]] = []
    at = 0
    for seg, size in zip(integrity["segments"], sizes, strict=True):
        out.append((seg, payload[at : at + size]))
        at += size
    return out


def _check_payload(
    recipe: Recipe, manifests: tuple[bytes, bytes], payloads: tuple[bytes, bytes]
) -> None:
    a, b = payloads
    if not recipe.payload:
        if a != b:
            raise TamperError("payload changed")
    elif recipe.payload_bytes:
        diff, want = _diff(a, b), _offsets(recipe, len(a))
        if diff != want:
            raise TamperError(f"payload bytes {diff[:8]} differ; want {want}")
    else:
        if a == b:
            raise TamperError("payload unchanged")
        base = _segment_chunks(manifests[0], a)
        for seg, chunk in _segment_chunks(manifests[1], b):
            if (seg, chunk) not in base:
                raise TamperError(f"segment {seg} does not hold its base bytes")


def _check_in_place(recipe: Recipe, base: Path, out: Path) -> None:
    diff = _diff(base.read_bytes(), out.read_bytes())
    start = _payload_offset(base)
    with zipfile.ZipFile(base) as z:
        size = z.getinfo(PAYLOAD).compress_size
    want = [start + i for i in _offsets(recipe, size)]
    if diff != want:
        raise TamperError(f"bytes {diff[:8]} differ; want {want}")
    with zipfile.ZipFile(out) as z:
        if z.testzip() != PAYLOAD:
            raise TamperError("payload CRC is not stale")


def check_derived(recipe: Recipe, base: Path, out: Path) -> None:
    """Fail unless ``out`` differs from ``base`` exactly where ``recipe`` declares."""
    if recipe.container == "in-place":
        _check_in_place(recipe, base, out)
        return
    method = (
        zipfile.ZIP_DEFLATED if recipe.container == "deflate" else zipfile.ZIP_STORED
    )
    with zipfile.ZipFile(base) as zb, zipfile.ZipFile(out) as zo:
        names = [i.filename for i in zo.infolist()]
        if names != [i.filename for i in zb.infolist()]:
            raise TamperError(f"entries {names}")
        if bad := zo.testzip():
            raise TamperError(f"bad CRC for {bad}")
        if any(i.compress_type != method for i in zo.infolist()):
            raise TamperError(f"entries not compressed with method {method}")
        for name in names:
            if name not in (MANIFEST, PAYLOAD) and zb.read(name) != zo.read(name):
                raise TamperError(f"{name} changed")
        manifests = zb.read(MANIFEST), zo.read(MANIFEST)
        payloads = zb.read(PAYLOAD), zo.read(PAYLOAD)
    changed = json_changes(*(json.loads(m) for m in manifests))
    extra = [p for p in changed if not any(_under(p, t) for t in recipe.touches)]
    if extra:
        raise TamperError(f"manifest changed outside {recipe.touches}: {extra}")
    unchanged = [t for t in recipe.touches if not any(_under(p, t) for p in changed)]
    if unchanged:
        raise TamperError(f"declared change missing: {unchanged}")
    if not recipe.touches and manifests[0] != manifests[1]:
        raise TamperError("manifest text changed")
    _check_payload(recipe, manifests, payloads)


def key_stem(base: str) -> str:
    """Stem of the key files for ``base``, which also unlock what derives from it."""
    return f"tamper-{base}" if base in TAMPER_BASES else base


def base_path(scratch: Path, base: str) -> Path:
    if base in TAMPER_BASES:
        return scratch / "bases" / f"tamper-base-{base}.tdf"
    return scratch / "stage" / f"{base}.tdf"


def run(scratch: Path, keys: Keys) -> int:
    """Derive every tamper-* fixture into scratch/stage and check each one."""
    stage = scratch / "stage"
    missing = sorted(
        {
            base_path(scratch, r.base).name
            for r in RECIPES.values()
            if not base_path(scratch, r.base).is_file()
        }
    )
    if missing:
        print(f"missing bases {missing}; run `write` first", file=sys.stderr)
        return 2
    for old in stage.glob("tamper-*.tdf"):
        old.unlink()
    failed: list[str] = []
    for name, r in RECIPES.items():
        base, out = base_path(scratch, r.base), stage / f"{name}.tdf"
        try:
            r.apply(base, out, keys)
            check_derived(r, base, out)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as e:
            out.unlink(missing_ok=True)
            failed.append(f"{name}: {e!r}")
            continue
        print(f"ok   {name} (from {base.name}; {', '.join(_changes(r))})")
    for f in failed:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"{len(RECIPES) - len(failed)}/{len(RECIPES)} tamper fixtures in {stage}")
    return 1 if failed else 0


def _changes(r: Recipe) -> list[str]:
    out = list(r.touches)
    if r.payload:
        out.append(PAYLOAD)
    if r.container != "stored":
        out.append(f"container: {r.container}")
    return out or ["unchanged"]
