"""Generate the DSPX-5520 shared assertion conformance vectors.

Run from ``xtest/``::

    uv run python -m vectors.generate_assertion_vectors          # rewrite
    uv run python -m vectors.generate_assertion_vectors --check  # compare only

``assertions-phase0.json`` next to this file is the source of truth for the
ZTDF assertions contract (DSPX-5519) Phase 0 vectors. The Go, Java, and JS
SDKs vendor byte-identical copies and run every vector in their unit tests,
so never edit the JSON by hand: change this generator and regenerate.

Output is deterministic. The two RSA-2048 keys in ``keys/`` were generated
once and are committed; never regenerate them, or every signature changes.
They are test-only, like the HMAC secrets below. RSA PKCS #1 v1.5 and HMAC
signatures are deterministic, and the self-signed certificates have fixed
names, serials, and dates.

Vector kinds, each with ``name``, ``kind``, ``status``, ``note``, exactly one
of ``input`` (JSON text) and ``inputBase64`` (bytes that are not UTF-8), and
``expect``:

``assertion``
    One assertion wire object. Parse it under spec Section 3, check its id
    (3.3), and hash it (4.1). ``expect`` is ``assertionHash`` or ``reason``.
``manifest``
    A manifest, possibly minimal. Only the manifest-level Section 3 parse
    step. ``expect`` is ``ok`` or ``reason``.
``binding``
    One assertion wire object. Only the binding form (5.1). ``expect`` is
    ``bindingForm`` or ``reason``.
``verify``
    One assertion and an already-selected key (``selectedKey``, from
    ``keys``; ``keySource`` ``configured`` or ``payload``), the decoded
    aggregate hash (``aggregateHashBase64``), and the legacy-encoding
    decision (``legacy``). Section 8 steps 3.3 to 3.9. ``expect`` is ``ok``
    or ``reason``.

``status: proposed`` vectors cover rules the spec marks Proposed. Run them,
but report a mismatch instead of failing on it.
"""

import argparse
import base64
import hashlib
import hmac
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import rfc8785
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

import assertions

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "assertions-phase0.json"

FORMAT = "opentdf-assertion-vectors/1"
SOURCE = "opentdf/tests xtest/vectors/assertions-phase0.json (DSPX-5520)"

#### KEY MATERIAL


def _private_key(name: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(
        (HERE / "keys" / f"{name}.pem").read_bytes(), password=None
    )
    assert isinstance(key, rsa.RSAPrivateKey) and key.key_size == 2048, name
    return key


def _public_pem(key: rsa.RSAPrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_uint(n: int) -> str:
    return b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))


#: The key that key selection chose for most verify vectors.
SIGNER = _private_key("rsa-signer")
#: An unrelated RSA key that is never selected.
OTHER = _private_key("rsa-other")
#: A configured HS256 shared secret and a payload key (DEK), as raw bytes.
CONFIGURED_SECRET = hashlib.sha256(b"DSPX-5520 vectors: configured HS256").digest()
PAYLOAD_KEY = hashlib.sha256(b"DSPX-5520 vectors: payload key").digest()

KEYS: dict[str, dict[str, str]] = {
    "rsa-signer": {"alg": "RS256", "publicKeyPem": _public_pem(SIGNER)},
    "rsa-other": {"alg": "RS256", "publicKeyPem": _public_pem(OTHER)},
    "hs256-configured": {"alg": "HS256", "secretBase64": _b64(CONFIGURED_SECRET)},
    "hs256-payload-key": {"alg": "HS256", "secretBase64": _b64(PAYLOAD_KEY)},
}


def _self_signed_certificate(key: rsa.RSAPrivateKey, name: str, serial: int) -> str:
    """Base64 DER of a fixed self-signed leaf, as an ``x5c`` entry."""
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2036, 1, 1, tzinfo=UTC))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    return _b64(certificate.public_bytes(serialization.Encoding.DER))


SIGNER_CERT = _self_signed_certificate(SIGNER, "DSPX-5520 vector signer", 0x55200001)
OTHER_CERT = _self_signed_certificate(OTHER, "DSPX-5520 vector other key", 0x55200002)


def rsa_jwk(key: rsa.RSAPrivateKey, **extra: Any) -> dict[str, Any]:
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    } | extra


def rsa_thumbprint(key: rsa.RSAPrivateKey) -> str:
    """RFC 7638 SHA-256 JWK thumbprint."""
    jwk = rsa_jwk(key)
    required = {m: jwk[m] for m in ("e", "kty", "n")}
    return b64url(hashlib.sha256(rfc8785.dumps(required)).digest())


def _segment_tag(label: str) -> bytes:
    return hashlib.sha256(label.encode("ascii")).digest()[:16]


#: Two 16-byte GMAC segment tags, decoded and concatenated.
AGGREGATE = _segment_tag("segment 0") + _segment_tag("segment 1")
OTHER_AGGREGATE = _segment_tag("segment 0, changed") + _segment_tag("segment 1")
#: Under the legacy encoding each decoded segment hash is ASCII hex text.
LEGACY_AGGREGATE = (
    hashlib.sha256(b"segment 0").hexdigest() + hashlib.sha256(b"segment 1").hexdigest()
).encode("ascii")

#### JSON TEXT
#
# Vectors need JSON that a dict cannot hold (duplicate names, escapes, exact
# number spellings), so inputs are built as text.


class Raw(str):
    """JSON text spliced in verbatim."""


class Obj:
    """A JSON object as ordered (name, value) pairs. Names may repeat."""

    def __init__(self, *pairs: tuple[str, Any]) -> None:
        self.pairs = list(pairs)

    def plus(self, *pairs: tuple[str, Any]) -> Obj:
        return Obj(*self.pairs, *pairs)

    def without(self, *names: str) -> Obj:
        return Obj(*((k, v) for k, v in self.pairs if k not in names))

    def put(self, name: str, value: Any) -> Obj:
        """Replace the value of ``name`` in place."""
        assert any(k == name for k, _ in self.pairs), name
        return Obj(*((k, value if k == name else v) for k, v in self.pairs))

    def rename(self, name: str, new: str) -> Obj:
        assert any(k == name for k, _ in self.pairs), name
        return Obj(*((new if k == name else k, v) for k, v in self.pairs))

    def after(self, name: str, *pairs: tuple[str, Any]) -> Obj:
        """Insert ``pairs`` right after member ``name``."""
        out: list[tuple[str, Any]] = []
        for k, v in self.pairs:
            out.append((k, v))
            if k == name:
                out.extend(pairs)
        assert len(out) == len(self.pairs) + len(pairs), name
        return Obj(*out)


def text(value: Any) -> str:
    match value:
        case Raw():
            return str(value)
        case Obj():
            return "{" + ",".join(f"{_name(k)}:{text(v)}" for k, v in value.pairs) + "}"
        case dict():
            return text(Obj(*value.items()))
        case list():
            return "[" + ",".join(text(v) for v in value) + "]"
        case float():
            raise TypeError("spell numbers out with Raw")
        case _:
            return json.dumps(value, ensure_ascii=False)


def _name(name: str) -> str:
    return str(name) if isinstance(name, Raw) else json.dumps(name, ensure_ascii=False)


# JSON escapes are built from code points rather than spelled in this source,
# so that no tool between an editor and the interpreter can decode them.
BACKSLASH = chr(0x5C)


def esc(*units: int) -> str:
    """JSON text of a backslash-u escape for each UTF-16 code unit."""
    return "".join(f"{BACKSLASH}u{unit:04x}" for unit in units)


def esc_non_ascii(s: str) -> str:
    """``s`` with every non-ASCII character as backslash-u escapes."""
    out = []
    for c in s:
        if ord(c) < 0x80:
            out.append(c)
            continue
        units = c.encode("utf-16-be")
        out.append(
            esc(*(int.from_bytes(units[i : i + 2]) for i in range(0, len(units), 2)))
        )
    return "".join(out)


def quoted(*parts: str) -> Raw:
    """A JSON string literal from already-escaped ``parts``."""
    return Raw('"' + "".join(parts) + '"')


GRINNING = chr(0x1F600)
GRINNING_ESCAPED = esc(0xD83D, 0xDE00)
LONG_S = chr(0x17F)


#### ASSERTIONS

SCHEMA = "urn:nato:stanag:5636:A:1:elements:json"
POLICY_ID = "62c76c68-d73d-4628-8ccc-4c1e18118c22"

#: Spec 4.4 anchor hashes.
EXAMPLE_STRING_HASH = "456d05d6a3f48a14aeee20c8d5f0429d07e5be3f1695fcec2dbc755cd9d64495"
EXAMPLE_EXTENSION_HASH = (
    "a7347ff1c718c0ee7e88558de64389d5e7194990eb6c78662d0bcd9cfb19c7ba"
)
EXAMPLE_OBJECT_HASH = "46853cb52912fd76f3ff90df3936158ee220b8e5973c5d02bb6e50f468596fba"
#: Spec 4.4: the extension example as JS hashes it today, and the object
#: example as Go hashes it today. Bindings over these must not verify.
JS_TODAY_EXTENSION_HASH = (
    "9abbc3e574a9f90e45d45537631c6aef826ea9e675515eb6a4044a1ee26ea30f"
)
GO_TODAY_OBJECT_HASH = (
    "885390e1d3bd0263409a7d7c620c169afcc27861019677eb806cd4da482d2b93"
)

EXAMPLE_VALUE = (
    f'{{"ocl":{{"pol":"{POLICY_ID}","cls":"SECRET","dcr":"2024-10-21T20:47:36Z"}}}}'
)


def statement(value: Any = EXAMPLE_VALUE) -> Obj:
    return Obj(("format", "json+stanag5636"), ("schema", SCHEMA), ("value", value))


def example(st: Any = None) -> Obj:
    """Spec 4.4 first example, in writer member order, without binding."""
    return Obj(
        ("id", "classification"),
        ("type", "handling"),
        ("scope", "payload"),
        ("appliesToState", "unencrypted"),
        ("statement", statement() if st is None else st),
    )


def acp240_value(cls: str = "CONFIDENTIAL") -> Obj:
    return Obj(
        ("@context", Obj(("@base", SCHEMA))),
        (
            "ocl",
            Obj(
                ("pol", POLICY_ID),
                ("cls", cls),
                (
                    "catl",
                    [Obj(("type", "P"), ("name", "Releasable To"), ("vals", ["USA"]))],
                ),
                ("dcr", "2026-11-06T12:00:00Z"),
            ),
        ),
    )


def acp240(value: Any = None) -> Obj:
    """The ACP 240-style assertion of spec 2.2, without binding."""
    return Obj(
        ("id", "3f1c2d9e-8a4b-4c6d-9e0f-1a2b3c4d5e6f"),
        ("type", "handling"),
        ("scope", "payload"),
        ("appliesToState", "encrypted"),
        (
            "statement",
            Obj(
                ("format", "json-structured"),
                ("schema", SCHEMA),
                ("value", acp240_value() if value is None else value),
            ),
        ),
    )


def extension(value: Any) -> Obj:
    """The first example plus an unmodelled ``extensions`` member."""
    return example().plus(("extensions", value))


#### BINDINGS

Signer = rsa.RSAPrivateKey | bytes


def _segment(value: Any) -> str:
    return b64url(text(value).encode("utf-8"))


def _signature(signing_input: bytes, signer: Signer) -> bytes:
    if isinstance(signer, bytes):
        return hmac.new(signer, signing_input, hashlib.sha256).digest()
    return signer.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())


def jws(
    header: Any,
    claims: Any,
    signer: Signer,
    *,
    header_segment: str | None = None,
    payload_segment: str | None = None,
) -> str:
    h = _segment(header) if header_segment is None else header_segment
    p = _segment(claims) if payload_segment is None else payload_segment
    return f"{h}.{p}.{b64url(_signature(f'{h}.{p}'.encode('ascii'), signer))}"


def bound_claims(
    unbound: str,
    aggregate: bytes = AGGREGATE,
    legacy: bool = False,
    hash_hex: str | None = None,
) -> dict[str, str]:
    """The ``assertionHash`` and ``assertionSig`` claims for ``unbound`` text."""
    h = assertions.assertion_hash(unbound) if hash_hex is None else hash_hex
    return {
        "assertionHash": h,
        "assertionSig": assertions.bound_assertion_sig(aggregate, h, legacy),
    }


def binding(token: Any, method: str | None = "jws") -> Obj:
    if method is None:
        return Obj(("signature", token))
    return Obj(("method", method), ("signature", token))


def bound(a: Obj, b: Any) -> str:
    """``a`` with ``binding`` ``b`` appended, as text."""
    return text(a.plus(("binding", b)))


def token_for(
    a: Obj,
    *,
    signer: Signer = SIGNER,
    alg: str = "RS256",
    header: dict[str, Any] | None = None,
    aggregate: bytes = AGGREGATE,
    legacy: bool = False,
    claims: Any = None,
) -> str:
    """A binding JWS for ``a`` (whose binding is ignored)."""
    if claims is None:
        claims = bound_claims(text(a), aggregate, legacy)
    return jws({"alg": alg} | (header or {}), claims, signer)


def signed(a: Obj, *, method: str | None = "jws", **kwargs: Any) -> str:
    """``a`` with a binding, by default an RS256 JWS from the selected key."""
    return bound(a, binding(token_for(a, **kwargs), method))


EXAMPLE_TOKEN = token_for(example())


def _strip_js_excluded(value: Any) -> Any:
    """What the old JS hash kept: every depth minus five member names."""
    excluded = ("binding", "hash", "sign", "verify", "signingKey")
    match value:
        case dict():
            return {
                k: _strip_js_excluded(v) for k, v in value.items() if k not in excluded
            }
        case list():
            return [_strip_js_excluded(v) for v in value]
        case _:
            return value


def old_js_hash(raw: str) -> str:
    """The hash the old JS writer computed, which skipped names at any depth."""
    stripped = _strip_js_excluded(assertions.parse_assertion(raw))
    return hashlib.sha256(rfc8785.dumps(stripped)).hexdigest()


def stringified_value_hash(raw: str) -> str:
    """The hash of a typed re-serialization with an object value stringified.

    This is Go's current reader: it turns an object ``statement.value`` into
    a string with sorted keys, then hashes its own struct.
    """
    a = assertions.parse_assertion(raw)
    a.pop("binding", None)
    a["statement"]["value"] = json.dumps(
        a["statement"]["value"], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rfc8785.dumps(a)).hexdigest()


#### VECTORS

Vector = dict[str, Any]
Status = Literal["required", "proposed"]


def _record(
    kind: str, name: str, note: str, raw: str | bytes, status: Status
) -> Vector:
    assert "\n" not in note, name
    record: Vector = {
        "name": f"{kind}-{name}",
        "kind": kind,
        "status": status,
        "note": note,
    }
    if isinstance(raw, bytes):
        try:
            raw.decode("utf-8")
            raise AssertionError(f"{name}: inputBase64 is only for non-UTF-8 input")
        except UnicodeDecodeError:
            pass
        record["inputBase64"] = _b64(raw)
    else:
        # Lone surrogates must be spelled as escapes inside the JSON text; a
        # raw one cannot be carried as UTF-8 by the vector file itself.
        assert not any(0xD800 <= ord(c) <= 0xDFFF for c in raw), name
        record["input"] = raw
    return record


class Vectors:
    def __init__(self) -> None:
        self.vectors: list[Vector] = []

    def _add(self, record: Vector) -> None:
        assert all(v["name"] != record["name"] for v in self.vectors), record["name"]
        self.vectors.append(record)

    def assertion(
        self,
        name: str,
        note: str,
        raw: str | bytes,
        *,
        reason: str | None = None,
        expect_hash: str | None = None,
        status: Status = "required",
    ) -> str | None:
        """Add an assertion vector; returns the hash when one is expected."""
        record = _record("assertion", name, note, raw, status)
        if reason is not None:
            record["expect"] = {"reason": reason}
            self._add(record)
            return None
        assert isinstance(raw, str)
        assertions.assertion_id(assertions.parse_assertion(raw))
        h = assertions.assertion_hash(raw)
        assert expect_hash in (None, h), f"{name}: {h} != {expect_hash}"
        record["expect"] = {"assertionHash": h}
        self._add(record)
        return h

    def manifest(
        self, name: str, note: str, raw: str | bytes, *, reason: str | None = None
    ) -> None:
        record = _record("manifest", name, note, raw, "required")
        record["expect"] = {"ok": True} if reason is None else {"reason": reason}
        self._add(record)

    def binding(
        self, name: str, note: str, b: Any, *, reason: str | None = None
    ) -> None:
        raw = text(example()) if b is _MISSING else bound(example(), b)
        record = _record("binding", name, note, raw, "required")
        record["expect"] = (
            {"bindingForm": "jws"} if reason is None else {"reason": reason}
        )
        self._add(record)

    def verify(
        self,
        name: str,
        note: str,
        raw: str,
        *,
        key: str = "rsa-signer",
        source: Literal["configured", "payload"] = "configured",
        aggregate: bytes = AGGREGATE,
        legacy: bool = False,
        reason: str | None = None,
    ) -> None:
        assert key in KEYS, key
        assert (source == "payload") == (key == "hs256-payload-key"), name
        record = _record("verify", name, note, raw, "required")
        record |= {
            "selectedKey": key,
            "keySource": source,
            "aggregateHashBase64": _b64(aggregate),
            "legacy": legacy,
            "expect": {"ok": True} if reason is None else {"reason": reason},
        }
        self._add(record)


_MISSING = object()


def _with_bad_bytes(raw: str, bad: bytes) -> bytes:
    marker = "@@BYTES@@"
    assert raw.count(marker) == 1
    return raw.encode("utf-8").replace(marker.encode("ascii"), bad)


# RFC 8785 Section 3.2.2 and 3.2.3 samples, as JSON text.
RFC8785_SAMPLE = (
    '{"numbers":[333333333.33333329,1E30,4.50,2e-3,0.000000000000000000000000001],'
    + '"string":'
    + quoted(
        esc(0x20AC),
        "$",
        esc(0x000F, 0x000A),
        "A'",
        esc(0x0042, 0x0022, 0x005C),
        BACKSLASH * 2,
        BACKSLASH + '"',
        BACKSLASH + "/",
    )
    + ',"literals":[null,true,false]}'
)
#: Its canonical form, from the RFC.
RFC8785_SAMPLE_CANONICAL = (
    '{"literals":[null,true,false],'
    '"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
    '"string":"'
    + chr(0x20AC)
    + "$"
    + esc(0x000F)
    + BACKSLASH
    + "nA'B"
    + BACKSLASH
    + '"'
    + BACKSLASH * 4
    + BACKSLASH
    + '"/"}'
)
RFC8785_SORT_SAMPLE = (
    "{"
    + ",".join(
        f"{name}:{json.dumps(value)}"
        for name, value in [
            (quoted(esc(0x20AC)), "Euro Sign"),
            (quoted(BACKSLASH + "r"), "Carriage Return"),
            (quoted(esc(0xFB33)), "Hebrew Letter Dalet With Dagesh"),
            (quoted("1"), "One"),
            (quoted(GRINNING_ESCAPED), "Emoji: Grinning Face"),
            (quoted(esc(0x0080)), "Control"),
            (quoted(esc(0x00F6)), "Latin Small Letter O With Diaeresis"),
        ]
    )
    + "}"
)
#: The order RFC 8785 3.2.3 gives for those names.
RFC8785_SORTED_NAMES = [
    "\r",
    "1",
    chr(0x80),
    chr(0xF6),
    chr(0x20AC),
    GRINNING,
    chr(0xFB33),
]

#: The STANAG 5636 label from xtest/fixtures/assertions.py.
FIXTURE_LABEL = (
    f'{{"ocl":{{"pol":"{POLICY_ID}","cls":"SECRET","catl":[{{"type":"P",'
    '"name":"Releasable To","vals":["usa"]}],"dcr":"2024-10-21T20:47:36Z"},'
    f'"context":{{"@base":"{SCHEMA}"}}}}'
)


def assertion_vectors(v: Vectors) -> None:
    a = v.assertion

    # Spec 4.4 worked examples, and spellings that must hash identically.
    a(
        "worked-example-string-value",
        "Spec 4.4 first example as a writer emits it, with its binding",
        signed(example()),
        expect_hash=EXAMPLE_STRING_HASH,
    )
    a(
        "worked-example-unmodelled-extension",
        "Spec 4.4 second example: an unmodelled member is hashed",
        signed(extension(Obj(("hash", "deadbeef"), ("note", "coi")))),
        expect_hash=EXAMPLE_EXTENSION_HASH,
    )
    a(
        "worked-example-acp240-object-value",
        "Spec 4.4 third example: ACP 240 label as an object value, JWS binding",
        signed(acp240()),
        expect_hash=EXAMPLE_OBJECT_HASH,
    )
    a(
        "no-binding-member",
        "The hash input never includes a binding, so none is needed",
        text(example()),
        expect_hash=EXAMPLE_STRING_HASH,
    )
    a(
        "binding-not-an-object",
        "Only the top-level binding is removed, whatever its type",
        bound(example(), "not-an-object"),
        expect_hash=EXAMPLE_STRING_HASH,
    )
    pretty = json.dumps(
        {
            "binding": {"signature": EXAMPLE_TOKEN, "method": "jws"},
            "statement": {
                "value": EXAMPLE_VALUE,
                "schema": SCHEMA,
                "format": "json+stanag5636",
            },
            "appliesToState": "unencrypted",
            "scope": "payload",
            "type": "handling",
            "id": "classification",
        },
        indent="\t",
    ).replace("\n", "\r\n")
    a(
        "whitespace-and-member-order",
        "Insignificant whitespace and member order do not change the hash",
        f"\r\n {pretty} \n",
        expect_hash=EXAMPLE_STRING_HASH,
    )
    a(
        "escaped-id",
        "An id spelled with an escape is the decoded string classification",
        text(example().put("id", quoted("classif", esc(0x69), "cation"))),
        expect_hash=EXAMPLE_STRING_HASH,
    )
    escaped_value = json.dumps(EXAMPLE_VALUE).replace(
        BACKSLASH + '"ocl' + BACKSLASH + '"', esc(0x22) + "ocl" + esc(0x22)
    )
    a(
        "escaped-names-and-values",
        "Escaped member names and strings hash as their decoded text",
        text(
            Obj(
                (quoted(esc(0x69), "d"), "classification"),
                ("type", quoted("handl", esc(0x69), "ng")),
                (quoted("sc", esc(0x6F), "pe"), "payload"),
                ("appliesToState", "unencrypted"),
                (
                    "statement",
                    Obj(
                        ("format", quoted("json", esc(0x2B), "stanag5636")),
                        ("schema", quoted(SCHEMA.replace(":", esc(0x3A)))),
                        ("value", Raw(escaped_value)),
                    ),
                ),
            )
        ),
        expect_hash=EXAMPLE_STRING_HASH,
    )

    # Unmodelled and reserved-looking members are all hashed.
    a(
        "unmodelled-top-level-member",
        "An unmodelled top-level member is part of the hash",
        signed(example().plus(("handlingCaveat", "TEST-CAVEAT"))),
    )
    a(
        "unmodelled-statement-member",
        "An unmodelled statement member is part of the hash",
        signed(example(statement().plus(("encoding", "utf-8")))),
    )
    a(
        "reserved-names-in-statement",
        "hash, binding, signingKey, sign, and verify inside statement are hashed",
        signed(
            example(
                statement().plus(
                    ("hash", EXAMPLE_STRING_HASH),
                    ("binding", Obj(("method", "jws"), ("signature", "e30.e30.c2ln"))),
                    ("signingKey", Obj(("alg", "HS256"), ("key", "placeholder"))),
                    ("sign", "yes"),
                    ("verify", False),
                )
            )
        ),
    )
    a(
        "reserved-names-in-object-value",
        "hash, binding, signingKey, sign, and verify inside statement.value are hashed",
        signed(
            acp240(
                acp240_value().plus(
                    ("hash", "deadbeef"),
                    ("binding", Obj(("signature", "e30.e30.c2ln"))),
                    (
                        "meta",
                        Obj(
                            ("signingKey", "k"), ("sign", Raw("1")), ("verify", [True])
                        ),
                    ),
                )
            )
        ),
    )
    a(
        "reserved-names-in-extension",
        "hash, binding, signingKey, sign, and verify inside an extension are hashed",
        signed(
            extension(
                Obj(
                    ("binding", Obj(("hash", "deadbeef"))),
                    ("signingKey", Obj(("alg", "RS256"), ("key", "placeholder"))),
                    ("sign", Obj(("verify", "x"))),
                )
            )
        ),
    )
    a(
        "top-level-signing-key-member",
        "A top-level signingKey is hashed; only binding is removed",
        signed(
            example().plus(
                ("signingKey", Obj(("alg", "HS256"), ("key", "placeholder")))
            )
        ),
    )
    a(
        "top-level-hash-member",
        "A top-level hash member is hashed; only binding is removed",
        signed(example().plus(("hash", EXAMPLE_STRING_HASH))),
    )
    label = Obj(
        ("id", "424ff3a3-50ca-4f01-a2ae-ef851cd3cac0"),
        ("type", "handling"),
        ("scope", "tdo"),
        ("appliesToState", "encrypted"),
    )
    a(
        "stanag-label-string-value",
        "The xtest STANAG 5636 label as a string value",
        signed(label.plus(("statement", statement(FIXTURE_LABEL)))),
    )
    a(
        "stanag-label-object-value",
        "The same STANAG 5636 label as an object value, which hashes differently",
        signed(label.plus(("statement", statement(Raw(FIXTURE_LABEL))))),
    )

    # JCS number formatting (RFC 8785 3.2.2.3): every number is a double.
    numbers = {
        "integers": (
            "integers and negative zero",
            "[0,-0,1,-1,42,-42,1000000,9007199254740991,-9007199254740991]",
        ),
        "decimals": (
            "decimals, trailing zeros, and small fractions",
            "[0.0,-0.0,0.1,0.5,1.5,-2.25,100.0,4.50,123.456,0.000001,0.0000001,"
            "333333333.33333329]",
        ),
        "exponents": (
            "exponent spellings and the 1e21 and 1e-7 switch points",
            "[1e0,1E3,1e+3,1E-3,2e-3,1e20,1e21,1E30,1e-6,1e-7,1.5e300,-1.5e-300,"
            "5e-324,1.7976931348623157e308,0.000000000000000000000000001]",
        ),
        "beyond-double-precision": (
            "digits beyond double precision round to the nearest double",
            "[9007199254740992,9007199254740993,9007199254740994,"
            "123456789012345678901234567890,0.1000000000000000055511151231257827,"
            "0.30000000000000004,1e23]",
        ),
    }
    for name, (note, literal) in numbers.items():
        a(
            f"numbers-{name}",
            f"JCS number form in an extension: {note}",
            signed(extension(Obj(("n", Raw(literal))))),
        )
    a(
        "numbers-in-object-value",
        "JCS number form inside an object statement.value",
        signed(
            acp240(
                acp240_value().plus(
                    ("version", Raw("1.0")),
                    ("weights", Raw("[1E2,-0,0.25e1,1e-7]")),
                )
            )
        ),
    )
    a(
        "rfc8785-sample-object",
        "RFC 8785 Section 3.2.2 sample: numbers, escapes, and literals",
        signed(extension(Raw(RFC8785_SAMPLE))),
    )

    # Strings and member names.
    literal_text = (
        "".join(
            chr(c)
            for c in (
                0xDC,
                0x6E,
                0xEF,
                0x63,
                0xF6,
                0x64,
                0xE9,
                0x20,
                0x4E2D,
                0x6587,
                0x20,
            )
        )
        + GRINNING
    )
    h_literal = a(
        "non-ascii-literal",
        "Literal non-ASCII text, including a character outside the BMP",
        signed(example(statement(literal_text))),
    )
    a(
        "non-ascii-escaped",
        "The same text with escapes, including a surrogate pair, hashes the same",
        signed(example(statement(quoted(esc_non_ascii(literal_text))))),
        expect_hash=h_literal,
    )
    escapes = [esc(0x0000), *(BACKSLASH + c for c in 'bfnrt"' + BACKSLASH + "/")]
    escapes += [esc(0x001F), esc(0x007F), esc(0x2028), esc(0x2029), esc(0x00E9)]
    a(
        "string-escapes",
        "JCS escapes only control characters, quote, and backslash",
        signed(example(statement(quoted(*escapes)))),
    )
    a(
        "keys-sorted-by-utf16-code-units",
        "RFC 8785 3.2.3: keys sort by UTF-16 code units, so U+1F600 precedes U+FB33",
        signed(extension(Raw(RFC8785_SORT_SAMPLE))),
    )
    a(
        "surrogate-pair-in-member-name",
        "An escaped surrogate pair is one valid code point, in a name or a value",
        signed(
            extension(
                Obj(
                    (quoted(GRINNING_ESCAPED), quoted(GRINNING_ESCAPED)),
                    (GRINNING + "x", "literal"),
                )
            )
        ),
    )

    # The id is exact.
    a(
        "id-surrounding-whitespace",
        "id is not trimmed: surrounding whitespace is part of the id and the hash",
        signed(example().put("id", " classification ")),
    )
    a(
        "id-non-ascii",
        "A non-ASCII id is hashed as its code points",
        signed(
            example().put(
                "id", "classification-" + chr(0x5206) + chr(0x7C7B) + "-" + chr(0xE9)
            )
        ),
    )

    # Case variants that the contract does not reserve.
    a(
        "case-variants-inside-object-value-allowed",
        "Names inside statement.value are application content, not checked",
        signed(
            acp240(
                acp240_value().plus(
                    ("id", "a"),
                    ("ID", "b"),
                    ("Statement", "c"),
                    ("Binding", Obj(("Signature", "d"))),
                )
            )
        ),
    )
    a(
        "case-variants-inside-extension-allowed",
        "Names inside unmodelled members are not checked",
        signed(
            extension(
                Obj(
                    ("id", Raw("1")),
                    ("ID", Raw("2")),
                    ("Type", "x"),
                    ("BINDING", True),
                    ("Assertions", []),
                )
            )
        ),
    )
    a(
        "unmodelled-name-case-pair-allowed",
        "extensions and Extensions are both unmodelled, so both are hashed",
        signed(
            example().plus(
                ("extensions", Obj(("a", Raw("1")))),
                ("Extensions", Obj(("a", Raw("2")))),
            )
        ),
    )
    a(
        "statement-names-at-assertion-level-allowed",
        "Format, Schema, and Value are modelled only inside statement",
        signed(example().plus(("Format", "x"), ("Schema", "y"), ("Value", "z"))),
    )
    a(
        "assertion-names-in-statement-allowed",
        "ID, Type, and Binding are modelled only at the assertion level",
        signed(example(statement().plus(("ID", "x"), ("Type", "y"), ("Binding", "z")))),
    )
    a(
        "dotless-i-not-a-case-variant",
        "U+0131 does not fold to i under the contract rule, so this name is unmodelled",
        signed(example().after("id", (chr(0x131) + "d", "system-metadata"))),
    )
    a(
        "dotted-capital-i-not-a-case-variant",
        "U+0130 does not fold to i under the contract rule, so this name is unmodelled",
        signed(example().after("id", (chr(0x130) + "d", "system-metadata"))),
    )
    a(
        "ligature-st-not-a-case-variant",
        "U+FB06 is one code point, so this name is not a variant of statement",
        signed(example().plus((chr(0xFB06) + "atement", "x"))),
    )
    a(
        "unicode-normalization-distinct-names",
        "Names are not normalized: precomposed and decomposed e-acute differ",
        signed(extension(Obj((chr(0xE9), Raw("1")), ("e" + chr(0x301), Raw("2"))))),
    )

    # Duplicate member names, compared after decoding escapes.
    dup = "duplicate-member"
    a(
        "duplicate-id",
        "Two id members with different values",
        text(example().after("id", ("id", "system-metadata"))),
        reason=dup,
    )
    a(
        "duplicate-id-identical-values",
        "Two id members with the same value",
        text(example().after("id", ("id", "classification"))),
        reason=dup,
    )
    a(
        "duplicate-in-statement",
        "Two format members inside statement",
        text(example(statement().plus(("format", "json")))),
        reason=dup,
    )
    a(
        "duplicate-deep-in-object-value",
        "Two cls members deep inside an object statement.value",
        text(
            acp240(
                acp240_value().put(
                    "ocl", Obj(("cls", "SECRET"), ("cls", "UNCLASSIFIED"))
                )
            )
        ),
        reason=dup,
    )
    a(
        "duplicate-in-value-array-element",
        "Two type members in an object inside an array in statement.value",
        text(
            acp240(acp240_value().plus(("catl", [Obj(("type", "P"), ("type", "R"))])))
        ),
        reason=dup,
    )
    a(
        "duplicate-in-extension",
        "Two note members inside an unmodelled member",
        text(extension(Obj(("note", "coi"), ("note", "other")))),
        reason=dup,
    )
    a(
        "duplicate-in-binding",
        "Two signature members inside binding",
        bound(
            example(),
            Obj(
                ("method", "jws"), ("signature", EXAMPLE_TOKEN), ("signature", "x.y.z")
            ),
        ),
        reason=dup,
    )
    a(
        "duplicate-binding-member",
        "Two top-level binding members, though binding is not hashed",
        text(
            example().plus(
                ("binding", binding(EXAMPLE_TOKEN)), ("binding", binding("x.y.z"))
            )
        ),
        reason=dup,
    )
    a(
        "escaped-duplicate-id",
        "id and the escaped spelling of id are duplicates",
        text(example().after("id", (quoted(esc(0x69), "d"), "system-metadata"))),
        reason=dup,
    )
    a(
        "escaped-duplicate-solidus",
        "a/b and its escaped-solidus spelling are duplicates",
        text(
            extension(Obj(("a/b", Raw("1")), (quoted("a", BACKSLASH, "/b"), Raw("2"))))
        ),
        reason=dup,
    )
    a(
        "escaped-duplicate-surrogate-pair",
        "A literal U+1F600 name and its escaped surrogate pair are duplicates",
        text(
            extension(Obj((GRINNING, Raw("1")), (quoted(GRINNING_ESCAPED), Raw("2"))))
        ),
        reason=dup,
    )

    # Case variants of modelled names (spec 3.2) at each checked level.
    amb = "ambiguous-member"
    variants = [
        ("ID", "ID alongside id", example().after("id", ("ID", "system-metadata"))),
        (
            "Id-alias-only",
            "Id without id is ambiguous, not a missing id",
            example().rename("id", "Id"),
        ),
        (
            "escaped-ID",
            "The escaped spelling of ID alongside id",
            example().after("id", (quoted(esc(0x49), "D"), "system-metadata")),
        ),
        ("TYPE", "TYPE alongside type", example().after("type", ("TYPE", "other"))),
        ("Scope-alias-only", "Scope without scope", example().rename("scope", "Scope")),
        (
            "appliestostate",
            "appliestostate alongside appliesToState",
            example().plus(("appliestostate", "encrypted")),
        ),
        (
            "Statement",
            "Statement alongside statement",
            example().plus(("Statement", statement())),
        ),
        (
            "Binding-alias-only",
            "Binding without binding",
            example().plus(("Binding", binding(EXAMPLE_TOKEN))),
        ),
        (
            "long-s-scope",
            "U+017F folds to s, so this name is a variant of scope",
            example().plus((LONG_S + "cope", "tdo")),
        ),
        (
            "long-s-appliesToState",
            "U+017F against the uppercase S of appliesToState",
            example().plus(("appliesTo" + LONG_S + "tate", "encrypted")),
        ),
    ]
    for name, note, obj in variants:
        a(f"case-variant-{name}", note, text(obj), reason=amb)
    statement_variants = [
        (
            "Value",
            "Value alongside value in statement",
            statement().plus(("Value", "x")),
        ),
        (
            "SCHEMA-alias-only",
            "SCHEMA without schema in statement",
            statement().rename("schema", "SCHEMA"),
        ),
        (
            "long-s-schema",
            "U+017F variant of schema in statement",
            statement().plus((LONG_S + "chema", SCHEMA)),
        ),
    ]
    for name, note, st in statement_variants:
        a(f"statement-case-variant-{name}", note, text(example(st)), reason=amb)
    binding_variants = [
        (
            "Signature",
            "Signature alongside signature in binding",
            binding(EXAMPLE_TOKEN).plus(("Signature", "x.y.z")),
        ),
        (
            "Method-alias-only",
            "Method without method in binding",
            Obj(("Method", "jws"), ("signature", EXAMPLE_TOKEN)),
        ),
        ("BDO", "BDO in a JWS binding", binding(EXAMPLE_TOKEN).plus(("BDO", "x"))),
        (
            "long-s-signature",
            "U+017F variant of signature in binding",
            Obj(("method", "jws"), (LONG_S + "ignature", EXAMPLE_TOKEN)),
        ),
    ]
    for name, note, b in binding_variants:
        a(f"binding-case-variant-{name}", note, bound(example(), b), reason=amb)

    # I-JSON (spec 3.1).
    bad = "invalid-json"
    in_value = [
        (
            "lone-high-surrogate-in-value",
            "A lone high surrogate in statement.value",
            quoted(esc(0xD800)),
        ),
        (
            "reversed-surrogate-pair",
            "A low surrogate before a high surrogate",
            quoted(esc(0xDE00, 0xD83D)),
        ),
        (
            "high-surrogate-before-non-surrogate",
            "A high surrogate followed by an escaped A",
            quoted(esc(0xD800, 0x0041)),
        ),
        (
            "noncharacter-fffe-escaped",
            "The noncharacter U+FFFE, escaped",
            quoted(esc(0xFFFE)),
        ),
        (
            "noncharacter-ffff-escaped",
            "The noncharacter U+FFFF, escaped",
            quoted(esc(0xFFFF)),
        ),
        (
            "noncharacter-fdd0-escaped",
            "The noncharacter U+FDD0, escaped",
            quoted(esc(0xFDD0)),
        ),
        (
            "noncharacter-1ffff-escaped-pair",
            "The noncharacter U+1FFFF as an escaped surrogate pair",
            quoted(esc(0xD83F, 0xDFFF)),
        ),
        (
            "noncharacter-10ffff-escaped-pair",
            "The noncharacter U+10FFFF as an escaped surrogate pair",
            quoted(esc(0xDBFF, 0xDFFF)),
        ),
        (
            "noncharacter-fffe-literal",
            "The noncharacter U+FFFE as literal UTF-8",
            quoted("x", chr(0xFFFE)),
        ),
        (
            "noncharacter-1fffe-literal",
            "The noncharacter U+1FFFE as literal UTF-8",
            quoted(chr(0x1FFFE)),
        ),
    ]
    for name, note, literal in in_value:
        a(name, note, text(example(statement(literal))), reason=bad)
    a(
        "lone-low-surrogate-in-extension",
        "A lone low surrogate in an unmodelled member",
        text(extension(Obj(("note", quoted("coi", esc(0xDC00)))))),
        reason=bad,
    )
    a(
        "lone-surrogate-in-member-name",
        "A lone surrogate in a member name inside an unmodelled member",
        text(extension(Obj((quoted(esc(0xDEAD)), Raw("1"))))),
        reason=bad,
    )
    a(
        "lone-surrogate-in-top-level-member-name",
        "A lone surrogate in an unmodelled top-level member name",
        text(example().plus((quoted("x", esc(0xD800)), Raw("1")))),
        reason=bad,
    )
    a(
        "lone-surrogate-in-binding",
        "A lone surrogate inside binding, which is parsed though not hashed",
        bound(example(), binding(quoted(esc(0xDEAD)))),
        reason=bad,
    )
    a(
        "lone-surrogate-in-id",
        "A lone surrogate in id fails parsing before the id check",
        text(example().put("id", quoted("classification", esc(0xD800)))),
        reason=bad,
    )
    a(
        "noncharacter-fdef-literal-in-member-name",
        "The noncharacter U+FDEF as a literal member name",
        text(extension(Obj((chr(0xFDEF), Raw("1"))))),
        reason=bad,
    )
    for name, note, literal in [
        ("number-1e400", "1e400 is outside the double range", "1e400"),
        ("number-minus-1e400", "-1e400 is outside the double range", "-1e400"),
        (
            "number-integer-beyond-double-range",
            "A 401-digit integer is outside the double range",
            "1" + "0" * 400,
        ),
    ]:
        a(name, note, text(extension(Obj(("n", Raw(literal))))), reason=bad)
    a(
        "number-1e400-in-object-value",
        "1e400 inside an object statement.value",
        text(acp240(acp240_value().plus(("n", Raw("1e400"))))),
        reason=bad,
    )
    marked_value = text(example(statement("@@BYTES@@")))
    for name, note, raw_bytes in [
        ("invalid-utf8-byte-ff", "The byte 0xFF in statement.value", b"label\xff"),
        (
            "invalid-utf8-overlong",
            "The overlong encoding C0 AF of a solidus",
            b"\xc0\xaf",
        ),
        (
            "invalid-utf8-encoded-surrogate",
            "U+D800 encoded as UTF-8 bytes ED A0 80",
            b"\xed\xa0\x80",
        ),
        (
            "invalid-utf8-truncated-sequence",
            "A three-byte sequence cut short",
            b"\xe2\x82",
        ),
    ]:
        a(name, note, _with_bad_bytes(marked_value, raw_bytes), reason=bad)
    a(
        "invalid-utf8-in-member-name",
        "The byte 0xFE in an unmodelled member name",
        _with_bad_bytes(text(example().plus(("@@BYTES@@", Raw("1")))), b"x\xfe"),
        reason=bad,
    )

    # Not JSON at all.
    example_text = text(example())
    syntax = [
        (
            "trailing-comma",
            "A trailing comma in the assertion object",
            example_text[:-1] + ",}",
        ),
        ("nan-literal", "NaN is not a JSON value", text(extension(Raw("NaN")))),
        (
            "single-quoted-string",
            "Single-quoted strings are not JSON",
            text(extension(Raw("'coi'"))),
        ),
        (
            "leading-zero",
            "Numbers cannot have leading zeros",
            text(extension(Raw("01"))),
        ),
        (
            "raw-control-character",
            "A literal tab inside a string",
            text(example(statement(quoted("a", chr(9), "b")))),
        ),
        ("comment", "Comments are not JSON", example_text[:-1] + "/* note */}"),
        ("trailing-data", "Data after the assertion object", example_text + " {}"),
        (
            "invalid-escape",
            r"\x is not a JSON escape",
            text(example(statement(quoted(BACKSLASH, "x41")))),
        ),
    ]
    for name, note, raw in syntax:
        a(f"syntax-{name}", note, raw, reason=bad)

    # The id (spec 3.3).
    for name, note, obj in [
        ("missing", "No id member", example().without("id")),
        ("null", "id is null", example().put("id", None)),
        ("number", "id is a number", example().put("id", Raw("42"))),
        ("empty", "id is the empty string", example().put("id", "")),
        ("array", "id is an array", example().put("id", ["classification"])),
        (
            "object",
            "id is an object",
            example().put("id", Obj(("value", "classification"))),
        ),
        ("boolean", "id is a boolean", example().put("id", True)),
    ]:
        a(f"id-{name}", note, text(obj), reason="invalid-id")

    # Proposed (spec 2.2): statement must be an object with a string or
    # object value. Phase 0 readers keep their current behaviour.
    for name, note, obj in [
        (
            "statement-value-number",
            "statement.value is a number",
            example(statement(Raw("42"))),
        ),
        (
            "statement-value-boolean",
            "statement.value is a boolean",
            example(statement(True)),
        ),
        ("statement-value-null", "statement.value is null", example(statement(None))),
        (
            "statement-value-array",
            "statement.value is an array",
            example(statement(["SECRET"])),
        ),
        ("statement-string", "statement is a string", example("SECRET")),
        ("statement-null", "statement is null", example().put("statement", None)),
    ]:
        a(
            name,
            f"Proposed: {note}",
            text(obj),
            reason="invalid-statement",
            status="proposed",
        )


def _manifest(*extra: tuple[str, Any]) -> Obj:
    """A realistic ZTDF manifest without assertions, plus ``extra`` members."""
    segment_hash = _b64(_segment_tag("segment 0"))
    return Obj(
        (
            "encryptionInformation",
            Obj(
                ("type", "split"),
                (
                    "policy",
                    _b64(
                        b'{"uuid":"00000000-0000-4000-8000-000000000000","body":{"dataAttributes":[],"dissem":[]}}'
                    ),
                ),
                (
                    "keyAccess",
                    [
                        Obj(
                            ("type", "wrapped"),
                            ("url", "https://kas.example.com"),
                            ("protocol", "kas"),
                            ("wrappedKey", _b64(b"\0" * 256)),
                            (
                                "policyBinding",
                                Obj(("alg", "HS256"), ("hash", _b64(b"\0" * 32))),
                            ),
                            ("kid", "r1"),
                        )
                    ],
                ),
                (
                    "method",
                    Obj(
                        ("algorithm", "AES-256-GCM"), ("iv", ""), ("isStreamable", True)
                    ),
                ),
                (
                    "integrityInformation",
                    Obj(
                        (
                            "rootSignature",
                            Obj(("alg", "HS256"), ("sig", _b64(b"\0" * 32))),
                        ),
                        ("segmentHashAlg", "GMAC"),
                        ("segmentSizeDefault", Raw("2097152")),
                        ("encryptedSegmentSizeDefault", Raw("2097180")),
                        (
                            "segments",
                            [
                                Obj(
                                    ("hash", segment_hash),
                                    ("segmentSize", Raw("14")),
                                    ("encryptedSegmentSize", Raw("42")),
                                )
                            ],
                        ),
                    ),
                ),
            ),
        ),
        (
            "payload",
            Obj(
                ("type", "reference"),
                ("url", "0.payload"),
                ("protocol", "zip"),
                ("mimeType", "application/octet-stream"),
                ("isEncrypted", True),
            ),
        ),
        ("schemaVersion", "4.3.0"),
        *extra,
    )


def manifest_vectors(v: Vectors) -> None:
    m = v.manifest
    good = [Raw(signed(example())), Raw(signed(acp240()))]

    def with_assertion(obj: Obj | str) -> str:
        return text(
            _manifest(
                (
                    "assertions",
                    [
                        Raw(signed(example())),
                        Raw(text(obj) if isinstance(obj, Obj) else obj),
                    ],
                )
            )
        )

    m(
        "clean",
        "A manifest with two well-formed assertions",
        text(_manifest(("assertions", good))),
    )
    m("no-assertions-member", "A manifest without assertions", text(_manifest()))
    m(
        "empty-assertions",
        "A manifest with an empty assertions array",
        text(_manifest(("assertions", []))),
    )
    m(
        "case-pair-at-unchecked-level",
        "payload and Payload at the root: only assertions is modelled there",
        text(_manifest(("assertions", good), ("Payload", Obj(("type", "reference"))))),
    )
    m(
        "case-pair-in-key-access",
        "url and URL in a key access object, a level that is not checked",
        text(_manifest(("assertions", good))).replace(
            '"url":"https://kas.example.com"',
            '"url":"https://kas.example.com","URL":"https://other.example.com"',
        ),
    )
    m(
        "case-variants-in-object-value",
        "ID and Statement inside an assertion's statement.value are not checked",
        with_assertion(
            signed(acp240(acp240_value().plus(("ID", "x"), ("Statement", "y"))))
        ),
    )

    dup = "duplicate-member"
    m(
        "duplicate-root-member",
        "Two schemaVersion members at the root",
        text(_manifest(("assertions", good), ("schemaVersion", "4.3.0"))),
        reason=dup,
    )
    m(
        "duplicate-assertions-member",
        "Two assertions members at the root",
        text(_manifest(("assertions", good), ("assertions", []))),
        reason=dup,
    )
    m(
        "duplicate-deep-in-key-access",
        "Two url members inside a key access object",
        text(_manifest(("assertions", good))).replace(
            '"url":"https://kas.example.com"',
            '"url":"https://kas.example.com","url":"https://other.example.com"',
        ),
        reason=dup,
    )
    m(
        "escaped-duplicate-root-member",
        "payload and its escaped spelling at the root",
        text(
            _manifest(
                ("assertions", good),
                (quoted("p", esc(0x61), "yload"), Obj(("type", "reference"))),
            )
        ),
        reason=dup,
    )
    m(
        "duplicate-in-assertion",
        "Two id members in one assertion",
        with_assertion(
            bound(
                acp240().after("id", ("id", "classification")), binding(EXAMPLE_TOKEN)
            )
        ),
        reason=dup,
    )

    amb = "ambiguous-member"
    m(
        "assertions-and-Assertions",
        "Both assertions and Assertions at the root",
        text(_manifest(("assertions", good), ("Assertions", []))),
        reason=amb,
    )
    m(
        "Assertions-alone",
        "Assertions without assertions at the root",
        text(_manifest(("Assertions", good))),
        reason=amb,
    )
    m(
        "ASSERTIONS-alone",
        "ASSERTIONS without assertions at the root",
        text(_manifest(("ASSERTIONS", good))),
        reason=amb,
    )
    m(
        "long-s-assertions-alone",
        "A U+017F variant of assertions without assertions at the root",
        text(_manifest(("a" + LONG_S * 2 + "ertions", good))),
        reason=amb,
    )
    m(
        "ID-variant-in-assertion",
        "ID alongside id in one assertion",
        with_assertion(
            bound(
                acp240().after("id", ("ID", "system-metadata")), binding(EXAMPLE_TOKEN)
            )
        ),
        reason=amb,
    )
    m(
        "Id-alias-only-in-assertion",
        "Id without id in one assertion",
        with_assertion(bound(acp240().rename("id", "Id"), binding(EXAMPLE_TOKEN))),
        reason=amb,
    )
    m(
        "statement-variant-in-assertion",
        "Value alongside value in an assertion's statement",
        with_assertion(
            bound(example(statement().plus(("Value", "x"))), binding(EXAMPLE_TOKEN))
        ),
        reason=amb,
    )
    m(
        "binding-variant-in-assertion",
        "Signature alongside signature in an assertion's binding",
        with_assertion(
            bound(example(), binding(EXAMPLE_TOKEN).plus(("Signature", "x.y.z")))
        ),
        reason=amb,
    )

    bad = "invalid-json"
    m(
        "lone-surrogate-in-assertion",
        "A lone surrogate in an assertion's statement.value",
        with_assertion(text(example(statement(quoted(esc(0xDEAD)))))),
        reason=bad,
    )
    m(
        "noncharacter-in-assertion",
        "The noncharacter U+FFFF in an assertion member name",
        with_assertion(text(extension(Obj((quoted(esc(0xFFFF)), Raw("1")))))),
        reason=bad,
    )
    m(
        "out-of-range-number-in-assertion",
        "1e400 in an assertion's unmodelled member",
        with_assertion(text(extension(Obj(("n", Raw("1e400")))))),
        reason=bad,
    )
    m(
        "invalid-utf8-in-assertion",
        "The byte 0xFF in an assertion's statement.value",
        _with_bad_bytes(with_assertion(text(example(statement("@@BYTES@@")))), b"\xff"),
        reason=bad,
    )


def binding_vectors(v: Vectors) -> None:
    b = v.binding
    t = EXAMPLE_TOKEN
    bdo = "PEJpbmRpbmdJbmZvcm1hdGlvbi8+"
    b("jws", "method jws with a signature", binding(t))
    b("JWS-uppercase", "method JWS, which Java writers emit", binding(t, "JWS"))
    b("method-missing", "A missing method means jws", binding(t, None))

    unsupported = "unsupported-binding"
    b(
        "method-mixed-case",
        "Jws is neither jws nor JWS",
        binding(t, "Jws"),
        reason=unsupported,
    )
    b("method-unknown", "An unknown method", binding(t, "xmldsig"), reason=unsupported)
    b(
        "method-empty-string",
        "An empty method string",
        binding(t, ""),
        reason=unsupported,
    )
    b(
        "bdo-object-alone",
        "A STANAG 4778 binding object as an object",
        Obj(("bdo", Obj(("BindingInformation", Obj())))),
        reason=unsupported,
    )
    b(
        "bdo-string-alone",
        "A STANAG 4778 binding object as a string",
        Obj(("bdo", bdo)),
        reason=unsupported,
    )
    b(
        "bdo-with-method-jws",
        "bdo without signature is a binding object whatever method says",
        Obj(("method", "jws"), ("bdo", bdo)),
        reason=unsupported,
    )

    invalid = "invalid-binding"
    b(
        "both-forms",
        "signature and bdo together",
        binding(t).plus(("bdo", bdo)),
        reason=invalid,
    )
    b("empty-object", "binding is an empty object", Obj(), reason=invalid)
    b(
        "method-only",
        "Neither signature nor bdo",
        Obj(("method", "jws")),
        reason=invalid,
    )
    b("missing", "No binding member", _MISSING, reason=invalid)
    b("string", "binding is a string", t, reason=invalid)
    b("null", "binding is null", None, reason=invalid)
    b("array", "binding is an array", [binding(t)], reason=invalid)
    b(
        "method-number",
        "method is a number",
        Obj(("method", Raw("1")), ("signature", t)),
        reason=invalid,
    )
    b(
        "method-null",
        "method is null",
        Obj(("method", None), ("signature", t)),
        reason=invalid,
    )
    b("signature-number", "signature is a number", binding(Raw("1")), reason=invalid)
    b("signature-null", "signature is null", binding(None), reason=invalid)
    h, p, s = t.split(".")
    b(
        "signature-json-serialization-object",
        "signature is a JWS JSON serialization object",
        binding(Obj(("payload", p), ("protected", h), ("signature", s))),
        reason=invalid,
    )


def verify_vectors(v: Vectors) -> None:
    ok = v.verify
    a = example()
    signer_pem = KEYS["rsa-signer"]["publicKeyPem"].encode("ascii")
    with_extension = extension(Obj(("hash", "deadbeef"), ("note", "coi")))

    def fail(name: str, note: str, raw: str, reason: str, **kwargs: Any) -> None:
        v.verify(name, note, raw, reason=reason, **kwargs)

    # Positive controls.
    ok("rs256", "RS256 binding from the selected key", signed(a))
    ok(
        "rs256-legacy",
        "Legacy encoding: assertionSig carries the hash as hex text",
        signed(a, aggregate=LEGACY_AGGREGATE, legacy=True),
        aggregate=LEGACY_AGGREGATE,
        legacy=True,
    )
    ok(
        "rs256-method-JWS",
        "method JWS, which Java writers emit",
        signed(a, method="JWS"),
    )
    ok("rs256-method-missing", "A missing method means jws", signed(a, method=None))
    ok(
        "hs256-configured",
        "HS256 binding from a configured shared secret",
        signed(a, signer=CONFIGURED_SECRET, alg="HS256"),
        key="hs256-configured",
    )
    ok(
        "hs256-payload-key",
        "HS256 binding from the payload key",
        signed(a, signer=PAYLOAD_KEY, alg="HS256"),
        key="hs256-payload-key",
        source="payload",
    )
    ok(
        "hs256-payload-key-legacy",
        "Legacy-encoded HS256 binding from the payload key",
        signed(
            a, signer=PAYLOAD_KEY, alg="HS256", aggregate=LEGACY_AGGREGATE, legacy=True
        ),
        key="hs256-payload-key",
        source="payload",
        aggregate=LEGACY_AGGREGATE,
        legacy=True,
    )
    ok(
        "header-jwk-selected-key",
        "Header jwk of the selected key, with kid, use, and alg members",
        signed(
            a, header={"jwk": rsa_jwk(SIGNER, kid="signer-1", use="sig", alg="RS256")}
        ),
    )
    ok(
        "header-x5c-selected-key",
        "Self-signed x5c whose leaf is the selected key; no chain is validated",
        signed(a, header={"x5c": [SIGNER_CERT]}),
    )
    ok(
        "header-jwk-and-x5c-selected-key",
        "jwk and x5c of the selected key with method JWS, as Java writers emit",
        signed(a, method="JWS", header={"jwk": rsa_jwk(SIGNER), "x5c": [SIGNER_CERT]}),
    )
    ok(
        "header-x5c-extra-certificate-ignored",
        "Certificates after the x5c leaf are ignored",
        signed(a, header={"x5c": [SIGNER_CERT, OTHER_CERT]}),
    )
    ok(
        "header-kid-ignored",
        "A kid naming some other key does not affect verification",
        signed(a, header={"kid": rsa_thumbprint(OTHER)}),
    )
    ok(
        "header-jku-x5u-not-fetched",
        "jku and x5u point at unresolvable URLs and must not be fetched",
        signed(
            a,
            header={
                "jku": "https://jwks.invalid/keys.json",
                "x5u": "https://certificates.invalid/signer.pem",
            },
        ),
    )
    ok(
        "extra-claim-ignored",
        "Claims other than assertionHash and assertionSig are ignored",
        signed(a, claims=bound_claims(text(a)) | {"iat": 1767225600}),
    )
    ok(
        "unmodelled-members-signed",
        "Unmodelled top-level and statement members, hashed as received",
        signed(
            with_extension.put("statement", statement().plus(("encoding", "utf-8")))
        ),
    )
    ok(
        "acp240-object-value",
        "ACP 240 object-valued label with a JWS binding",
        signed(acp240()),
    )
    ok(
        "statement-hash-member-signed",
        "statement.hash covered by the hash, as corrected writers sign it",
        signed(example(statement().plus(("hash", EXAMPLE_STRING_HASH)))),
    )

    # Binding form (step 3.3).
    fail(
        "binding-bdo",
        "A STANAG 4778 binding object",
        bound(a, Obj(("bdo", "PEJpbmRpbmdJbmZvcm1hdGlvbi8+"))),
        "unsupported-binding",
    )
    fail(
        "binding-unknown-method",
        "An unknown method fails even with a valid signature",
        signed(a, method="Jws"),
        "unsupported-binding",
    )
    fail("binding-missing", "No binding member", text(a), "invalid-binding")
    fail(
        "binding-both-forms",
        "signature and bdo together",
        bound(a, binding(EXAMPLE_TOKEN).plus(("bdo", "PEJpbmRpbmdJbmZvcm1hdGlvbi8+"))),
        "invalid-binding",
    )

    # JWS structure (step 3.4).
    h, p, s = EXAMPLE_TOKEN.split(".")
    for name, note, token in [
        ("jws-empty", "An empty signature string", ""),
        ("jws-two-parts", "A compact JWS without its signature part", f"{h}.{p}"),
        ("jws-four-parts", "A compact JWS with an extra part", f"{EXAMPLE_TOKEN}.{s}"),
        (
            "jws-json-serialization",
            "The JWS JSON serialization in a string",
            json.dumps({"payload": p, "protected": h, "signature": s}),
        ),
        (
            "jws-header-not-json",
            "A protected header that is not JSON",
            jws(None, bound_claims(text(a)), SIGNER, header_segment=b64url(b"RS256")),
        ),
        (
            "jws-header-json-array",
            "A protected header that is a JSON array",
            jws(
                None, bound_claims(text(a)), SIGNER, header_segment=b64url(b'["RS256"]')
            ),
        ),
        (
            "jws-payload-not-json",
            "A validly signed payload that is not JSON",
            jws({"alg": "RS256"}, None, SIGNER, payload_segment=b64url(b"not json")),
        ),
        (
            "jws-payload-json-string",
            "A validly signed payload that is a JSON string",
            jws({"alg": "RS256"}, None, SIGNER, payload_segment=b64url(b'"claims"')),
        ),
        (
            "jws-crit-header",
            "A crit header, which this version never accepts",
            token_for(a, header={"crit": ["x-vector"], "x-vector": True}),
        ),
    ]:
        fail(name, note, bound(a, binding(token)), "invalid-binding")

    # Algorithms (step 3.4).
    none_token = f"{_segment({'alg': 'none'})}.{_segment(bound_claims(text(a)))}."
    fail(
        "alg-none",
        "alg none against an RS256 key",
        bound(a, binding(none_token)),
        "unsupported-algorithm",
    )
    fail(
        "alg-none-payload-key",
        "alg none against the payload key",
        bound(a, binding(none_token)),
        "unsupported-algorithm",
        key="hs256-payload-key",
        source="payload",
    )
    fail(
        "alg-missing",
        "No alg header",
        bound(a, binding(jws({"typ": "JWT"}, bound_claims(text(a)), SIGNER))),
        "unsupported-algorithm",
    )
    fail(
        "alg-not-string",
        "alg is a number",
        bound(a, binding(jws(Obj(("alg", Raw("256"))), bound_claims(text(a)), SIGNER))),
        "unsupported-algorithm",
    )
    hs512_header = _segment({"alg": "HS512"})
    hs512_payload = _segment(bound_claims(text(a)))
    hs512_mac = hmac.new(
        CONFIGURED_SECRET,
        f"{hs512_header}.{hs512_payload}".encode("ascii"),
        hashlib.sha512,
    ).digest()
    fail(
        "alg-HS512",
        "HS512 is not a supported algorithm",
        bound(a, binding(f"{hs512_header}.{hs512_payload}.{b64url(hs512_mac)}")),
        "unsupported-algorithm",
    )
    fail(
        "alg-lowercase-rs256",
        "Algorithm names are case-sensitive: rs256 is not RS256",
        signed(a, alg="rs256"),
        "unsupported-algorithm",
    )
    fail(
        "hs256-mac-with-rsa-public-key-pem",
        "HS256 keyed with the selected RSA public key PEM, against that RS256 key",
        signed(a, signer=signer_pem, alg="HS256"),
        "algorithm-mismatch",
    )
    fail(
        "rs256-against-hs256-configured",
        "An RS256 binding against a configured HS256 secret",
        signed(a),
        "algorithm-mismatch",
        key="hs256-configured",
    )
    fail(
        "rs256-jwk-against-payload-key",
        "An RS256 binding with a header jwk of its own key, against the payload key",
        signed(a, signer=OTHER, header={"jwk": rsa_jwk(OTHER)}),
        "algorithm-mismatch",
        key="hs256-payload-key",
        source="payload",
    )

    # Embedded keys (step 3.5).
    other_jwk = rsa_jwk(OTHER)
    snp = "signer-not-permitted"
    fail(
        "jwk-other-key",
        "Signed by another key whose jwk is in the header",
        signed(a, signer=OTHER, header={"jwk": other_jwk}),
        snp,
    )
    fail(
        "x5c-other-key",
        "Signed by another key whose self-signed x5c is in the header",
        signed(a, signer=OTHER, header={"x5c": [OTHER_CERT]}),
        snp,
    )
    fail(
        "jwk-and-x5c-other-key",
        "Signed by another key whose jwk and x5c agree with each other",
        signed(a, signer=OTHER, header={"jwk": other_jwk, "x5c": [OTHER_CERT]}),
        snp,
    )
    fail(
        "x5c-other-leaf-selected-key-second",
        "Another key's x5c leaf, with the selected key's certificate after it",
        signed(a, signer=OTHER, header={"x5c": [OTHER_CERT, SIGNER_CERT]}),
        snp,
    )
    iek = "invalid-embedded-key"
    fail(
        "jwk-other-x5c-selected",
        "jwk of another key with x5c of the selected key",
        signed(a, signer=OTHER, header={"jwk": other_jwk, "x5c": [SIGNER_CERT]}),
        iek,
    )
    fail(
        "jwk-selected-x5c-other",
        "jwk of the selected key with x5c of another key",
        signed(a, signer=OTHER, header={"jwk": rsa_jwk(SIGNER), "x5c": [OTHER_CERT]}),
        iek,
    )
    fake = b64url(
        hashlib.sha256(b"DSPX-5520 vectors: not a private exponent").digest() * 8
    )
    for name, note, jwk in [
        ("jwk-oct", "A symmetric jwk", {"kty": "oct", "k": b64url(CONFIGURED_SECRET)}),
        ("jwk-private-member-d", "An RSA jwk with a d member", rsa_jwk(SIGNER, d=fake)),
        (
            "jwk-private-member-qi",
            "An RSA jwk whose only private member is qi",
            rsa_jwk(SIGNER, qi=fake),
        ),
        ("jwk-not-object", "jwk is a string", "not-a-jwk"),
        ("jwk-missing-n", "An RSA jwk without n", {"kty": "RSA", "e": "AQAB"}),
        (
            "jwk-n-not-base64url",
            "An RSA jwk whose n is not base64url",
            {"kty": "RSA", "n": "not base64url!", "e": "AQAB"},
        ),
    ]:
        fail(
            name,
            f"{note}; signed by the selected key",
            signed(a, header={"jwk": jwk}),
            iek,
        )
    for name, note, x5c in [
        ("x5c-empty", "x5c is an empty array", []),
        ("x5c-not-array", "x5c is a string, not an array", SIGNER_CERT),
        ("x5c-not-base64", "The x5c leaf is not base64", ["not base64!"]),
        (
            "x5c-not-certificate",
            "The x5c leaf is not a DER certificate",
            [_b64(b"not a certificate")],
        ),
    ]:
        fail(
            name,
            f"{note}; signed by the selected key",
            signed(a, header={"x5c": x5c}),
            iek,
        )
    fail(
        "hs256-configured-x5c",
        "x5c with a configured HS256 secret",
        signed(a, signer=CONFIGURED_SECRET, alg="HS256", header={"x5c": [SIGNER_CERT]}),
        iek,
        key="hs256-configured",
    )
    fail(
        "hs256-configured-oct-jwk",
        "A symmetric jwk carrying the configured HS256 secret itself",
        signed(
            a,
            signer=CONFIGURED_SECRET,
            alg="HS256",
            header={"jwk": {"kty": "oct", "k": b64url(CONFIGURED_SECRET)}},
        ),
        iek,
        key="hs256-configured",
    )
    fail(
        "hs256-payload-key-jwk",
        "An RSA jwk with an HS256 binding from the payload key",
        signed(a, signer=PAYLOAD_KEY, alg="HS256", header={"jwk": other_jwk}),
        iek,
        key="hs256-payload-key",
        source="payload",
    )

    # Signature (step 3.6).
    sig = "signature-invalid"
    fail(
        "other-key-signature",
        "Signed by another key, no header key",
        signed(a, signer=OTHER),
        sig,
    )
    fail(
        "other-key-signature-copied-kid",
        "Signed by another key with the selected key's thumbprint as kid",
        signed(a, signer=OTHER, header={"kid": rsa_thumbprint(SIGNER)}),
        sig,
    )
    fail(
        "other-key-signature-copied-jwk",
        "Signed by another key with the selected key's jwk copied into the header",
        signed(a, signer=OTHER, header={"jwk": rsa_jwk(SIGNER)}),
        sig,
    )
    fail(
        "other-key-signature-copied-x5c",
        "Signed by another key with the selected key's certificate copied into x5c",
        signed(a, signer=OTHER, header={"x5c": [SIGNER_CERT]}),
        sig,
    )
    good_sig = bytearray(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
    good_sig[100] ^= 0x01
    fail(
        "signature-bit-flip",
        "One bit of the selected key's signature flipped",
        bound(a, binding(f"{h}.{p}.{b64url(bytes(good_sig))}")),
        sig,
    )
    fail(
        "payload-key-binding-against-configured-hs256",
        "Payload-key HS256 binding against a configured HS256 secret",
        signed(a, signer=PAYLOAD_KEY, alg="HS256"),
        sig,
        key="hs256-configured",
    )
    fail(
        "configured-hs256-binding-against-payload-key",
        "Configured-secret HS256 binding against the payload key",
        signed(a, signer=CONFIGURED_SECRET, alg="HS256"),
        sig,
        key="hs256-payload-key",
        source="payload",
    )

    # Claims and hashes (steps 3.7 to 3.9).
    mismatch = "binding-mismatch"
    claims = bound_claims(text(a))
    for name, note, c in [
        (
            "claims-missing-assertionHash",
            "No assertionHash claim",
            {"assertionSig": claims["assertionSig"]},
        ),
        (
            "claims-assertionHash-not-string",
            "assertionHash is a number",
            {"assertionHash": Raw("1"), "assertionSig": claims["assertionSig"]},
        ),
        (
            "claims-missing-assertionSig",
            "No assertionSig claim",
            {"assertionHash": claims["assertionHash"]},
        ),
        (
            "claims-assertionSig-not-string",
            "assertionSig is an array",
            {
                "assertionHash": claims["assertionHash"],
                "assertionSig": [claims["assertionSig"]],
            },
        ),
        (
            "claims-assertionHash-uppercase",
            "assertionHash in uppercase hex; it is compared exactly",
            {
                "assertionHash": claims["assertionHash"].upper(),
                "assertionSig": claims["assertionSig"],
            },
        ),
    ]:
        fail(name, note, signed(a, claims=c), mismatch)
    changed = example(statement(EXAMPLE_VALUE.replace("SECRET", "UNCLASSIFIED")))
    fail(
        "statement-changed-after-signing",
        "statement.value changed after signing",
        bound(changed, binding(token_for(a))),
        mismatch,
    )
    fail(
        "unmodelled-member-added-after-signing",
        "An unmodelled member added after signing",
        bound(with_extension, binding(token_for(a))),
        mismatch,
    )
    fail(
        "unmodelled-member-changed-after-signing",
        "An unmodelled member changed after signing",
        bound(
            extension(Obj(("hash", "deadbeef"), ("note", "changed"))),
            binding(token_for(with_extension)),
        ),
        mismatch,
    )
    fail(
        "object-value-changed-after-signing",
        "A member deep in an object statement.value changed after signing",
        bound(acp240(acp240_value("UNCLASSIFIED")), binding(token_for(acp240()))),
        mismatch,
    )
    fail(
        "binding-from-another-assertion",
        "A valid binding of a different assertion with the same key",
        bound(a, binding(token_for(acp240()))),
        mismatch,
    )
    fail(
        "aggregate-mismatch",
        "Bound to a different aggregate hash",
        signed(a),
        mismatch,
        aggregate=OTHER_AGGREGATE,
    )
    fail(
        "legacy-binding-read-as-current",
        "Legacy assertionSig, read without the legacy encoding; never retried",
        signed(a, legacy=True),
        mismatch,
    )
    fail(
        "current-binding-read-as-legacy",
        "Current assertionSig, read with the legacy encoding; never retried",
        signed(a),
        mismatch,
        legacy=True,
    )
    js_extension = with_extension
    assert old_js_hash(text(js_extension)) == JS_TODAY_EXTENSION_HASH
    fail(
        "old-js-hash-of-extension",
        "Spec 4.4 extension example signed over the old JS hash that skips hash",
        signed(
            js_extension,
            claims=bound_claims(text(js_extension), hash_hex=JS_TODAY_EXTENSION_HASH),
        ),
        mismatch,
    )
    old_js = example(
        statement().plus(("hash", "sha256:e3b0c44298fc1c149afbf4c8996fb924"))
    )
    fail(
        "old-js-writer-statement-hash",
        "statement.hash on the wire, signed by the payload key over the old JS hash",
        signed(
            old_js,
            signer=PAYLOAD_KEY,
            alg="HS256",
            claims=bound_claims(text(old_js), hash_hex=old_js_hash(text(old_js))),
        ),
        mismatch,
        key="hs256-payload-key",
        source="payload",
    )
    assert stringified_value_hash(text(acp240())) == GO_TODAY_OBJECT_HASH
    fail(
        "typed-reserialization-of-object-value",
        "ACP 240 label signed over a hash of the value stringified with sorted keys",
        signed(
            acp240(), claims=bound_claims(text(acp240()), hash_hex=GO_TODAY_OBJECT_HASH)
        ),
        mismatch,
    )


#### OUTPUT


def build() -> dict[str, Any]:
    v = Vectors()
    for add in (assertion_vectors, manifest_vectors, binding_vectors, verify_vectors):
        add(v)
    return {"format": FORMAT, "source": SOURCE, "keys": KEYS, "vectors": v.vectors}


def render(doc: dict[str, Any]) -> bytes:
    """The committed form: two-space indent, ASCII only, trailing newline."""
    return (json.dumps(doc, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the DSPX-5520 shared assertion conformance vectors."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=f"exit 1 if {OUTPUT.name} differs from a fresh build; write nothing",
    )
    args = parser.parse_args(argv)
    rendered = render(build())
    if args.check:
        if OUTPUT.read_bytes() != rendered:
            print(f"{OUTPUT} is out of date; regenerate it", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_bytes(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
