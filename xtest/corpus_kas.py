"""Test-time setup of the corpus KAS keys and attribute namespace.

Imports the keys in corpus/kas-keys.json into km1/km2 and creates the fixed
corpus attributes, idempotently and tolerant of concurrent setup.
"""

import base64
import re
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import abac
import corpus
from corpus import CorpusKey

NAMESPACE = "corpus.opentdf.example"
ATTR_BASE = f"https://{NAMESPACE}/attr"

# name, rule, values
ATTRIBUTES: tuple[tuple[str, abac.AttributeRule, tuple[str, ...]], ...] = (
    ("split-allof", abac.AttributeRule.ALL_OF, ("km1", "km2")),
    ("split-anyof", abac.AttributeRule.ANY_OF, ("km1", "km2")),
    ("label", abac.AttributeRule.ANY_OF, ("a",)),
)
# attribute value FQN suffix -> kid it is mapped to
VALUE_KEYS: dict[str, str] = {
    "split-allof/value/km1": "corpus-r2048",
    "split-allof/value/km2": "corpus-r2048-b",
    "split-anyof/value/km1": "corpus-r2048",
    "split-anyof/value/km2": "corpus-r2048-b",
    "label/value/a": "corpus-r2048",
}

_EXISTS = re.compile(r"already[ _]exists|unique field violation", re.IGNORECASE)


class CorpusKeyMismatch(Exception):
    """A registry key has a corpus kid but a different public key."""

    def __init__(self, kid: str):
        super().__init__(f"KAS key {kid!r} exists with a different public key")
        self.kid = kid


class CorpusValueMismatch(Exception):
    """An attribute value is mapped to a key other than the corpus key."""


def _spki_der(key: Any) -> bytes:
    return key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _body(pem: str) -> str:
    return re.sub(r"-----[A-Z ]+-----|\s", "", pem)


def registry_pem(entry: CorpusKey) -> str:
    """The public PEM to register for a corpus key (cert for PQC, public key otherwise)."""
    if entry["alg"].startswith(("rsa:", "ec:")):
        cert = x509.load_pem_x509_certificate(entry["cert"].encode())
        return (
            cert.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
    return entry["cert"]


def _decode_pem(text: str) -> str:
    """The registry returns public PEMs base64-encoded; accept either form."""
    if "-----BEGIN" in text:
        return text
    try:
        return base64.b64decode(text, validate=True).decode()
    except ValueError:
        return text


def public_matches(entry: CorpusKey, registry_pem_text: str) -> bool:
    """Whether a registry public PEM is the corpus key's public key."""
    registry_pem_text = _decode_pem(registry_pem_text)
    if entry["alg"].startswith(("rsa:", "ec:")):
        cert = x509.load_pem_x509_certificate(entry["cert"].encode())
        try:
            theirs = serialization.load_pem_public_key(registry_pem_text.encode())
        except ValueError:
            return False
        return _spki_der(cert.public_key()) == _spki_der(theirs)
    return _body(entry["cert"]) == _body(registry_pem_text)


def _check(entry: CorpusKey, key: abac.KasKey) -> abac.KasKey:
    if not public_matches(entry, key.key.public_key_ctx.pem):
        raise CorpusKeyMismatch(entry["kid"])
    return key


def _find(keys: list[abac.KasKey], kid: str) -> abac.KasKey | None:
    return next((k for k in keys if k.key.key_id == kid), None)


def ensure_corpus_keys(
    otdfctl: Any, km1: abac.KasEntry, km2: abac.KasEntry, root_key: str
) -> dict[str, abac.KasKey]:
    """Import any missing corpus keys; reuse present ones that match."""
    kases = {"km1": km1, "km2": km2}
    out: dict[str, abac.KasKey] = {}
    for kid, entry in corpus.kas_keys().items():
        kas = kases[entry["kas"]]
        existing = _find(otdfctl.kas_registry_keys_list(kas), kid)
        if existing is not None:
            out[kid] = _check(entry, existing)
            continue
        try:
            out[kid] = _check(
                entry,
                otdfctl.kas_registry_import_key(
                    kas,
                    private_pem=entry["privateKey"],
                    public_pem=registry_pem(entry),
                    key_id=kid,
                    legacy=False,
                    wrapping_key=root_key,
                    wrapping_key_id="root",
                    algorithm=entry["alg"],
                ),
            )
        except CorpusKeyMismatch:
            raise
        except Exception as e:
            if not _EXISTS.search(str(e)):
                raise
            raced = _find(otdfctl.kas_registry_keys_list(kas), kid)
            if raced is None:
                raise
            out[kid] = _check(entry, raced)
    return out


def _attribute_by_fqn(otdfctl: Any, fqn: str) -> abac.Attribute | None:
    return next((a for a in otdfctl.attribute_list() if a.fqn == fqn), None)


def ensure_corpus_attributes(
    otdfctl: Any,
    scs: abac.SubjectConditionSet,
    keys: dict[str, abac.KasKey],
) -> dict[str, abac.AttributeValue]:
    """Create the corpus namespace and attributes if absent, then bring every
    value into line, whoever created it: assign its corpus key (raising if it
    carries another) and map it to ``scs`` unless an equivalent mapping exists.

    Returns attribute values keyed by FQN.
    """
    ns = next((n for n in otdfctl.namespace_list() if n.name == NAMESPACE), None)
    if ns is None:
        try:
            ns = otdfctl.namespace_create(NAMESPACE)
        except Exception:
            ns = next(
                (n for n in otdfctl.namespace_list() if n.name == NAMESPACE), None
            )
            if ns is None:
                raise

    out: dict[str, abac.AttributeValue] = {}
    for name, rule, values in ATTRIBUTES:
        fqn = f"{ATTR_BASE}/{name}"
        attr = _attribute_by_fqn(otdfctl, fqn)
        if attr is None:
            try:
                attr = otdfctl.attribute_create(ns, name, rule, list(values))
            except Exception:
                attr = _attribute_by_fqn(otdfctl, fqn)
                if attr is None:
                    raise
        for val in attr.values or []:
            assert val.fqn
            out[val.fqn] = val

    mapped = _mapped_value_ids(otdfctl, scs)
    for fqn, val in out.items():
        suffix = fqn.removeprefix(f"{ATTR_BASE}/")
        _ensure_value_key(otdfctl, val, keys[VALUE_KEYS[suffix]])
        if val.id not in mapped:
            try:
                otdfctl.scs_map(scs, val)
            except Exception:
                if val.id not in _mapped_value_ids(otdfctl, scs):
                    raise
    return out


def _mapped_value_ids(otdfctl: Any, scs: abac.SubjectConditionSet) -> set[str]:
    """Value ids with a subject mapping to an equivalent condition set."""
    return {
        m.attribute_value.id
        for m in otdfctl.scs_map_list()
        if m.subject_condition_set.id == scs.id
        or m.subject_condition_set.subject_sets == scs.subject_sets
    }


def _ensure_value_key(otdfctl: Any, val: abac.AttributeValue, key: abac.KasKey) -> None:
    """Assign key to the value; raise if it already carries a different key."""
    current = otdfctl.attribute_value_get(val.id)
    kids = {k.public_key.kid for k in current.kas_keys or []}
    if kids == {key.key.key_id}:
        return
    if kids:
        raise CorpusValueMismatch(
            f"{val.fqn} is mapped to {sorted(kids)}, expected {key.key.key_id!r}"
        )
    try:
        otdfctl.key_assign_value(key, val)
    except Exception as e:
        if not _EXISTS.search(str(e)):
            raise
