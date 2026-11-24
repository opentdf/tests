"""Contract check for the static TDF corpus in xtest/corpus (offline)."""

import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import load_pem_x509_certificate

from corpus import (
    CORPUS_DIR,
    PREFIXES,
    SIDECAR_SUFFIX,
    Sidecar,
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


def _key_refs(sc: Sidecar) -> list[str]:
    """Key-file paths a sidecar references, relative to CORPUS_DIR."""
    raw = sc.raw
    refs: list[str] = []
    if "key" in raw:
        refs.append(raw["key"])
    refs += [v.partition("=")[2] for v in raw.get("share_keys", [])]
    for v in raw.get("assertion_keys", []):
        refs.append(v.partition("=")[2] if "=" in v else v)
    return refs


def _resolve_ref(ref: str) -> Path:
    path = (CORPUS_DIR / ref).resolve()
    assert path.is_relative_to(CORPUS_DIR.resolve()), f"{ref!r} escapes the corpus"
    return path


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
    for ref in _key_refs(load_sidecar(sidecar)):
        assert _resolve_ref(ref).is_file(), f"missing key file {ref}"


def test_no_orphan_key_files():
    referenced = {
        _resolve_ref(ref) for sc in SIDECARS for ref in _key_refs(load_sidecar(sc))
    }
    present = {
        p.resolve()
        for p in (CORPUS_DIR / "keys").rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }
    orphans = sorted(p.name for p in present - referenced)
    assert not orphans, f"key files no sidecar references: {orphans}"


@pytest.mark.parametrize("sidecar", SIDECARS, ids=_ids(SIDECARS))
def test_valid_fixtures_open_as_tdf(sidecar: Path):
    sc = load_sidecar(sidecar)
    if sc.raw.get("expect") != "valid":
        pytest.skip("not expected valid")
    with zipfile.ZipFile(sc.fixture) as z:
        names = z.namelist()
    assert "0.manifest.json" in names
    assert "0.payload" in names


def _public_der(key: object) -> bytes:
    return key.public_bytes(  # type: ignore[attr-defined]
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


@pytest.mark.skipif(
    not KAS_KEYS.exists(), reason="xtest/corpus/kas-keys.json does not exist yet"
)
def test_kas_keys_well_formed():
    entries = json.loads(KAS_KEYS.read_text())
    assert isinstance(entries, list)
    for entry in entries:
        for field in KAS_KEY_FIELDS:
            assert entry.get(field), f"{entry.get('kid')}: missing {field}"
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
