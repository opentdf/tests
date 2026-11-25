"""Contract check for the static TDF corpus in xtest/corpus (offline)."""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import load_pem_x509_certificate

from corpus import (
    CORPUS_DIR,
    PREFIXES,
    SIDECAR_SUFFIX,
    fixtures,
    load_sidecar,
)

FIXTURES = fixtures()
SIDECARS = sorted(CORPUS_DIR.glob(f"*{SIDECAR_SUFFIX}"))
KAS_KEYS = CORPUS_DIR / "kas-keys.json"

KAS_KEY_FIELDS = ("kid", "alg", "privateKey", "cert", "kas")
EXPECTED_KAS_KEYS = {
    "corpus-r2048": ("rsa:2048", "km1"),
    "corpus-e256": ("ec:secp256r1", "km1"),
    "corpus-xwing": ("hpqt:xwing", "km1"),
    "corpus-p256mlkem768": ("hpqt:secp256r1-mlkem768", "km1"),
    "corpus-p384mlkem1024": ("hpqt:secp384r1-mlkem1024", "km1"),
    "corpus-mlkem768": ("mlkem:768", "km1"),
    "corpus-mlkem1024": ("mlkem:1024", "km1"),
    "corpus-r2048-b": ("rsa:2048", "km2"),
}


def _ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


def _bad(sidecar: str, key: str, value: object, why: str) -> AssertionError:
    return AssertionError(f"{sidecar}: bad {key} value {value!r}: {why}")


def _str_list(sidecar: str, raw: dict[str, Any], key: str) -> list[str]:
    values = raw.get(key, [])
    if not isinstance(values, list):
        raise _bad(sidecar, key, values, "expected a list of strings")
    for v in values:
        if not isinstance(v, str):
            raise _bad(sidecar, key, v, "expected a string")
    return values


def _split_ref(sidecar: str, key: str, value: str) -> str:
    """Path half of an `<id>=<path>` reference."""
    ident, sep, path = value.partition("=")
    if not sep or not ident or not path:
        raise _bad(sidecar, key, value, "expected <id>=<path>")
    return path


def _key_refs(sidecar: str, raw: dict[str, Any]) -> list[str]:
    """Key-file paths a sidecar references, relative to CORPUS_DIR."""
    refs: list[str] = []
    if "key" in raw:
        key = raw["key"]
        if not isinstance(key, str) or not key:
            raise _bad(sidecar, "key", key, "expected a non-empty path")
        refs.append(key)
    refs += [
        _split_ref(sidecar, "share_keys", v)
        for v in _str_list(sidecar, raw, "share_keys")
    ]
    for v in _str_list(sidecar, raw, "assertion_keys"):
        if not v:
            raise _bad(sidecar, "assertion_keys", v, "expected <path> or <id>=<path>")
        refs.append(_split_ref(sidecar, "assertion_keys", v) if "=" in v else v)
    return refs


def _sidecar_refs(sidecar: Path) -> list[str]:
    return _key_refs(sidecar.name, load_sidecar(sidecar).raw)


def _resolve_ref(ref: str) -> Path:
    assert ref, "empty key reference"
    path = (CORPUS_DIR / ref).resolve()
    assert path.is_relative_to(CORPUS_DIR.resolve()), f"{ref!r} escapes the corpus"
    assert path != CORPUS_DIR.resolve(), f"{ref!r} resolves to the corpus folder"
    return path


def test_key_refs_all_three_forms():
    raw = {
        "key": "keys/a.dek",
        "share_keys": ["s1=keys/b.dek", "s2=keys/c.dek"],
        "assertion_keys": ["keys/d.pem", "kid=keys/e.pem"],
    }
    assert _key_refs("x", raw) == [
        "keys/a.dek",
        "keys/b.dek",
        "keys/c.dek",
        "keys/d.pem",
        "keys/e.pem",
    ]


def test_key_refs_none():
    assert _key_refs("x", {"expect": "valid"}) == []


@pytest.mark.parametrize(
    "raw",
    [
        {"key": ""},
        {"key": 3},
        {"share_keys": ["keys/a.dek"]},
        {"share_keys": ["=keys/a.dek"]},
        {"share_keys": ["s1="]},
        {"share_keys": [3]},
        {"share_keys": "s1=keys/a.dek"},
        {"assertion_keys": [""]},
        {"assertion_keys": ["=keys/a.pem"]},
        {"assertion_keys": ["kid="]},
        {"assertion_keys": [None]},
        {"assertion_keys": "keys/a.pem"},
    ],
    ids=repr,
)
def test_key_refs_malformed(raw: dict[str, Any]):
    with pytest.raises(AssertionError, match="x.expect.toml.*bad"):
        _key_refs("x.expect.toml", raw)


@pytest.mark.parametrize("ref", ["", ".", "keys/..", "../x"])
def test_resolve_ref_rejects_bad_refs(ref: str):
    with pytest.raises(AssertionError):
        _resolve_ref(ref)


def test_corpus_is_not_empty():
    assert FIXTURES
    assert SIDECARS


@pytest.mark.parametrize("fixture", FIXTURES, ids=_ids(FIXTURES))
def test_every_fixture_has_a_sidecar(fixture: Path):
    sidecar = fixture.with_name(fixture.name + SIDECAR_SUFFIX)
    assert sidecar.is_file(), f"missing {sidecar.name}"


@pytest.mark.parametrize("sidecar", SIDECARS, ids=_ids(SIDECARS))
def test_every_sidecar_has_a_fixture(sidecar: Path):
    fixture = sidecar.with_name(sidecar.name.removesuffix(SIDECAR_SUFFIX))
    assert fixture.is_file(), f"no fixture for {sidecar.name}"


@pytest.mark.parametrize("sidecar", SIDECARS, ids=_ids(SIDECARS))
def test_sidecar_parses(sidecar: Path):
    load_sidecar(sidecar)


@pytest.mark.parametrize("fixture", FIXTURES, ids=_ids(FIXTURES))
def test_fixture_has_known_prefix(fixture: Path):
    matches = [p for p in PREFIXES if fixture.name.startswith(p)]
    assert len(matches) == 1, f"{fixture.name}: matching prefixes {matches}"


@pytest.mark.parametrize("sidecar", SIDECARS, ids=_ids(SIDECARS))
def test_referenced_key_files_exist(sidecar: Path):
    for ref in _sidecar_refs(sidecar):
        assert _resolve_ref(ref).is_file(), f"missing key file {ref}"


def test_no_orphan_key_files():
    referenced = {_resolve_ref(ref) for sc in SIDECARS for ref in _sidecar_refs(sc)}
    present = {
        p.resolve()
        for p in (CORPUS_DIR / "keys").rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }
    root = CORPUS_DIR.resolve()
    orphans = sorted(str(p.relative_to(root)) for p in present - referenced)
    assert not orphans, f"key files no sidecar references: {orphans}"


def _is_valid_tdf(sidecar: Path) -> bool:
    raw = load_sidecar(sidecar).raw
    return raw.get("expect") == "valid" and raw.get("format") == "tdf"


VALID_TDF_SIDECARS = [p for p in SIDECARS if _is_valid_tdf(p)]


def test_some_valid_tdf_fixture_exists():
    assert VALID_TDF_SIDECARS


@pytest.mark.parametrize("sidecar", VALID_TDF_SIDECARS, ids=_ids(VALID_TDF_SIDECARS))
def test_valid_fixtures_open_as_tdf(sidecar: Path):
    fixture = sidecar.with_name(sidecar.name.removesuffix(SIDECAR_SUFFIX))
    with zipfile.ZipFile(fixture) as z:
        names = z.namelist()
    assert "0.manifest.json" in names
    assert "0.payload" in names


def _public_der(key: Any) -> bytes:
    return key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_kas_keys_well_formed():
    entries = json.loads(KAS_KEYS.read_text())
    assert isinstance(entries, list), "kas-keys.json must be a JSON list"
    for entry in entries:
        assert isinstance(entry, dict), f"entry is not an object: {entry!r}"
    for entry in entries:
        assert entry.get("kid"), f"entry has no kid: {sorted(entry)}"
        for field in KAS_KEY_FIELDS:
            assert entry.get(field), f"{entry['kid']}: missing {field}"
    assert len(entries) == len(EXPECTED_KAS_KEYS)
    assert {e["kid"] for e in entries} == set(EXPECTED_KAS_KEYS)
    for entry in entries:
        alg, kas = EXPECTED_KAS_KEYS[entry["kid"]]
        assert (entry["alg"], entry["kas"]) == (alg, kas), entry["kid"]
        if alg.startswith(("rsa:", "ec:")):
            private = serialization.load_pem_private_key(
                entry["privateKey"].encode(), password=None
            )
            cert = load_pem_x509_certificate(entry["cert"].encode())
            assert _public_der(cert.public_key()) == _public_der(
                private.public_key()
            ), f"{entry['kid']}: cert does not match privateKey"
