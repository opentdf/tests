"""Offline tests for corpus sidecar parsing and per-SDK verdict resolution."""

import hashlib
import time
from pathlib import Path

import pytest

import corpus
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
    with pytest.raises(SidecarError, match="go"):
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
