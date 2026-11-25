"""What the generator writes: the sdk-* variants, the tamper bases and their plaintexts.

Shapes (key, segment layout, assertions, plaintext size) follow the corpus being
regenerated, re-pointed at the corpus keys. Offline: no platform imports.
"""

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

import corpus_kas
from corpus import CorpusKey

Keys = dict[str, CorpusKey]

# KAO URLs baked into every fixture.
KAS_URL = {"km1": "http://localhost:8585", "km2": "http://localhost:8686"}


class KasSpec(TypedDict):
    url: str
    kid: str
    alg: str


class SplitSpec(TypedDict):
    kas: int
    sid: NotRequired[str]


class StatementSpec(TypedDict):
    format: str
    schema: str
    value: str


class AssertionSpec(TypedDict):
    kind: Literal["system-metadata", "handling"]
    alg: NotRequired[str]
    key_pem: NotRequired[str]
    x5c: NotRequired[list[str]]
    # Handling only; each writer has a default for any left out.
    id: NotRequired[str]
    scope: NotRequired[Literal["tdo", "payload"]]
    applies_to_state: NotRequired[Literal["encrypted", "unencrypted"]]
    statement: NotRequired[StatementSpec]


class WriteJob(TypedDict, total=False):
    """One writer job; see corpus_gen/selfcheck.py and the writers for the fields."""

    out: str
    plaintext: str
    kas: list[KasSpec]
    split: list[SplitSpec]
    attributes: list[str]
    segment_size: int
    mime_type: str
    encrypted_metadata: str
    assertions: list[AssertionSpec]
    target_mode: str


def _kas(keys: Keys, kid: str) -> KasSpec:
    k = keys[kid]
    return {"url": KAS_URL[k["kas"]], "kid": kid, "alg": k["alg"]}


def _wrapped(kid: str, extra: WriteJob | None = None) -> Callable[[Keys], WriteJob]:
    def job(keys: Keys) -> WriteJob:
        j = copy.deepcopy(extra) if extra else WriteJob()
        j["kas"] = [_kas(keys, kid)]
        return j

    return job


def _attrs(*suffixes: str) -> Callable[[Keys], WriteJob]:
    fqns = [f"{corpus_kas.ATTR_BASE}/{s}" for s in suffixes]
    return lambda _keys: WriteJob(attributes=list(fqns))


def _split_two_kao(keys: Keys) -> WriteJob:
    return WriteJob(
        kas=[_kas(keys, "corpus-r2048"), _kas(keys, "corpus-r2048")],
        split=[{"kas": 0, "sid": "s-0"}, {"kas": 1, "sid": "s-1"}],
    )


def _handling_rs256(caveat: str, id: str = "handling-rs256") -> AssertionSpec:
    """The regenerated corpus's handling assertion. The signing key is added at
    write time; an x5c list, even empty, asks for the test leaf and its chain."""
    return {
        "kind": "handling",
        "alg": "RS256",
        "id": id,
        "scope": "payload",
        "applies_to_state": "unencrypted",
        "statement": {
            "format": "json",
            "schema": "urn:example:handling",
            "value": json.dumps({"caveat": caveat}, separators=(",", ":")),
        },
    }


RS256_X5C = _handling_rs256("x5c", "handling-rs256-x5c")
RS256_X5C["x5c"] = []
SYSTEM_METADATA: AssertionSpec = {"kind": "system-metadata"}
R2048 = "corpus-r2048"

VARIANTS: dict[str, Callable[[Keys], WriteJob]] = {
    "assertion-rs256": _wrapped(
        R2048, WriteJob(assertions=[_handling_rs256("conformance")])
    ),
    "assertion-rs256-x5c": _wrapped(R2048, WriteJob(assertions=[RS256_X5C])),
    "assertion-system-hs256": _wrapped(R2048, WriteJob(assertions=[SYSTEM_METADATA])),
    "attributes": _attrs("label/value/a"),
    "basic": _wrapped(R2048),
    "ec-wrapped": _wrapped("corpus-e256"),
    "empty": _wrapped(R2048),
    "hybrid-p256-mlkem768": _wrapped("corpus-p256mlkem768"),
    "hybrid-p384-mlkem1024": _wrapped("corpus-p384mlkem1024"),
    "hybrid-xwing": _wrapped("corpus-xwing"),
    "legacy-v4.2.2": _wrapped(R2048, WriteJob(target_mode="4.2.2")),
    "metadata-mimetype": _wrapped(
        R2048,
        WriteJob(
            mime_type="text/plain",
            encrypted_metadata='{"corpus":"metadata-mimetype"}',
        ),
    ),
    "mlkem1024": _wrapped("corpus-mlkem1024"),
    "mlkem768": _wrapped("corpus-mlkem768"),
    "multi-segment": _wrapped(R2048, WriteJob(segment_size=16 * 1024)),
    "split-allof-two-kas": _attrs("split-allof/value/km1", "split-allof/value/km2"),
    "split-anyof-two-kas": _attrs("split-anyof/value/km1", "split-anyof/value/km2"),
    "split-two-kao": _split_two_kao,
}

_HYBRIDS = {"hybrid-p256-mlkem768", "hybrid-p384-mlkem1024", "hybrid-xwing"}
_GO = sorted(set(VARIANTS) - {"assertion-rs256-x5c"})

# Fixture SDK label (sdk-<label>-<variant>) -> variants it writes.
WRITERS: dict[str, list[str]] = {
    "go": _GO,
    "java": sorted(VARIANTS),
    "web": [v for v in _GO if v not in _HYBRIDS],
}
# Fixture SDK label -> the xtest SDK whose writer produces it.
WRITER_SDK = {"go": "go", "java": "java", "web": "js"}

# Plaintext sizes match the regenerated corpus; the default is 1 KiB.
_SIZES = {
    "empty": 0,
    "multi-segment": 40 * 1024,
    "assertion-rs256-x5c": 132,
    "split-allof-two-kas": 132,
    "split-anyof-two-kas": 132,
    "mlkem768": 132,
    "mlkem1024": 132,
    **dict.fromkeys(_HYBRIDS, 132),
}


def plaintext_size(variant: str) -> int:
    return _SIZES.get(variant, 1024)


def job_for(sdk: str, variant: str, keys: Keys) -> WriteJob:
    """The job body for sdk-<sdk>-<variant>; out, plaintext and keys come later."""
    if variant not in WRITERS[sdk]:
        raise ValueError(f"{sdk} does not write {variant!r}")
    job = VARIANTS[variant](keys)
    if sdk == "java" and "split" in job:
        # The Java SDK names its own split ids.
        job["split"] = [{"kas": s["kas"]} for s in job["split"]]
    return job


@dataclass(frozen=True)
class Base:
    sdk: Literal["go", "web"]
    size: int
    job: Callable[[Keys], WriteJob]


TAMPER_BASES: dict[str, Base] = {
    "go-basic": Base("go", 132, _wrapped(R2048)),
    "go-assertion-hs256": Base(
        "go", 132, _wrapped(R2048, WriteJob(assertions=[SYSTEM_METADATA]))
    ),
    "go-assertion-rs256": Base(
        "go", 132, _wrapped(R2048, WriteJob(assertions=[_handling_rs256("corpus")]))
    ),
    "web-basic": Base("web", 165, _wrapped(R2048)),
    "web-multi-segment": Base("web", 165, _wrapped(R2048, WriteJob(segment_size=64))),
}

_ALPHABET = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,"


def plaintext(name: str, size: int) -> bytes:
    """Deterministic printable text for a fixture, seeded by its name."""
    raw = hashlib.shake_256(f"opentdf corpus plaintext {name}".encode()).digest(size)
    out = bytearray(_ALPHABET[b % len(_ALPHABET)] for b in raw)
    for i in range(63, size, 64):
        out[i] = 0x0A
    return bytes(out)
