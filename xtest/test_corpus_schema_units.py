"""Offline tests for corpus sidecar parsing and per-SDK verdict resolution."""

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import abac
import corpus
import corpus_kas
from corpus import DecryptHung, SidecarError, load_sidecar, resolve_verdict

HASH = "a" * 64
ALL_SDKS = (
    f'plaintext_sha256 = "{HASH}"\ngo = "decrypt"\njava = "decrypt"\njs = "decrypt"\n'
)
JS_LIST = f"""
[sdk]
plaintext_sha256 = "{HASH}"
go = "decrypt"
java = "decrypt"
js = [
  {{verdict="decrypt", before="0.24.0"}},
  {{verdict="reject", platform_before="0.32.0"}},
  {{verdict="decrypt"}},
]
"""


def write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "a.tdf.expect.toml"
    p.write_text(body)
    return p


def table(tmp_path: Path, body: str = JS_LIST) -> corpus.SdkTable:
    sdk = load_sidecar(write(tmp_path, body)).sdk
    assert sdk is not None
    return sdk


def test_unknown_top_level_key_rejected(tmp_path: Path):
    with pytest.raises(SidecarError, match="bogus"):
        load_sidecar(write(tmp_path, "bogus = 1\n"))


def test_unknown_sdk_key_rejected(tmp_path: Path):
    with pytest.raises(SidecarError, match="rust"):
        load_sidecar(write(tmp_path, f'[sdk]\n{ALL_SDKS}rust = "decrypt"\n'))


def test_sdk_requires_all_three(tmp_path: Path):
    with pytest.raises(SidecarError, match="java"):
        load_sidecar(write(tmp_path, '[sdk]\ngo = "decrypt"\n'))


def test_bad_verdict_rejected(tmp_path: Path):
    body = '[sdk]\ngo = "maybe"\njava = "decrypt"\njs = "decrypt"\n'
    with pytest.raises(SidecarError, match="maybe"):
        load_sidecar(write(tmp_path, body))


def test_malformed_bound_rejected(tmp_path: Path):
    body = (
        '[sdk]\ngo = [{verdict="reject", before="nope"}, {verdict="decrypt"}]\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )
    with pytest.raises(SidecarError, match="before"):
        load_sidecar(write(tmp_path, body))


@pytest.mark.parametrize("bad", ["0.24.0bogus", "0.24.0.1", "0.24.0-rc1"])
@pytest.mark.parametrize("key", corpus.BOUND_KEYS)
def test_inexact_semver_bound_rejected(tmp_path: Path, key: str, bad: str):
    body = (
        f'[sdk]\ngo = [{{verdict="reject", {key}="{bad}"}}, {{verdict="decrypt"}}]\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )
    with pytest.raises(SidecarError, match=key):
        load_sidecar(write(tmp_path, body))


def test_v_prefixed_bound_accepted(tmp_path: Path):
    body = (
        f'[sdk]\nplaintext_sha256 = "{HASH}"\n'
        'go = [{verdict="reject", before="v0.24.0"}, {verdict="decrypt"}]\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )
    assert table(tmp_path, body).verdicts["go"][0].before == (0, 24, 0)


def test_toml_syntax_error_wrapped(tmp_path: Path):
    p = write(tmp_path, "expect = \n")
    with pytest.raises(SidecarError, match="a.tdf.expect.toml"):
        load_sidecar(p)


def test_inverted_bounds_rejected(tmp_path: Path):
    body = (
        '[sdk]\ngo = [{verdict="reject", since="0.25.0", before="0.24.0"},'
        ' {verdict="decrypt"}]\njava = "decrypt"\njs = "decrypt"\n'
    )
    with pytest.raises(SidecarError, match="since"):
        load_sidecar(write(tmp_path, body))


def test_last_entry_must_be_unbounded(tmp_path: Path):
    body = (
        '[sdk]\ngo = [{verdict="reject", before="0.24.0"}]\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )
    with pytest.raises(SidecarError, match="unbounded"):
        load_sidecar(write(tmp_path, body))


def test_earlier_unbounded_entry_rejected(tmp_path: Path):
    body = (
        f'[sdk]\nplaintext_sha256 = "{HASH}"\n'
        'go = [{verdict="reject"}, {verdict="decrypt", before="0.24.0"},'
        ' {verdict="decrypt"}]\njava = "decrypt"\njs = "decrypt"\n'
    )
    with pytest.raises(SidecarError, match="unbounded"):
        load_sidecar(write(tmp_path, body))


def test_second_table_rejected(tmp_path: Path):
    with pytest.raises(SidecarError, match="unknown key 'other'"):
        load_sidecar(write(tmp_path, f"[sdk]\n{ALL_SDKS}\n[other]\nx = 1\n"))


def test_whitelisted_key_as_table_rejected(tmp_path: Path):
    with pytest.raises(SidecarError, match="'key'"):
        load_sidecar(write(tmp_path, "[key]\nx = 1\n"))


def test_whitelisted_key_as_array_of_tables_rejected(tmp_path: Path):
    with pytest.raises(SidecarError, match="'assertion_keys'"):
        load_sidecar(write(tmp_path, "[[assertion_keys]]\nx = 1\n"))


def test_sdk_must_come_last(tmp_path: Path):
    body = (
        f'sdk = {{plaintext_sha256 = "{HASH}", go = "reject", java = "reject", '
        'js = "reject"}\nexpect = "invalid"\n'
    )
    with pytest.raises(SidecarError, match="after all top-level"):
        load_sidecar(write(tmp_path, body))


def test_decrypt_requires_plaintext_hash(tmp_path: Path):
    body = '[sdk]\ngo = "decrypt"\njava = "reject"\njs = "reject"\n'
    with pytest.raises(SidecarError, match="plaintext_sha256"):
        load_sidecar(write(tmp_path, body))


@pytest.mark.parametrize("bad", ["A" * 64, "a" * 63, "zz" * 32])
def test_bad_plaintext_hash_rejected(tmp_path: Path, bad: str):
    body = (
        f'[sdk]\nplaintext_sha256 = "{bad}"\n'
        'go = "reject"\njava = "reject"\njs = "reject"\n'
    )
    with pytest.raises(SidecarError, match="plaintext_sha256"):
        load_sidecar(write(tmp_path, body))


def test_non_string_note_rejected(tmp_path: Path):
    body = '[sdk]\nnote = 1\ngo = "reject"\njava = "reject"\njs = "reject"\n'
    with pytest.raises(SidecarError, match="note"):
        load_sidecar(write(tmp_path, body))


def test_all_reject_needs_no_hash(tmp_path: Path):
    body = '[sdk]\ngo = "reject"\njava = "reject"\njs = "reject"\n'
    assert table(tmp_path, body).plaintext_sha256 is None


def test_bare_string_becomes_unbounded_entry(tmp_path: Path):
    body = f'[sdk]\nnote = "n"\n{ALL_SDKS}'
    sc = load_sidecar(write(tmp_path, body))
    assert sc.fixture == tmp_path / "a.tdf"
    assert sc.sdk is not None
    assert sc.sdk.plaintext_sha256 == HASH
    assert sc.sdk.verdicts["go"] == [corpus.Bounded("decrypt", None, None, None, None)]


def test_no_sdk_table_is_none(tmp_path: Path):
    sc = load_sidecar(write(tmp_path, 'expect = "valid"\n'))
    assert sc.sdk is None
    assert sc.raw == {"expect": "valid"}


def test_resolve_first_match(tmp_path: Path):
    t = table(tmp_path)
    assert resolve_verdict(t, "js", (0, 23, 0), (0, 31, 0)) == "decrypt"
    assert resolve_verdict(t, "js", (0, 24, 0), (0, 31, 0)) == "reject"
    assert resolve_verdict(t, "js", (0, 24, 0), (0, 32, 0)) == "decrypt"


def test_branch_build_skips_upper_bounded_sdk_entries(tmp_path: Path):
    assert resolve_verdict(table(tmp_path), "js", None, (0, 31, 0)) == "reject"


def test_branch_build_platform_skips_platform_before(tmp_path: Path):
    assert resolve_verdict(table(tmp_path), "js", None, None) == "decrypt"


def test_since_is_inclusive_before_exclusive(tmp_path: Path):
    body = (
        f'[sdk]\nplaintext_sha256 = "{HASH}"\n'
        'go = [{verdict="reject", since="0.24.0", before="0.25.0"},'
        ' {verdict="decrypt"}]\njava = "decrypt"\njs = "decrypt"\n'
    )
    t = table(tmp_path, body)
    assert resolve_verdict(t, "go", (0, 23, 9), None) == "decrypt"
    assert resolve_verdict(t, "go", (0, 24, 0), None) == "reject"
    assert resolve_verdict(t, "go", (0, 25, 0), None) == "decrypt"


def test_resolve_unknown_sdk_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError, match="rust"):
        resolve_verdict(table(tmp_path), "rust", None, None)


def test_platform_since_inclusive_and_excluded_below(tmp_path: Path):
    body = (
        f'[sdk]\nplaintext_sha256 = "{HASH}"\n'
        'go = [{verdict="reject", platform_since="0.31.0"}, {verdict="decrypt"}]\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )
    t = table(tmp_path, body)
    assert resolve_verdict(t, "go", (0, 24, 0), (0, 30, 9)) == "decrypt"
    assert resolve_verdict(t, "go", (0, 24, 0), (0, 31, 0)) == "reject"
    assert resolve_verdict(t, "go", (0, 24, 0), (0, 32, 0)) == "reject"


def test_since_only_entry_matches_branch_build(tmp_path: Path):
    body = (
        f'[sdk]\nplaintext_sha256 = "{HASH}"\n'
        'go = [{verdict="reject", since="0.24.0"}, {verdict="decrypt"}]\n'
        'java = "decrypt"\njs = "decrypt"\n'
    )
    assert resolve_verdict(table(tmp_path, body), "go", None, None) == "reject"


@pytest.mark.parametrize(
    "version", ["0.31.0-14-gabcdef", "v0.32.0-rc.1", "0.31.0-dev", "0.31.0.1"]
)
def test_platform_semver_non_release_is_none(
    monkeypatch: pytest.MonkeyPatch, version: str
):
    monkeypatch.delenv("PLATFORM_TAG", raising=False)
    monkeypatch.setenv("PLATFORM_VERSION", version)
    assert corpus.platform_semver() is None


@pytest.mark.parametrize("version", ["0.31.0", "v0.31.0"])
def test_platform_semver_release(monkeypatch: pytest.MonkeyPatch, version: str):
    monkeypatch.delenv("PLATFORM_TAG", raising=False)
    monkeypatch.setenv("PLATFORM_VERSION", version)
    assert corpus.platform_semver() == (0, 31, 0)


def test_platform_semver_branch_tag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_VERSION", "0.31.0")
    monkeypatch.setenv("PLATFORM_TAG", "main")
    assert corpus.platform_semver() is None
    monkeypatch.setenv("PLATFORM_TAG", "v0.31.0")
    assert corpus.platform_semver() == (0, 31, 0)
    monkeypatch.delenv("PLATFORM_TAG")
    assert corpus.platform_semver() == (0, 31, 0)


def test_classify_outcome(tmp_path: Path):
    out = tmp_path / "out"
    empty = hashlib.sha256(b"").hexdigest()
    assert corpus.classify_outcome(1, out, empty) == "reject"
    assert corpus.classify_outcome(0, out, empty) == "wrong-plaintext"
    out.write_bytes(b"")
    assert corpus.classify_outcome(0, out, empty) == "decrypt"
    out.write_bytes(b"x")
    assert corpus.classify_outcome(0, out, empty) == "wrong-plaintext"
    assert corpus.classify_outcome(0, out, None) == "decrypt"


def test_fixtures_skips_dotfiles(tmp_path: Path):
    for name in (".DS_Store", "a.tdf"):
        (tmp_path / name).write_bytes(b"")
    assert [p.name for p in corpus.fixtures(tmp_path)] == ["a.tdf"]


def test_fixtures_skips_subdirs_and_meta(tmp_path: Path):
    (tmp_path / "keys").mkdir()
    for name in (
        "keys/a.dek",
        "README.md",
        "kas-keys.json",
        "a.tdf",
        "a.tdf.expect.toml",
        "a.bin",
    ):
        (tmp_path / name).write_bytes(b"")
    assert [p.name for p in corpus.fixtures(tmp_path)] == ["a.bin", "a.tdf"]


def test_decrypt_timeout_is_an_error():
    start = time.monotonic()
    with pytest.raises(DecryptHung):
        corpus.run_decrypt(["sleep", "5"], {}, timeout=0.2)
    assert time.monotonic() - start < 2


def _wait_gone(pid: int) -> bool:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    os.kill(pid, 9)
    return False


def _spawn_grandchild(pidfile: Path) -> list[str]:
    return ["sh", "-c", 'sleep 30 & echo $! > "$1"; wait', "sh", str(pidfile)]


def test_decrypt_timeout_kills_process_group(tmp_path: Path):
    pidfile = tmp_path / "pid"
    with pytest.raises(DecryptHung):
        corpus.run_decrypt(_spawn_grandchild(pidfile), {}, timeout=0.5)
    assert _wait_gone(int(pidfile.read_text())), "grandchild survived the timeout"


def test_decrypt_interrupt_kills_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pidfile = tmp_path / "pid"
    real = corpus.subprocess.Popen.communicate
    calls = 0

    def interrupt_first(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            deadline = time.monotonic() + 5
            while not pidfile.exists() or not pidfile.read_text().strip():
                if time.monotonic() > deadline:
                    raise AssertionError(f"{pidfile} was never written")
                time.sleep(0.01)
            raise KeyboardInterrupt
        return real(self, *args, **kwargs)

    monkeypatch.setattr(corpus.subprocess.Popen, "communicate", interrupt_first)
    with pytest.raises(KeyboardInterrupt):
        corpus.run_decrypt(_spawn_grandchild(pidfile), {}, timeout=5)
    assert _wait_gone(int(pidfile.read_text())), "grandchild survived the interrupt"


class FakeOtdfctl:
    """In-memory otdfctl double covering the calls corpus_kas makes."""

    def __init__(self) -> None:
        self.keys: dict[str, list[abac.KasKey]] = {}
        self.namespaces: list[abac.Namespace] = []
        self.attributes: list[abac.Attribute] = []
        self.imports: list[dict[str, Any]] = []
        self.assigned: list[tuple[str, str]] = []
        self.mapped: list[str] = []
        self.fail_first_import = False
        self.fail_first_attr = False
        self.value_keys: dict[str, list[str]] = {}
        self.mappings: list[tuple[str, str]] = []

    def kas_registry_keys_list(self, kas: abac.KasEntry) -> list[abac.KasKey]:
        return list(self.keys.get(kas.uri, []))

    def add_key(self, kas: abac.KasEntry, kid: str, pem: str) -> abac.KasKey:
        k = abac.KasKey(
            kas_id=kas.id,
            kas_uri=kas.uri,
            key=abac.KasKeyResponseKeyDetails(
                id=f"id-{kid}",
                key_id=kid,
                key_algorithm=1,
                key_status=1,
                key_mode=1,
                public_key_ctx=abac.KasKeyResponsePublicKeyContext(pem=pem),
            ),
        )
        self.keys.setdefault(kas.uri, []).append(k)
        return k

    def kas_registry_import_key(
        self, kas: abac.KasEntry, public_pem: str, key_id: str, **kw: Any
    ) -> abac.KasKey:
        self.imports.append({"kas": kas.uri, "key_id": key_id, **kw})
        key = self.add_key(kas, key_id, public_pem)
        if self.fail_first_import:
            self.fail_first_import = False
            raise AssertionError("Key import failed: key already exists")
        return key

    def namespace_list(self) -> list[abac.Namespace]:
        return list(self.namespaces)

    def namespace_create(self, name: str) -> abac.Namespace:
        ns = abac.Namespace(id=f"ns-{name}", name=name, fqn=f"https://{name}")
        self.namespaces.append(ns)
        return ns

    def attribute_list(self) -> list[abac.Attribute]:
        return list(self.attributes)

    def attribute_create(
        self,
        namespace: abac.Namespace,
        name: str,
        t: abac.AttributeRule,
        values: list[str],
    ) -> abac.Attribute:
        fqn = f"{namespace.fqn}/attr/{name}"
        attr = abac.Attribute(
            id=f"attr-{name}",
            namespace=namespace,
            name=name,
            rule=t,
            fqn=fqn,
            values=[
                abac.AttributeValue(id=f"v-{name}-{v}", value=v, fqn=f"{fqn}/value/{v}")
                for v in values
            ],
        )
        self.attributes.append(attr)
        if self.fail_first_attr:
            self.fail_first_attr = False
            raise AssertionError("attribute already exists")
        return attr

    def key_assign_value(self, key: abac.KasKey, val: abac.AttributeValue) -> None:
        self.assigned.append((key.key.key_id, val.fqn or ""))
        self.value_keys.setdefault(val.id, []).append(key.key.key_id)

    def scs_map(self, sc: Any, value: abac.AttributeValue) -> None:
        self.mapped.append(value.fqn or "")
        self.mappings.append((value.id, sc.id))

    def attribute_value_get(self, value_id: str) -> abac.AttributeValue:
        return abac.AttributeValue(
            id=value_id,
            value="",
            kas_keys=[
                abac.ValueKasKey(
                    kas_uri="http://localhost:8585",
                    public_key=abac.ValueKasKeyPublic(kid=kid),
                )
                for kid in self.value_keys.get(value_id, [])
            ],
        )

    def scs_map_list(self) -> list[abac.SubjectMapping]:
        return [
            abac.SubjectMapping(
                id=f"sm{i}",
                attribute_value=abac.AttributeValue(id=vid, value=""),
                subject_condition_set=abac.SubjectConditionSet(id=sid, subject_sets=[]),
                actions=[],
            )
            for i, (vid, sid) in enumerate(self.mappings)
        ]


def _kas(name: str, port: int) -> abac.KasEntry:
    return abac.KasEntry(
        id=f"kas-{name}", uri=f"http://localhost:{port}", public_key=None
    )


@pytest.fixture
def two_kas() -> tuple[abac.KasEntry, abac.KasEntry]:
    return _kas("km1", 8585), _kas("km2", 8686)


def _pem(kid: str) -> str:
    return corpus_kas.registry_pem(corpus.kas_keys()[kid])


def test_existing_kid_with_other_key_raises(two_kas):
    km1, km2 = two_kas
    fake = FakeOtdfctl()
    fake.add_key(km1, "corpus-r2048", _pem("corpus-r2048-b"))
    with pytest.raises(corpus_kas.CorpusKeyMismatch) as ei:
        corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    assert "corpus-r2048" in str(ei.value)


def test_import_uses_stable_settings(two_kas):
    km1, km2 = two_kas
    fake = FakeOtdfctl()
    keys = corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    assert set(keys) == set(corpus.kas_keys())
    assert len(fake.imports) == 8
    for imp in fake.imports:
        assert imp["legacy"] is False
        assert imp["wrapping_key_id"] == "root"
    on = {i["key_id"]: i["kas"] for i in fake.imports}
    assert on["corpus-r2048-b"] == km2.uri
    assert on["corpus-xwing"] == km1.uri
    corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    assert len(fake.imports) == 8


def test_create_race_reuses_existing(two_kas):
    km1, km2 = two_kas
    fake = FakeOtdfctl()
    fake.fail_first_import = True
    keys = corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    assert set(keys) == set(corpus.kas_keys())


def test_create_race_with_other_key_raises(two_kas):
    km1, km2 = two_kas

    class Rival(FakeOtdfctl):
        def kas_registry_import_key(self, kas, public_pem, key_id, **kw):
            pem = _pem("corpus-r2048-b") if key_id == "corpus-r2048" else public_pem
            self.add_key(kas, key_id, pem)
            raise AssertionError("Key import failed: already_exists")

    with pytest.raises(corpus_kas.CorpusKeyMismatch):
        corpus_kas.ensure_corpus_keys(Rival(), km1, km2, "rootkey")


def test_ensure_attributes_creates_and_maps(two_kas):
    km1, km2 = two_kas
    fake = FakeOtdfctl()
    keys = corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    scs = abac.SubjectConditionSet(id="scs", subject_sets=[])
    vals = corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    base = "https://corpus.opentdf.example/attr"
    assert set(vals) == {
        f"{base}/split-allof/value/km1",
        f"{base}/split-allof/value/km2",
        f"{base}/split-anyof/value/km1",
        f"{base}/split-anyof/value/km2",
        f"{base}/label/value/a",
    }
    assert sorted(fake.mapped) == sorted(vals)
    assigned = {fqn: kid for kid, fqn in fake.assigned}
    assert assigned[f"{base}/split-allof/value/km2"] == "corpus-r2048-b"
    assert assigned[f"{base}/split-anyof/value/km1"] == "corpus-r2048"
    assert assigned[f"{base}/label/value/a"] == "corpus-r2048"
    assert {a.name: a.rule for a in fake.attributes} == {
        "split-allof": abac.AttributeRule.ALL_OF,
        "split-anyof": abac.AttributeRule.ANY_OF,
        "label": abac.AttributeRule.ANY_OF,
    }
    n_attrs, n_maps = len(fake.attributes), len(fake.mapped)
    corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    assert (len(fake.attributes), len(fake.mapped)) == (n_attrs, n_maps)


def test_attribute_create_race_reuses_existing(two_kas):
    km1, km2 = two_kas
    fake = FakeOtdfctl()
    keys = corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    fake.fail_first_attr = True
    scs = abac.SubjectConditionSet(id="scs", subject_sets=[])
    vals = corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    assert len(vals) == 5
    assert len(fake.attributes) == 3


def test_public_matches_accepts_base64_registry_pem():
    import base64

    for kid, entry in corpus.kas_keys().items():
        pem = corpus_kas.registry_pem(entry)
        assert corpus_kas.public_matches(entry, pem), kid
        assert corpus_kas.public_matches(
            entry, base64.b64encode(pem.encode()).decode()
        ), kid
    assert not corpus_kas.public_matches(
        corpus.kas_keys()["corpus-r2048"], _pem("corpus-r2048-b")
    )


def _setup_unmapped(two_kas):
    km1, km2 = two_kas
    fake = FakeOtdfctl()
    keys = corpus_kas.ensure_corpus_keys(fake, km1, km2, "rootkey")
    scs = abac.SubjectConditionSet(id="scs", subject_sets=[])
    # Interrupted earlier run: attributes exist, nothing mapped.
    fake.fail_first_attr = False
    corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    fake.assigned.clear()
    fake.mapped.clear()
    fake.value_keys.clear()
    fake.mappings.clear()
    return fake, keys, scs


def test_existing_unmapped_attributes_get_mapped(two_kas):
    fake, keys, scs = _setup_unmapped(two_kas)
    n_attrs = len(fake.attributes)
    vals = corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    assert len(fake.attributes) == n_attrs
    assert sorted(fake.mapped) == sorted(vals)
    assert len(fake.assigned) == 5
    assert len(fake.mappings) == len(set(fake.mappings)) == 5


def test_fully_mapped_attributes_make_no_calls(two_kas):
    fake, keys, scs = _setup_unmapped(two_kas)
    corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    n_attrs = len(fake.attributes)
    fake.assigned.clear()
    fake.mapped.clear()
    corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    assert (len(fake.attributes), fake.assigned, fake.mapped) == (n_attrs, [], [])


def test_value_mapped_to_wrong_key_raises(two_kas):
    fake, keys, scs = _setup_unmapped(two_kas)
    val = next(
        v
        for a in fake.attributes
        for v in a.values or []
        if v.fqn and v.fqn.endswith("split-allof/value/km2")
    )
    fake.value_keys[val.id] = ["corpus-r2048"]
    with pytest.raises(corpus_kas.CorpusValueMismatch) as ei:
        corpus_kas.ensure_corpus_attributes(fake, scs, keys)
    msg = str(ei.value)
    assert "split-allof/value/km2" in msg
    assert "corpus-r2048" in msg and "corpus-r2048-b" in msg


KEYS_BY_KID: Any = {
    "k-xwing": {"alg": "hpqt:xwing"},
    "k-secp": {"alg": "hpqt:secp256r1-mlkem768"},
}


def manifest(*kaos: dict[str, str], attrs: list[str] | None = None) -> dict[str, Any]:
    policy = {"body": {"dataAttributes": [{"attribute": a} for a in attrs or []]}}
    return {
        "encryptionInformation": {
            "keyAccess": list(kaos),
            "policy": base64.b64encode(json.dumps(policy).encode()).decode(),
        }
    }


@pytest.mark.parametrize(
    ("kao", "expected"),
    [
        ({"type": "wrapped"}, []),
        ({"type": "ec-wrapped"}, ["ecwrap"]),
        ({"type": "mlkem-wrapped", "kid": "x"}, ["mechanism-mlkem"]),
        ({"type": "hybrid-wrapped", "kid": "k-xwing"}, ["mechanism-xwing"]),
        ({"type": "hybrid-wrapped", "kid": "k-secp"}, ["mechanism-secpmlkem"]),
        ({"type": "hybrid-wrapped", "kid": "unknown"}, []),
    ],
)
def test_required_features_by_kao(kao: dict[str, str], expected: list[str]):
    assert corpus.required_features(manifest(kao), KEYS_BY_KID) == expected


def test_required_features_dedupes_and_tolerates_no_manifest():
    two = manifest({"type": "ec-wrapped"}, {"type": "ec-wrapped"})
    assert corpus.required_features(two, KEYS_BY_KID) == ["ecwrap"]
    assert corpus.required_features(None, KEYS_BY_KID) == []


def test_has_data_attributes():
    assert corpus.has_data_attributes(manifest(attrs=["https://x/attr/a/value/b"]))
    assert not corpus.has_data_attributes(manifest())
    assert not corpus.has_data_attributes(None)


def test_read_manifest_none_for_non_zip(tmp_path: Path):
    p = tmp_path / "x.tdf"
    p.write_bytes(b"not a zip")
    assert corpus.read_manifest(p) is None
    assert corpus.read_manifest(tmp_path / "missing.tdf") is None


def test_assertion_verification_keys(tmp_path: Path):
    pem = (
        rsa.generate_private_key(65537, 2048)
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    (tmp_path / "a.pem").write_text(pem)
    m = {"assertions": [{"id": "one"}, {"id": "two"}]}
    both = {"alg": "RS256", "key": pem}
    got = corpus.assertion_verification_keys({"assertion_keys": ["a.pem"]}, m, tmp_path)
    assert got == {"keys": {"one": both, "two": both}}
    named = corpus.assertion_verification_keys(
        {"assertion_keys": ["x=a.pem"]}, None, tmp_path
    )
    assert named == {"keys": {"x": both}}
    assert corpus.assertion_verification_keys({}, m, tmp_path) is None
    bare = {"assertion_keys": ["a.pem"]}
    assert corpus.assertion_verification_keys(bare, None, tmp_path) is None


def test_output_sha256_hashes_file_or_none(tmp_path: Path):
    out = tmp_path / "out.bin"
    out.write_bytes(b"plaintext")
    assert corpus.output_sha256(out) == hashlib.sha256(b"plaintext").hexdigest()
    assert corpus.output_sha256(tmp_path / "missing.bin") is None


def test_make_record_carries_output_hash(tmp_path: Path):
    out = tmp_path / "out.bin"
    out.write_bytes(b"abc")
    rec = corpus.make_record(
        fixture="f.tdf", sdk="go", version="main", outcome="decrypt", out=out
    )
    assert rec["output_sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert rec["fixture"] == "f.tdf" and rec["outcome"] == "decrypt"
    out.unlink()
    rec = corpus.make_record(
        fixture="f.tdf", sdk="go", version="main", outcome="reject", out=out
    )
    assert "output_sha256" in rec and rec["output_sha256"] is None


def test_append_record_one_line_each(tmp_path: Path):
    p = tmp_path / "rec.jsonl"
    corpus.append_record(p, {"fixture": "a", "outcome": "decrypt"})
    corpus.append_record(p, {"fixture": "b", "outcome": "reject"})
    rows = [json.loads(line) for line in p.read_text().splitlines()]
    assert [r["fixture"] for r in rows] == ["a", "b"]
