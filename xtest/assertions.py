import base64
import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import rfc8785
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

import jsontext

Type = Literal["handling", "other"]
Scope = Literal["payload", "tdo"]
AppliesTo = Literal["encrypted", "unencrypted"]
BindingMethod = Literal["jws", "JWS"]


class Statement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format: str
    schema_: str = Field(..., alias="schema")
    value: str | dict[str, str]


class Binding(BaseModel):
    method: BindingMethod
    signature: str


class AssertionKey(BaseModel):
    alg: str
    key: str


class Assertion(BaseModel):
    id: str
    type: Type
    scope: Scope
    appliesToState: AppliesTo
    statement: Statement
    binding: Binding | None = None
    signingKey: AssertionKey | None = None


class AssertionVerificationKeys(BaseModel):
    keys: dict[str, AssertionKey]


def load_assertions(path: Path | str) -> list[Assertion]:
    return TypeAdapter(list[Assertion]).validate_json(Path(path).read_text())


def load_verification_keys(path: Path | str) -> AssertionVerificationKeys:
    return AssertionVerificationKeys.model_validate_json(Path(path).read_text())


#### PARSING (spec Section 3 of the ZTDF assertions contract, DSPX-5519)
#
# A reference reader for the parts of the contract every SDK must agree on:
# the strict JSON profile, case variants of modelled member names, the exact
# `id`, the hash input, the binding form, and (below, after BINDING CHECKS)
# single-assertion binding verification. The DSPX-5520 shared vectors in
# vectors/assertions-phase0.json are checked against it.

#: The spec Section 9 failure reasons that Phase 0 readers report.
REASONS = frozenset(
    {
        "invalid-json",
        "duplicate-member",
        "ambiguous-member",
        "invalid-id",
        "invalid-statement",
        "invalid-binding",
        "unsupported-binding",
        "unsupported-algorithm",
        "algorithm-mismatch",
        "invalid-embedded-key",
        "signer-not-permitted",
        "signature-invalid",
        "binding-mismatch",
        "configuration-error",
    }
)


class AssertionFailure(Exception):
    """A manifest or assertion fails a contract check with one Section 9 reason."""

    def __init__(self, reason: str, detail: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"unknown reason {reason!r}")
        super().__init__(f"reason={reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for name, value in pairs:
        if name in obj:
            raise AssertionFailure("duplicate-member", f"duplicate member {name!r}")
        obj[name] = value
    return obj


def _not_json(name: str) -> Any:
    raise AssertionFailure("invalid-json", f"{name} is not a JSON value")


def loads_strict(raw: str | bytes) -> Any:
    """Parse RFC 8259 JSON, rejecting duplicate member names while parsing.

    Names are compared after escapes are decoded, so ``"id"`` and
    ``"\\u0069d"`` are duplicates. Every number becomes a float, the IEEE 754
    double that JCS works with; out-of-range numbers become infinities, which
    ``check_ijson`` rejects where the contract requires it.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise AssertionFailure("invalid-json", f"not UTF-8: {e}") from None
    try:
        return json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_float=float,
            parse_int=float,
            parse_constant=_not_json,
        )
    except json.JSONDecodeError as e:
        raise AssertionFailure("invalid-json", str(e)) from None
    except RecursionError:
        raise AssertionFailure("invalid-json", "nested too deeply") from None


def _check_text(text: str, what: str) -> None:
    for c in text:
        cp = ord(c)
        if 0xD800 <= cp <= 0xDFFF:
            raise AssertionFailure(
                "invalid-json", f"{what} contains surrogate U+{cp:04X}"
            )
        if 0xFDD0 <= cp <= 0xFDEF or cp & 0xFFFE == 0xFFFE:
            raise AssertionFailure(
                "invalid-json", f"{what} contains noncharacter U+{cp:04X}"
            )


def check_ijson(value: Any) -> None:
    """Reject what RFC 7493 (I-JSON) forbids inside an assertion (spec 3.1).

    Surrogate code points (lone surrogates; a valid escaped pair has already
    been combined into one code point), Unicode noncharacters, and numbers
    outside the IEEE 754 double range.
    """
    match value:
        case str():
            _check_text(value, "string")
        case float() if math.isinf(value):
            raise AssertionFailure("invalid-json", "number outside the double range")
        case dict():
            for name, member in value.items():
                _check_text(name, "member name")
                check_ijson(member)
        case list():
            for element in value:
                check_ijson(element)
        case _:
            pass


#: Listed member names per checked level (spec Table 3.2; DSPX-1561
#: decisions, "Modelled member names and case variants"). A level path is the
#: dot-separated member names from the manifest root, ``""`` being the root;
#: ``name[]`` means each element of that member's array. A level applies only
#: where its value is a JSON object.
MODELLED_NAMES: dict[str, tuple[str, ...]] = {
    "": (
        "assertions",
        "encryptionInformation",
        "payload",
        "schemaVersion",
        "tdf_spec_version",
    ),
    "payload": (
        "type",
        "url",
        "protocol",
        "mimeType",
        "isEncrypted",
        "tdf_spec_version",
    ),
    "encryptionInformation": (
        "type",
        "policy",
        "keyAccess",
        "method",
        "integrityInformation",
    ),
    "encryptionInformation.keyAccess[]": (
        "type",
        "url",
        "protocol",
        "wrappedKey",
        "policyBinding",
        "encryptedMetadata",
        "kid",
        "sid",
        "schemaVersion",
        "ephemeralPublicKey",
    ),
    "encryptionInformation.keyAccess[].policyBinding": ("alg", "hash"),
    "encryptionInformation.method": ("algorithm", "iv", "isStreamable"),
    "encryptionInformation.integrityInformation": (
        "rootSignature",
        "segmentHashAlg",
        "segmentSizeDefault",
        "encryptedSegmentSizeDefault",
        "segments",
    ),
    "encryptionInformation.integrityInformation.rootSignature": ("alg", "sig"),
    "encryptionInformation.integrityInformation.segments[]": (
        "hash",
        "segmentSize",
        "encryptedSegmentSize",
    ),
    "assertions[]": ("id", "type", "scope", "appliesToState", "statement", "binding"),
    "assertions[].statement": ("format", "schema", "value"),
    "assertions[].binding": ("method", "signature", "bdo"),
}

#: Names that do not violate rule R1 at a level (R4): java-sdk up to v0.7.5
#: wrote ``IsStreamable``. R2 still applies to them.
CASE_VARIANT_EXCEPTIONS: dict[str, tuple[str, ...]] = {
    "encryptionInformation.method": ("IsStreamable",),
}

#: The level of an assertion object, for vectors that hold one assertion.
ASSERTION_LEVEL = "assertions[]"

# The simple case folds that Go's strings.EqualFold applies to ASCII letters,
# besides the ASCII case pairs themselves: U+017F LATIN SMALL LETTER LONG S and
# U+212A KELVIN SIGN.
_NON_ASCII_FOLDS = {"\u017f": "s", "\u212a": "k"}


def _fold(c: str) -> str:
    if "A" <= c <= "Z":
        return c.lower()
    return _NON_ASCII_FOLDS.get(c, c)


def fold_name(name: str) -> str:
    """``name`` with the contract's case fold applied to each code point."""
    return "".join(_fold(c) for c in name)


def is_case_variant(name: str, other: str) -> bool:
    """True when two member names are case variants of each other (spec 3.2).

    They differ, and are equal after folding ASCII letters, U+017F, and U+212A
    code point by code point (so the code point counts match too). Deliberately
    not Unicode case folding, ``str.lower``, or Java's ``equalsIgnoreCase``:
    those also match names such as ``ıd`` or ``ﬆatement``, which Go's decoder
    does not.
    """
    return name != other and fold_name(name) == fold_name(other)


def _check_level(obj: dict[str, Any], level: str) -> None:
    """Rules R1 and R2 for one object at ``level``, then its child levels."""
    listed = MODELLED_NAMES[level]
    exempt = CASE_VARIANT_EXCEPTIONS.get(level, ())
    where = level or "manifest root"
    folded: dict[str, str] = {}
    for name in obj:
        if name not in exempt:
            for m in listed:
                if is_case_variant(name, m):
                    raise AssertionFailure(
                        "ambiguous-member",
                        f"{where}: {name!r} is a case variant of {m!r}",
                    )
        key = fold_name(name)
        if key in folded:
            raise AssertionFailure(
                "ambiguous-member",
                f"{where}: {folded[key]!r} and {name!r} are case variants",
            )
        folded[key] = name
    for m in listed:
        if m not in obj:
            continue
        child = f"{level}.{m}" if level else m
        value = obj[m]
        if child in MODELLED_NAMES and isinstance(value, dict):
            _check_level(value, child)
        elif f"{child}[]" in MODELLED_NAMES and isinstance(value, list):
            for element in value:
                if isinstance(element, dict):
                    _check_level(element, f"{child}[]")


def parse_assertion(raw: str | bytes) -> dict[str, Any]:
    """Spec Section 3 parsing of one assertion wire object's JSON text.

    Duplicate members anywhere, then case variants (rules R1 and R2) at the
    ``assertions[]`` level and below, then I-JSON. Does not check ``id``;
    see ``assertion_id``.
    """
    a = loads_strict(raw)
    if not isinstance(a, dict):
        raise AssertionFailure("invalid-json", "an assertion must be a JSON object")
    _check_level(a, ASSERTION_LEVEL)
    check_ijson(a)
    return a


def parse_manifest(raw: str | bytes) -> dict[str, Any]:
    """The manifest-level Section 3 parse step (step 1 of spec Section 8).

    Invalid UTF-8 or a byte-order mark anywhere; duplicate members anywhere;
    case variants (rules R1 and R2) at every level of ``MODELLED_NAMES``;
    I-JSON inside each assertion object. Nothing else is checked.
    """
    m = loads_strict(raw)
    if not isinstance(m, dict):
        raise AssertionFailure("invalid-json", "a manifest must be a JSON object")
    _check_level(m, "")
    listed = m.get("assertions")
    if isinstance(listed, list):
        for a in listed:
            if isinstance(a, dict):
                check_ijson(a)
    return m


def assertion_id(a: dict[str, Any]) -> str:
    """The exact ``id`` (spec 3.3): a nonempty string, never trimmed or folded."""
    id = a.get("id")
    if not isinstance(id, str) or not id:
        raise AssertionFailure(
            "invalid-id", f"id must be a nonempty string, not {id!r}"
        )
    return id


def check_statement(a: dict[str, Any]) -> None:
    """**Proposed** statement typing (spec 2.2). Not a Phase 0 check.

    ``statement`` must be an object whose ``value`` is a string or an object.
    """
    statement = a.get("statement")
    if not isinstance(statement, dict):
        raise AssertionFailure("invalid-statement", "statement is not an object")
    if not isinstance(statement.get("value"), str | dict):
        raise AssertionFailure(
            "invalid-statement", "statement.value is neither a string nor an object"
        )


def binding_form(a: dict[str, Any]) -> Literal["jws"]:
    """The binding form (spec 5.1); only the JWS form is supported.

    The form follows from which of ``signature`` and ``bdo`` are present,
    before ``method`` is looked at.
    """
    if "binding" not in a:
        raise AssertionFailure("invalid-binding", "no binding")
    binding = a["binding"]
    if not isinstance(binding, dict):
        raise AssertionFailure("invalid-binding", "binding is not an object")
    has_signature, has_bdo = "signature" in binding, "bdo" in binding
    if has_signature and has_bdo:
        raise AssertionFailure("invalid-binding", "binding has both forms")
    if not has_signature and not has_bdo:
        raise AssertionFailure("invalid-binding", "binding has neither form")
    if has_bdo:
        raise AssertionFailure(
            "unsupported-binding", "STANAG 4778 binding objects are not supported"
        )
    if not isinstance(binding["signature"], str):
        raise AssertionFailure("invalid-binding", "binding.signature is not a string")
    method = binding.get("method", "jws")
    if not isinstance(method, str):
        raise AssertionFailure("invalid-binding", "binding.method is not a string")
    if method not in ("jws", "JWS"):
        raise AssertionFailure(
            "unsupported-binding", f"unsupported binding method {method!r}"
        )
    return "jws"


def _as_doubles(value: Any) -> Any:
    """Every JSON number is a double to JCS, but ``json.load`` makes ints."""
    match value:
        case bool():
            return value
        case int():
            try:
                return float(value)
            except OverflowError:
                raise AssertionFailure(
                    "invalid-json", "number outside the double range"
                ) from None
        case dict():
            return {k: _as_doubles(v) for k, v in value.items()}
        case list():
            return [_as_doubles(v) for v in value]
        case _:
            return value


#### BINDING CHECKS
#
# Every SDK binds an assertion the same way: a compact JWS whose claims are
#   assertionHash: hex(SHA-256(JCS(assertion as received, minus its binding)))
#   assertionSig:  base64(aggregateHash || assertionHash)
# where aggregateHash is the concatenated, base64-decoded segment hashes, and
# assertionHash is appended as raw bytes -- or as its hex text, for manifests
# with no schemaVersion (4.2.2 and earlier). The JWS is signed with the
# assertion's own key if it has one, else HS256 over the payload key.


@dataclass(frozen=True)
class Jws:
    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def parse_jws(token: str) -> Jws:
    parts = token.split(".")
    assert len(parts) == 3, (
        f"binding signature is not a compact JWS ({len(parts)} part(s))"
    )
    header, claims = (json.loads(_b64url_decode(p)) for p in parts[:2])
    return Jws(
        header=header,
        claims=claims,
        signing_input=f"{parts[0]}.{parts[1]}".encode("ascii"),
        signature=_b64url_decode(parts[2]),
    )


def verify_jws_signature(jws: Jws, key: AssertionKey) -> None:
    assert jws.header.get("alg") == key.alg, (
        f"binding signed with {jws.header.get('alg')!r}, expected {key.alg!r}"
    )
    match key.alg:
        case "HS256":
            # The CLIs all take the HS256 key string's UTF-8 bytes as the secret.
            mac = hmac.new(key.key.encode("utf-8"), jws.signing_input, hashlib.sha256)
            assert hmac.compare_digest(mac.digest(), jws.signature), (
                "HS256 binding signature does not verify"
            )
        case "RS256":
            public_key = serialization.load_pem_public_key(key.key.encode("ascii"))
            assert isinstance(public_key, rsa.RSAPublicKey)
            try:
                public_key.verify(
                    jws.signature,
                    jws.signing_input,
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
            except InvalidSignature:
                raise AssertionError(
                    "RS256 binding signature does not verify"
                ) from None
        case _:
            assert False, f"unsupported binding algorithm {key.alg!r}"


def assertion_hash(assertion: dict[str, Any] | str | bytes) -> str:
    """``assertionHash`` for ``assertion``: spec Section 4.1.

    Lowercase hex SHA-256 of the RFC 8785 (JCS) form of the assertion as
    received, minus only its top-level ``binding``. Raw JSON text is parsed
    under spec Section 3 first (see ``parse_assertion``); a dict, such as an
    element of ``tdfs.manifest_json``, is taken as already parsed.
    """
    a = parse_assertion(assertion) if isinstance(assertion, str | bytes) else assertion
    unbound = {k: _as_doubles(v) for k, v in a.items() if k != "binding"}
    return hashlib.sha256(rfc8785.dumps(unbound)).hexdigest()


def bound_assertion_sig(aggregate: bytes, hash_hex: str, legacy: bool) -> str:
    """The ``assertionSig`` claim (spec 5.3) binding ``hash_hex`` to a payload.

    ``aggregate`` is the concatenated, base64-decoded segment hashes. The
    assertion hash is appended as its 32 raw bytes, or as its 64 hex
    characters under the legacy (4.2.2) encoding.
    """
    bound = hash_hex.encode("ascii") if legacy else bytes.fromhex(hash_hex)
    return base64.b64encode(aggregate + bound).decode("ascii")


def assertion_sig(manifest: dict[str, Any], hash_hex: str) -> str:
    """The ``assertionSig`` claim a writer must produce for ``hash_hex``."""
    segments = manifest["encryptionInformation"]["integrityInformation"]["segments"]
    aggregate = b"".join(base64.b64decode(s["hash"], validate=True) for s in segments)
    return bound_assertion_sig(
        aggregate, hash_hex, legacy=not manifest.get("schemaVersion")
    )


def assert_bound(
    manifest: dict[str, Any],
    expected: list[Assertion],
    keys: AssertionVerificationKeys | None = None,
) -> None:
    """Assert ``manifest`` carries ``expected``, each bound to this payload.

    Checks what a reader checks, plus what no reader can: that the writer
    copied each assertion through unchanged and kept its signing key out of
    the manifest. Every assertion's claims are checked, including any the
    writer added on its own (java adds system-metadata). Signatures are only
    verified for assertions in ``keys``; the rest are signed with the payload
    key, which the test never sees.
    """
    written = {a["id"]: a for a in manifest.get("assertions") or []}
    for want in expected:
        assert want.id in written, (
            f"assertion {want.id!r} missing from manifest; found {sorted(written)}"
        )
        raw = written[want.id]
        assert "signingKey" not in raw, (
            f"assertion {want.id!r} leaked its signing key into the manifest"
        )
        got = Assertion.model_validate(raw)
        unbound = {"binding", "signingKey"}
        assert got.model_dump(exclude=unbound) == want.model_dump(exclude=unbound), (
            f"assertion {want.id!r} was altered on write"
        )

    for id, raw in written.items():
        binding = Binding.model_validate(raw.get("binding"))
        jws = parse_jws(binding.signature)
        hash_hex = assertion_hash(raw)
        assert jws.claims.get("assertionHash") == hash_hex, (
            f"assertion {id!r}: assertionHash claim is not the hash of the assertion"
        )
        assert jws.claims.get("assertionSig") == assertion_sig(manifest, hash_hex), (
            f"assertion {id!r}: assertionSig claim does not bind this payload"
        )
        key = keys.keys.get(id) if keys else None
        if key:
            verify_jws_signature(jws, key)
        else:
            assert jws.header.get("alg") == "HS256", (
                f"assertion {id!r} has no key of its own, so must be HS256 over "
                f"the payload key; got {jws.header.get('alg')!r}"
            )


#### BINDING CONSTRUCTION (spec Sections 4.3 and 5)
#
# What a writer does: hash the wire object, then sign the claims. Shared by
# the DSPX-5520 vector generator and the xtest cases that put assertions into
# real TDFs, both signed by the key a reader configured (positive controls)
# and by keys it never configured.

#: An RSA private key signs RS256; raw secret bytes sign HS256.
Signer = rsa.RSAPrivateKey | bytes


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def jws_signature(signing_input: bytes, signer: Signer) -> bytes:
    if isinstance(signer, bytes):
        return hmac.new(signer, signing_input, hashlib.sha256).digest()
    return signer.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())


def json_segment(value: Any) -> str:
    """A JWS header or payload segment: base64url of compact JSON."""
    return b64url(jsontext.text(value).encode("utf-8"))


def compact_jws(header_segment: str, payload_segment: str, signer: Signer) -> str:
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = b64url(jws_signature(signing_input, signer))
    return f"{header_segment}.{payload_segment}.{signature}"


def binding_claims(hash_hex: str, aggregate: bytes, legacy: bool) -> dict[str, str]:
    """The ``assertionHash`` and ``assertionSig`` claims (spec 5.3)."""
    return {
        "assertionHash": hash_hex,
        "assertionSig": bound_assertion_sig(aggregate, hash_hex, legacy),
    }


def manifest_aggregate(manifest: dict[str, Any]) -> bytes:
    """The aggregate hash (spec 5.2) of a parsed manifest."""
    segments = manifest["encryptionInformation"]["integrityInformation"]["segments"]
    return b"".join(base64.b64decode(s["hash"], validate=True) for s in segments)


def sign_assertion(
    unbound: dict[str, Any],
    signer: Signer,
    *,
    aggregate: bytes,
    legacy: bool,
    alg: str = "RS256",
    header: dict[str, Any] | None = None,
    method: str | None = "jws",
    hash_hex: str | None = None,
) -> dict[str, Any]:
    """``unbound`` with a JWS ``binding`` appended, as a writer would sign it.

    ``hash_hex`` overrides the hash to sign, for bindings computed under some
    other rule. ``method=None`` leaves ``method`` out of the binding.
    """
    h = assertion_hash(unbound) if hash_hex is None else hash_hex
    token = compact_jws(
        json_segment({"alg": alg} | (header or {})),
        json_segment(binding_claims(h, aggregate, legacy)),
        signer,
    )
    binding = (
        {"signature": token}
        if method is None
        else {"method": method, "signature": token}
    )
    return {k: v for k, v in unbound.items() if k != "binding"} | {"binding": binding}


def _b64url_uint(n: int) -> str:
    return b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))


def rsa_public_jwk(public_key: rsa.RSAPublicKey, **extra: Any) -> dict[str, Any]:
    numbers = public_key.public_numbers()
    jwk = {"kty": "RSA", "n": _b64url_uint(numbers.n), "e": _b64url_uint(numbers.e)}
    return jwk | extra


def rsa_jwk_thumbprint(public_key: rsa.RSAPublicKey) -> str:
    """RFC 7638 SHA-256 JWK thumbprint."""
    jwk = rsa_public_jwk(public_key)
    required = {m: jwk[m] for m in ("e", "kty", "n")}
    return b64url(hashlib.sha256(rfc8785.dumps(required)).digest())


def self_signed_certificate(
    key: rsa.RSAPrivateKey,
    common_name: str,
    serial: int,
    not_before: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    not_after: datetime = datetime(2036, 1, 1, tzinfo=UTC),
) -> str:
    """Base64 DER of a self-signed leaf for ``key``, as an ``x5c`` entry.

    Deterministic for fixed arguments: RSA PKCS #1 v1.5 signatures are.
    """
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    return base64.b64encode(
        certificate.public_bytes(serialization.Encoding.DER)
    ).decode("ascii")


#: The member names the old JS hash skipped at every depth.
OLD_JS_EXCLUDED = ("binding", "hash", "sign", "verify", "signingKey")


def _strip_old_js_excluded(value: Any) -> Any:
    match value:
        case dict():
            return {
                k: _strip_old_js_excluded(v)
                for k, v in value.items()
                if k not in OLD_JS_EXCLUDED
            }
        case list():
            return [_strip_old_js_excluded(v) for v in value]
        case _:
            return value


def old_js_assertion_hash(a: dict[str, Any]) -> str:
    """The hash older JS writers signed: five member names dropped at any depth.

    Not the contract's hash. A binding over it must fail with
    ``binding-mismatch`` whenever one of those names appears below the top
    level (spec 13).
    """
    stripped = _strip_old_js_excluded(_as_doubles(a))
    return hashlib.sha256(rfc8785.dumps(stripped)).hexdigest()


#### REFERENCE VERIFIER (spec Section 8, steps 3.3 to 3.9)
#
# Verifies one parsed assertion against a key that key selection (spec 6.1)
# has already chosen. Embedded keys only ever have to match that key; the
# signature is always checked with it, and `kid`, `jku`, and `x5u` are never
# consulted.

#: The algorithms every Phase 0 reader supports (spec 7). ES256 is Phase 1.
SUPPORTED_ALGORITHMS = ("RS256", "HS256")

#: JWK members that only a private or symmetric key has (RFC 7518 Section 6).
PRIVATE_JWK_MEMBERS = ("d", "p", "q", "dp", "dq", "qi", "oth")


@dataclass(frozen=True)
class VerificationKey:
    """A selected verification key: an RSA public key or an HMAC secret."""

    alg: Literal["RS256", "HS256"]
    material: rsa.RSAPublicKey | bytes


def configured_key(
    alg: str, *, public_key_pem: str | None = None, secret: bytes | None = None
) -> VerificationKey:
    """Prepare a configured key (spec 6.1); ``configuration-error`` if unusable.

    Exactly one form of material, matching ``alg`` exactly (``rs256`` is not
    ``RS256``). A PEM text secret is refused, so public-key bytes can never be
    an HMAC secret (spec 7).
    """

    def refuse(why: str) -> AssertionFailure:
        return AssertionFailure("configuration-error", why)

    if alg == "RS256":
        if public_key_pem is None or secret is not None:
            raise refuse("an RS256 key needs a public key and nothing else")
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
        except ValueError:
            raise refuse("the RS256 key is not a PEM public key") from None
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise refuse("the RS256 key is not an RSA key")
        return VerificationKey("RS256", public_key)
    if alg == "HS256":
        if not secret or public_key_pem is not None:
            raise refuse("an HS256 key needs a nonempty secret and nothing else")
        if b"-----BEGIN" in secret:
            raise refuse("an HS256 secret must not be PEM text")
        return VerificationKey("HS256", secret)
    raise refuse(f"unsupported alg {alg!r}")


_BASE64URL = re.compile(r"[A-Za-z0-9_-]*")


def _b64url_strict(part: str) -> bytes | None:
    """Canonical unpadded base64url, as JWS requires, or None.

    The URL-safe alphabet, no padding, and zero in the unused trailing bits
    of the last character, so that exactly one spelling decodes to any given
    bytes (RFC 4648 Section 3.5).
    """
    if not _BASE64URL.fullmatch(part) or len(part) % 4 == 1:
        return None
    data = base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    return data if b64url(data) == part else None


def _jws_object(part: str, what: str) -> dict[str, Any]:
    data = _b64url_strict(part)
    if data is None:
        raise AssertionFailure("invalid-binding", f"JWS {what} is not base64url")
    try:
        obj = loads_strict(data)
    except AssertionFailure as e:
        raise AssertionFailure(
            "invalid-binding", f"JWS {what} is not JSON: {e.detail}"
        ) from None
    if not isinstance(obj, dict):
        raise AssertionFailure("invalid-binding", f"JWS {what} is not a JSON object")
    return obj


def _public_key_identity(public_key: Any) -> tuple[Any, ...]:
    if isinstance(public_key, rsa.RSAPublicKey):
        numbers = public_key.public_numbers()
        return ("RSA", numbers.n, numbers.e)
    return (
        "SPKI",
        public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
    )


def _jwk_bytes(jwk: dict[str, Any], member: str) -> bytes:
    value = jwk.get(member)
    data = _b64url_strict(value) if isinstance(value, str) else None
    if not data:
        raise AssertionFailure(
            "invalid-embedded-key", f"jwk {member!r} is not canonical base64url"
        )
    return data


def _jwk_uint(jwk: dict[str, Any], member: str) -> int:
    """An RSA jwk integer, which must use the minimum number of octets
    (RFC 7518 Section 6.3.1.1): a leading zero octet is malformed."""
    data = _jwk_bytes(jwk, member)
    if data[0] == 0:
        raise AssertionFailure(
            "invalid-embedded-key", f"jwk {member!r} has a leading zero octet"
        )
    return int.from_bytes(data, "big")


#: JWK ``crv`` values and their coordinate lengths (RFC 7518 Section 6.2.1).
_EC_CURVES: dict[str, tuple[ec.EllipticCurve, int]] = {
    "P-256": (ec.SECP256R1(), 32),
    "P-384": (ec.SECP384R1(), 48),
    "P-521": (ec.SECP521R1(), 66),
}


#: OKP signature ``crv`` values and their key lengths (RFC 8037 Section 2).
#: X25519 and X448 are key-agreement curves, so they are malformed here.
_OKP_CURVES: dict[str, int] = {"Ed25519": 32, "Ed448": 57}


def _jwk_okp_identity(jwk: dict[str, Any]) -> tuple[Any, ...]:
    """An OKP jwk's public key: a signature curve and an exact-length ``x``."""
    crv = jwk.get("crv")
    if not isinstance(crv, str) or crv not in _OKP_CURVES:
        raise AssertionFailure("invalid-embedded-key", f"jwk crv {crv!r}")
    x = _jwk_bytes(jwk, "x")
    if len(x) != _OKP_CURVES[crv]:
        raise AssertionFailure(
            "invalid-embedded-key", f"jwk x is not {_OKP_CURVES[crv]} octets"
        )
    return ("OKP", crv, x)


def _jwk_ec_identity(jwk: dict[str, Any]) -> tuple[Any, ...]:
    """An EC jwk's public key; coordinates are exactly the curve's length."""
    crv = jwk.get("crv")
    if not isinstance(crv, str) or crv not in _EC_CURVES:
        raise AssertionFailure("invalid-embedded-key", f"jwk crv {crv!r}")
    curve, size = _EC_CURVES[crv]
    x, y = (_jwk_bytes(jwk, m) for m in ("x", "y"))
    if len(x) != size or len(y) != size:
        raise AssertionFailure(
            "invalid-embedded-key", f"jwk coordinates are not {size} octets"
        )
    try:
        public_key = ec.EllipticCurvePublicNumbers(
            int.from_bytes(x), int.from_bytes(y), curve
        ).public_key()
    except ValueError:
        raise AssertionFailure(
            "invalid-embedded-key", "jwk is not a point on its curve"
        ) from None
    return _public_key_identity(public_key)


def _jwk_identity(jwk: Any) -> tuple[Any, ...]:
    if not isinstance(jwk, dict):
        raise AssertionFailure("invalid-embedded-key", "jwk is not an object")
    kty = jwk.get("kty")
    if not isinstance(kty, str):
        raise AssertionFailure("invalid-embedded-key", "jwk has no kty")
    if kty == "oct":
        raise AssertionFailure("invalid-embedded-key", "jwk is a symmetric key")
    private = [m for m in PRIVATE_JWK_MEMBERS if m in jwk]
    if private:
        raise AssertionFailure(
            "invalid-embedded-key", f"jwk has private members {private}"
        )
    if kty == "RSA":
        return ("RSA", _jwk_uint(jwk, "n"), _jwk_uint(jwk, "e"))
    if kty == "EC":
        # Well formed, it is a different key type from any RSA selection.
        return _jwk_ec_identity(jwk)
    if kty == "OKP":
        return _jwk_okp_identity(jwk)
    raise AssertionFailure("invalid-embedded-key", f"jwk kty {kty!r}")


def _x5c_identity(x5c: Any) -> tuple[Any, ...]:
    if not isinstance(x5c, list) or not x5c or not all(isinstance(c, str) for c in x5c):
        raise AssertionFailure(
            "invalid-embedded-key", "x5c is not a nonempty array of strings"
        )
    try:
        # Every element must be canonical padded standard base64 (RFC 7515
        # Section 4.1.6): zero trailing bits. Only the leaf is parsed,
        # strictly, with no trailing data.
        decoded = [base64.b64decode(c, validate=True) for c in x5c]
        if any(
            base64.b64encode(d).decode("ascii") != c
            for d, c in zip(decoded, x5c, strict=True)
        ):
            raise ValueError("x5c base64 is not canonical")
        leaf = x509.load_der_x509_certificate(decoded[0])
    except ValueError:
        raise AssertionFailure(
            "invalid-embedded-key", "x5c is not base64 DER with a valid leaf"
        ) from None
    # Only the leaf's public key is compared. No chain is built or validated,
    # so nothing here says the certificate is valid (spec 6.2).
    return _public_key_identity(leaf.public_key())


def _check_embedded_keys(header: dict[str, Any], key: VerificationKey) -> None:
    present = [m for m in ("jwk", "x5c") if m in header]
    if not present:
        return
    if key.alg == "HS256":
        raise AssertionFailure(
            "invalid-embedded-key", f"{present} present with an HMAC key"
        )
    identities = []
    if "jwk" in header:
        identities.append(_jwk_identity(header["jwk"]))
    if "x5c" in header:
        identities.append(_x5c_identity(header["x5c"]))
    if len(identities) == 2 and identities[0] != identities[1]:
        raise AssertionFailure("invalid-embedded-key", "jwk and x5c keys differ")
    if identities[0] != _public_key_identity(key.material):
        raise AssertionFailure(
            "signer-not-permitted", "embedded key is not the selected key"
        )


def _check_signature(
    signing_input: bytes, signature_part: str, key: VerificationKey
) -> None:
    signature = _b64url_strict(signature_part)
    valid = False
    if signature is not None:
        if isinstance(key.material, bytes):
            mac = hmac.new(key.material, signing_input, hashlib.sha256).digest()
            valid = hmac.compare_digest(mac, signature)
        else:
            try:
                key.material.verify(
                    signature, signing_input, padding.PKCS1v15(), hashes.SHA256()
                )
                valid = True
            except InvalidSignature:
                pass
    if not valid:
        raise AssertionFailure(
            "signature-invalid", f"signature does not verify under the {key.alg} key"
        )


def verify_assertion_binding(
    a: dict[str, Any], key: VerificationKey, aggregate: bytes, legacy: bool
) -> None:
    """Spec Section 8 steps 3.3 to 3.9 for one parsed assertion.

    ``key`` is the already-selected key, ``aggregate`` the decoded aggregate
    hash, and ``legacy`` the SDK's legacy-encoding decision (spec 5.4).
    Raises ``AssertionFailure`` with the first failing step's reason.
    """
    binding_form(a)
    parts = a["binding"]["signature"].split(".")
    if len(parts) != 3:
        raise AssertionFailure(
            "invalid-binding", f"JWS has {len(parts)} part(s), not 3"
        )
    header = _jws_object(parts[0], "header")
    claims = _jws_object(parts[1], "payload")
    if "crit" in header:
        raise AssertionFailure("invalid-binding", "JWS has a crit header")
    alg = header.get("alg")
    if not isinstance(alg, str) or alg not in SUPPORTED_ALGORITHMS:
        raise AssertionFailure("unsupported-algorithm", f"alg {alg!r}")
    if alg != key.alg:
        raise AssertionFailure(
            "algorithm-mismatch", f"alg {alg!r} but the selected key is {key.alg}"
        )
    _check_embedded_keys(header, key)
    _check_signature(f"{parts[0]}.{parts[1]}".encode("ascii"), parts[2], key)
    hash_claim, sig_claim = claims.get("assertionHash"), claims.get("assertionSig")
    if not isinstance(hash_claim, str) or not isinstance(sig_claim, str):
        raise AssertionFailure(
            "binding-mismatch", "assertionHash or assertionSig missing or not a string"
        )
    expected = assertion_hash(a)
    if hash_claim != expected:
        raise AssertionFailure(
            "binding-mismatch", "assertionHash is not the hash of the assertion"
        )
    if sig_claim != bound_assertion_sig(aggregate, expected, legacy):
        raise AssertionFailure(
            "binding-mismatch", "assertionSig does not bind this payload"
        )
