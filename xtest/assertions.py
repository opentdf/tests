import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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


#### BINDING CHECKS
#
# Every SDK binds an assertion the same way: a compact JWS whose claims are
#   assertionHash: hex(SHA-256(JCS(assertion without its binding)))
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


def assertion_hash(assertion: dict[str, Any]) -> str:
    """Hex SHA-256 of the RFC 8785 (JCS) form of ``assertion`` minus its binding.

    Sorted keys and no whitespace is JCS for what an assertion holds: strings
    and ASCII keys. It is not JCS for numbers, which no assertion carries.
    """
    unbound = {k: v for k, v in assertion.items() if k != "binding"}
    canonical = json.dumps(
        unbound, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assertion_sig(manifest: dict[str, Any], hash_hex: str) -> str:
    """The ``assertionSig`` claim a writer must produce for ``hash_hex``."""
    segments = manifest["encryptionInformation"]["integrityInformation"]["segments"]
    aggregate = b"".join(base64.b64decode(s["hash"], validate=True) for s in segments)
    if manifest.get("schemaVersion"):
        bound = bytes.fromhex(hash_hex)
    else:
        bound = hash_hex.encode("ascii")
    return base64.b64encode(aggregate + bound).decode("ascii")


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
