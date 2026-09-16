# TDF Container Spec Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every SDK in the workspace write `manifest.json` at the zip root, locate the payload entry from `manifest.payload.url`, read legacy `0.manifest.json` archives forever, and resolve the spec version with the priority `schemaVersion` > `tdf_spec_version` > `payload.tdf_spec_version`.

**Architecture:** Each SDK gets one pair of resolver functions (manifest entry name, payload entry name) that every read path calls, and one pair of constants that every write path uses so the zip entry name and `payload.url` can never diverge. The manifest model in each SDK gains decode-only `tdf_spec_version` fields and a prioritized accessor. The test harness gets the same resolvers plus a new stage-1 container-layout test gated on a new `spec-container` capability.

**Tech Stack:** Python 3 / `zipfile` / pytest (`uv run pytest`); Rust / `zip` 2.2 / serde (`cargo test`); Swift / ZIPFoundation / XCTest (`swift test`); Go 1.25 / custom `zipstream` / testify (`go test`); harness is pytest + pydantic.

**Spec:** `opentdf-tests/docs/superpowers/specs/2026-09-16-tdf-container-spec-compliance-design.md`

## Global Constraints

- Manifest zip entry written by every SDK: exactly `manifest.json`, at the archive root.
- Manifest zip entry accepted on read: `manifest.json` first, then `0.manifest.json`. Both accepted permanently.
- Payload zip entry written: `0.payload`. The manifest's `payload.url` MUST be produced from the same constant as the zip entry name.
- Payload zip entry on read: `manifest.payload.url` when non-empty. Fallback to `0.payload` only when `url` is empty or absent. A non-empty `url` naming a missing entry is an error that quotes the URL.
- Unsafe `payload.url` (contains `..` as a path segment, starts with `/`, or contains `\`) is rejected before any zip lookup.
- Version key written: `schemaVersion` only, value `4.3.0`. No SDK writes `tdf_spec_version` anywhere.
- Version read priority: `schemaVersion`, then top-level `tdf_spec_version`, then `payload.tdf_spec_version`. First non-empty wins. All three absent means legacy.
- Do not regenerate binary fixtures that contain `0.manifest.json` (Rust `tests/data/sensitive.txt.tdf`, harness `xtest/golden/*.tdf`). They are the legacy-read regression tests.
- Out of scope: Rust `N.manifest.json` for `N > 0`, the Rust gguf profile and `TdfMultiEntryBuilder`, TDF-JSON, TDF-CBOR, NanoTDF, integrity verification, assertions, `sid`.
- Community-encrypt / upstream-Go-decrypt cells in the harness stage-1 lanes are expected to fail after this change. Do not "fix" that by reverting the writer.
- Each repo is its own git repository. Create branch `tdf-container-spec-compliance` in each before the first commit there. Commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

Repo roots used below:

| Alias | Path |
|---|---|
| PY | `/Users/arkavo/Projects/opentdf/opentdf-python-sdk` |
| RS | `/Users/arkavo/Projects/opentdf/opentdf-rs` |
| SW | `/Users/arkavo/Projects/opentdf/OpenTDFKit` |
| GO | `/Users/arkavo/Projects/opentdf/opentdf-platform` |
| XT | `/Users/arkavo/Projects/opentdf/opentdf-tests` |

---

## Python SDK

### Task 1: Python entry-name resolvers and `TDFReader`

**Files:**
- Modify: `PY/packages/otdf-python/src/otdf_python/tdf_reader.py:1-45`
- Test: `PY/tests/test_tdf_reader.py`

**Interfaces:**
- Produces (module `otdf_python.tdf_reader`):
  - `TDF_MANIFEST_FILE_NAME: str = "manifest.json"`
  - `LEGACY_TDF_MANIFEST_FILE_NAME: str = "0.manifest.json"`
  - `TDF_PAYLOAD_FILE_NAME: str = "0.payload"`
  - `resolve_manifest_name(names: Iterable[str]) -> str` raises `ValueError("tdf doesn't contain a manifest")`
  - `resolve_payload_name(payload_url: str | None, names: Iterable[str]) -> str` raises `ValueError`
  - `payload_url_from_manifest_json(manifest_text: str) -> str | None`
  - `TDFReader` unchanged public API; internally uses the resolvers.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && git checkout -b tdf-container-spec-compliance
```

- [ ] **Step 2: Write the failing resolver tests**

Append to `PY/tests/test_tdf_reader.py`:

```python
import pytest
from otdf_python.tdf_reader import (
    LEGACY_TDF_MANIFEST_FILE_NAME,
    payload_url_from_manifest_json,
    resolve_manifest_name,
    resolve_payload_name,
)


class TestEntryNameResolvers:
    def test_manifest_prefers_spec_name(self):
        names = ["0.manifest.json", "manifest.json", "0.payload"]
        assert resolve_manifest_name(names) == "manifest.json"

    def test_manifest_falls_back_to_legacy_name(self):
        assert resolve_manifest_name(["0.manifest.json", "0.payload"]) == "0.manifest.json"

    def test_manifest_missing(self):
        with pytest.raises(ValueError, match="tdf doesn't contain a manifest"):
            resolve_manifest_name(["0.payload"])

    def test_payload_from_url(self):
        assert resolve_payload_name("data.bin", ["manifest.json", "data.bin"]) == "data.bin"

    def test_payload_url_missing_entry_is_error_and_quotes_url(self):
        with pytest.raises(ValueError, match="'data.bin'"):
            resolve_payload_name("data.bin", ["manifest.json", "0.payload"])

    def test_payload_fallback_when_url_empty(self):
        assert resolve_payload_name("", ["manifest.json", "0.payload"]) == "0.payload"
        assert resolve_payload_name(None, ["manifest.json", "0.payload"]) == "0.payload"

    def test_payload_fallback_missing(self):
        with pytest.raises(ValueError, match="tdf doesn't contain a payload"):
            resolve_payload_name(None, ["manifest.json"])

    @pytest.mark.parametrize("bad", ["../x", "/abs", "a\\b", "x/../y"])
    def test_payload_unsafe_url_rejected(self, bad):
        with pytest.raises(ValueError, match="unsafe"):
            resolve_payload_name(bad, ["manifest.json", bad])

    def test_payload_url_from_manifest_json(self):
        assert payload_url_from_manifest_json('{"payload": {"url": "p.bin"}}') == "p.bin"
        assert payload_url_from_manifest_json('{"payload": {}}') is None
        assert payload_url_from_manifest_json("{}") is None
        assert payload_url_from_manifest_json("not json") is None


class TestTDFReaderEntryResolution:
    def _reader_with(self, names, manifest_text):
        with patch("otdf_python.tdf_reader.ZipReader") as mock_zip_reader:
            inst = mock_zip_reader.return_value
            inst.namelist.return_value = names
            inst.read.side_effect = lambda n: (
                manifest_text.encode() if n.endswith("manifest.json") else b"PAYLOAD"
            )
            reader = TDFReader(io.BytesIO(b"x"))
            return reader, inst

    def test_reads_legacy_manifest_name(self):
        reader, inst = self._reader_with(
            ["0.manifest.json", "0.payload"], '{"payload": {"url": "0.payload"}}'
        )
        assert reader.manifest() == '{"payload": {"url": "0.payload"}}'
        inst.read.assert_called_with(LEGACY_TDF_MANIFEST_FILE_NAME)

    def test_payload_name_comes_from_manifest_url(self):
        reader, inst = self._reader_with(
            ["manifest.json", "custom.bin"], '{"payload": {"url": "custom.bin"}}'
        )
        buf = bytearray(7)
        assert reader.read_payload_bytes(buf) == 7
        inst.read.assert_called_with("custom.bin")

    def test_payload_url_missing_entry_fails_at_init(self):
        with pytest.raises(ValueError, match="'custom.bin'"):
            self._reader_with(
                ["manifest.json", "0.payload"], '{"payload": {"url": "custom.bin"}}'
            )
```

- [ ] **Step 3: Run the new tests to confirm they fail**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_tdf_reader.py -v`
Expected: FAIL with `ImportError: cannot import name 'LEGACY_TDF_MANIFEST_FILE_NAME'`.

- [ ] **Step 4: Implement the resolvers and rewire `TDFReader.__init__`**

Replace lines 1-45 of `PY/packages/otdf-python/src/otdf_python/tdf_reader.py` (everything up to and including the `except` block of `__init__`) with:

```python
"""TDFReader is responsible for reading and processing Trusted Data Format (TDF) files."""

import json
from collections.abc import Iterable

from .manifest import Manifest
from .policy_object import PolicyObject
from .sdk_exceptions import SDKException
from .zip_reader import ZipReader

# Spec (opentdf/spec schema/OpenTDF/README.md): the manifest entry MUST be
# `manifest.json` at the archive root. `0.manifest.json` is what every SDK
# wrote before this change and is accepted forever on read.
TDF_MANIFEST_FILE_NAME = "manifest.json"
LEGACY_TDF_MANIFEST_FILE_NAME = "0.manifest.json"
# Payload entry name. Written by TDFWriter and into manifest.payload.url.
# On read this is only a fallback for manifests with an empty payload.url.
TDF_PAYLOAD_FILE_NAME = "0.payload"


def resolve_manifest_name(names: Iterable[str]) -> str:
    """Return the zip entry holding the manifest, spec name first."""
    name_set = set(names)
    for candidate in (TDF_MANIFEST_FILE_NAME, LEGACY_TDF_MANIFEST_FILE_NAME):
        if candidate in name_set:
            return candidate
    raise ValueError("tdf doesn't contain a manifest")


def _is_safe_entry_name(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name:
        return False
    return ".." not in name.split("/")


def resolve_payload_name(payload_url: str | None, names: Iterable[str]) -> str:
    """Return the zip entry holding the payload.

    Uses manifest.payload.url when present; falls back to `0.payload` only
    when the url is empty or missing.
    """
    name_set = set(names)
    if payload_url:
        if not _is_safe_entry_name(payload_url):
            raise ValueError(f"unsafe payload url in manifest: {payload_url!r}")
        if payload_url in name_set:
            return payload_url
        raise ValueError(f"tdf doesn't contain payload entry {payload_url!r}")
    if TDF_PAYLOAD_FILE_NAME in name_set:
        return TDF_PAYLOAD_FILE_NAME
    raise ValueError("tdf doesn't contain a payload")


def payload_url_from_manifest_json(manifest_text: str) -> str | None:
    """Extract payload.url without requiring a fully valid manifest."""
    try:
        data = json.loads(manifest_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    url = payload.get("url")
    return url if isinstance(url, str) else None


class TDFReader:
    """TDFReader is responsible for reading and processing Trusted Data Format (TDF) files.

    The class initializes with a TDF file channel, extracts the manifest and payload entries,
    and provides methods to retrieve the manifest content, read payload bytes, and read policy objects.
    """

    def __init__(self, tdf):
        """Initialize a TDFReader with a TDF file channel.

        Args:
            tdf: A file-like object containing the TDF data

        Raises:
            SDKException: If there's an error reading the TDF
            ValueError: If the TDF doesn't contain a manifest or payload

        """
        try:
            self._zip_reader = ZipReader(tdf)
            namelist = self._zip_reader.namelist()
            self._manifest_name = resolve_manifest_name(namelist)
            manifest_text = self._zip_reader.read(self._manifest_name).decode("utf-8")
            payload_url = payload_url_from_manifest_json(manifest_text)
            self._payload_name = resolve_payload_name(payload_url, namelist)
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise SDKException("Error initializing TDFReader") from e
```

Keep the rest of the file (`manifest()`, `read_payload_bytes()`, `read_policy_object()`) unchanged.

- [ ] **Step 5: Fix the existing mock fixture so its manifest is valid JSON with no url**

In `PY/tests/test_tdf_reader.py`, the existing `mock_zip_reader` fixture already returns `{"test": "manifest"}`, which has no `payload.url`, so the reader falls back to `0.payload`. No change needed there. But `test_init_success` asserts `namelist.assert_called_once()`; `__init__` still calls it once. Leave as is.

- [ ] **Step 6: Run the reader tests**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_tdf_reader.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk
git add packages/otdf-python/src/otdf_python/tdf_reader.py tests/test_tdf_reader.py
git commit -m "feat(tdf): resolve manifest.json and payload.url on read, keep legacy fallback

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 2: Python `load_tdf`, `read_payload`, and `is_tdf` use the resolvers

**Files:**
- Modify: `PY/packages/otdf-python/src/otdf_python/tdf.py:436,467,490,513`
- Modify: `PY/packages/otdf-python/src/otdf_python/sdk.py:365-380`
- Test: `PY/tests/test_tdf.py`, `PY/tests/test_sdk.py`

**Interfaces:**
- Consumes: `resolve_manifest_name`, `resolve_payload_name`, `payload_url_from_manifest_json` from Task 1.

- [ ] **Step 1: Write the failing tests**

Append to `PY/tests/test_tdf.py`:

```python
def _make_tdf_bytes(tdf, payload, config):
    _, _, out = tdf.create_tdf(payload, config)
    return out.getvalue() if hasattr(out, "getvalue") else out.read()


def _rewrite_zip(data: bytes, rename: dict[str, str], manifest_edit=None) -> bytes:
    """Copy a zip, renaming entries and optionally editing the manifest JSON."""
    src = zipfile.ZipFile(io.BytesIO(data))
    dst_buf = io.BytesIO()
    with zipfile.ZipFile(dst_buf, "w") as dst:
        for name in src.namelist():
            content = src.read(name)
            if name.endswith("manifest.json") and manifest_edit:
                m = json.loads(content)
                manifest_edit(m)
                content = json.dumps(m).encode()
            dst.writestr(rename.get(name, name), content)
    return dst_buf.getvalue()


def test_load_tdf_reads_legacy_manifest_name():
    tdf = TDF()
    kas_private_key, kas_public_key = generate_rsa_keypair()
    kas_info = KASInfo(url="https://kas.example.com", public_key=kas_public_key, kid="k")
    config = TDFConfig(kas_info_list=[kas_info], tdf_private_key=kas_private_key)
    data = _make_tdf_bytes(tdf, b"legacy", config)
    legacy = _rewrite_zip(data, {"manifest.json": "0.manifest.json"})
    with zipfile.ZipFile(io.BytesIO(legacy)) as z:
        assert "0.manifest.json" in z.namelist()
    decrypted = tdf.load_tdf(legacy, TDFReaderConfig(kas_private_key=kas_private_key))
    assert decrypted.payload == b"legacy"


def test_load_tdf_locates_payload_by_manifest_url():
    tdf = TDF()
    kas_private_key, kas_public_key = generate_rsa_keypair()
    kas_info = KASInfo(url="https://kas.example.com", public_key=kas_public_key, kid="k")
    config = TDFConfig(kas_info_list=[kas_info], tdf_private_key=kas_private_key)
    data = _make_tdf_bytes(tdf, b"renamed", config)

    def set_url(m):
        m["payload"]["url"] = "data.bin"

    renamed = _rewrite_zip(data, {"0.payload": "data.bin"}, manifest_edit=set_url)
    decrypted = tdf.load_tdf(renamed, TDFReaderConfig(kas_private_key=kas_private_key))
    assert decrypted.payload == b"renamed"


def test_load_tdf_rejects_unsafe_payload_url():
    tdf = TDF()
    kas_private_key, kas_public_key = generate_rsa_keypair()
    kas_info = KASInfo(url="https://kas.example.com", public_key=kas_public_key, kid="k")
    config = TDFConfig(kas_info_list=[kas_info], tdf_private_key=kas_private_key)
    data = _make_tdf_bytes(tdf, b"x", config)

    def set_url(m):
        m["payload"]["url"] = "../0.payload"

    bad = _rewrite_zip(data, {}, manifest_edit=set_url)
    with pytest.raises(ValueError, match="unsafe"):
        tdf.load_tdf(bad, TDFReaderConfig(kas_private_key=kas_private_key))
```

Append to `PY/tests/test_sdk.py` (add `import io`, `import json`, `import zipfile` at the top if missing; `SDK` is already imported there). `is_tdf` is a `@staticmethod`, so call it on the class:

```python
def _zip_with(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return buf.getvalue()


def test_is_tdf_accepts_spec_layout():
    manifest = json.dumps({"payload": {"url": "0.payload"}}).encode()
    assert SDK.is_tdf(_zip_with({"manifest.json": manifest, "0.payload": b"x"}))


def test_is_tdf_accepts_legacy_layout():
    manifest = json.dumps({"payload": {"url": "0.payload"}}).encode()
    assert SDK.is_tdf(_zip_with({"0.manifest.json": manifest, "0.payload": b"x"}))


def test_is_tdf_accepts_extra_entries_and_custom_payload_name():
    manifest = json.dumps({"payload": {"url": "blob"}}).encode()
    assert SDK.is_tdf(
        _zip_with({"manifest.json": manifest, "blob": b"x", "extra.txt": b"y"})
    )


def test_is_tdf_rejects_missing_payload_entry():
    manifest = json.dumps({"payload": {"url": "blob"}}).encode()
    assert not SDK.is_tdf(_zip_with({"manifest.json": manifest, "0.payload": b"x"}))
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_tdf.py tests/test_sdk.py -v -k "legacy or manifest_url or unsafe or is_tdf"`
Expected: `test_load_tdf_locates_payload_by_manifest_url` and `test_load_tdf_rejects_unsafe_payload_url` FAIL (`KeyError: "There is no item named '0.payload' in the archive"` and no `ValueError`), and the three `is_tdf` spec-layout tests FAIL (return False). `test_load_tdf_reads_legacy_manifest_name` already PASSES because the writer still emits `0.manifest.json` until Task 3; its rename is a no-op today and it becomes a real regression test after Task 3.

- [ ] **Step 3: Rewire `tdf.py`**

At the top of `PY/packages/otdf-python/src/otdf_python/tdf.py` add:

```python
from otdf_python.tdf_reader import resolve_manifest_name, resolve_payload_name
```

In `load_tdf` replace

```python
        with zipfile.ZipFile(tdf_bytes_io, "r") as z:
            manifest_json = z.read("0.manifest.json").decode()
            manifest = Manifest.from_json(manifest_json)
```

with

```python
        with zipfile.ZipFile(tdf_bytes_io, "r") as z:
            names = z.namelist()
            manifest_json = z.read(resolve_manifest_name(names)).decode()
            manifest = Manifest.from_json(manifest_json)
```

and replace

```python
            encrypted_payload = z.read("0.payload")
            payload = self._decrypt_segments(aesgcm, segments, encrypted_payload)
```

with

```python
            payload_url = manifest.payload.url if manifest.payload else None
            encrypted_payload = z.read(resolve_payload_name(payload_url, names))
            payload = self._decrypt_segments(aesgcm, segments, encrypted_payload)
```

In `read_payload` make the same two substitutions: the `z.read("0.manifest.json")` line becomes `names = z.namelist()` followed by `manifest_json = z.read(resolve_manifest_name(names)).decode()`, and `encrypted_payload = z.read("0.payload")` becomes the two-line `payload_url` / `resolve_payload_name` form above.

- [ ] **Step 4: Rewire `is_tdf` in `sdk.py`**

Replace the body of `is_tdf` (the `try:` block at `sdk.py:365-380`) with:

```python
        import json
        import zipfile
        from io import BytesIO

        from otdf_python.tdf_reader import resolve_manifest_name, resolve_payload_name

        try:
            file_like = BytesIO(data) if isinstance(data, bytes | bytearray) else data
            with zipfile.ZipFile(file_like) as zf:
                names = zf.namelist()
                manifest_name = resolve_manifest_name(names)
                manifest = json.loads(zf.read(manifest_name))
                payload = manifest.get("payload") if isinstance(manifest, dict) else None
                url = payload.get("url") if isinstance(payload, dict) else None
                resolve_payload_name(url, names)
                return True
        except Exception:
            return False
```

- [ ] **Step 5: Run the tests**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_tdf.py tests/test_sdk.py tests/test_tdf_reader.py -v`
Expected: the new tests PASS. `test_tdf_create_and_load` still PASSES because the writer still emits `0.manifest.json` until Task 3.

- [ ] **Step 6: Commit**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk
git add packages/otdf-python/src/otdf_python/tdf.py packages/otdf-python/src/otdf_python/sdk.py tests/test_tdf.py tests/test_sdk.py
git commit -m "feat(tdf): load paths and is_tdf resolve entry names from the manifest

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: Python writer emits `manifest.json`, derives `payload.url`, manifest gains version accessor

**Files:**
- Modify: `PY/packages/otdf-python/src/otdf_python/tdf_writer.py:11-12`
- Modify: `PY/packages/otdf-python/src/otdf_python/tdf.py:400-410`
- Modify: `PY/packages/otdf-python/src/otdf_python/manifest.py:81-89,113-118,166-170,231-239`
- Modify tests: `PY/tests/test_tdf_writer.py`, `PY/tests/test_tdf.py:31-35`, `PY/tests/test_tdf_key_management.py:93,97`, `PY/tests/test_manifest.py`, `PY/tests/integration/test_cli_tdf_validation.py:93-101`
- Test: `PY/tests/test_manifest_format.py`

**Interfaces:**
- Produces: `Manifest.tdf_spec_version: str | None`, `ManifestPayload.tdf_spec_version: str | None`, `Manifest.spec_version() -> str | None`.
- `TDFWriter.TDF_MANIFEST_FILE_NAME == "manifest.json"`, `TDFWriter.TDF_PAYLOAD_FILE_NAME == "0.payload"`.

- [ ] **Step 1: Write the failing writer and version tests**

In `PY/tests/test_tdf_writer.py` change both `z.read("0.manifest.json")` calls (lines 25 and 37) to `z.read("manifest.json")`. Then append inside `TestTDFWriter`:

```python
    def test_manifest_entry_is_spec_name(self):
        writer = TDFWriter()
        writer.append_manifest("{}")
        with writer.payload() as f:
            f.write(b"x")
        writer.finish()
        with zipfile.ZipFile(io.BytesIO(writer.getvalue()), "r") as z:
            self.assertEqual(sorted(z.namelist()), ["0.payload", "manifest.json"])
            self.assertNotIn("0.manifest.json", z.namelist())
```

In `PY/tests/test_tdf.py::test_tdf_create_and_load` replace lines 31-35 with:

```python
        assert "manifest.json" in files
        assert "0.manifest.json" not in files
        manifest_json = json.loads(z.read("manifest.json").decode())
        assert manifest_json["schemaVersion"] == TDF.TDF_VERSION
        assert "tdf_spec_version" not in manifest_json
        assert "tdf_spec_version" not in manifest_json["payload"]
        assert manifest_json["payload"]["url"] in files
        encrypted_payload = z.read(manifest_json["payload"]["url"])
```

Append to `PY/tests/test_manifest_format.py`:

```python
from otdf_python.manifest import Manifest


def _minimal(**top):
    base = {
        "payload": {
            "type": "reference",
            "url": "0.payload",
            "protocol": "zip",
            "mimeType": "text/plain",
            "isEncrypted": True,
        }
    }
    base.update(top)
    return base


def test_spec_version_prefers_schema_version():
    m = _minimal(schemaVersion="4.3.0", tdf_spec_version="9.9.9")
    m["payload"]["tdf_spec_version"] = "8.8.8"
    assert Manifest.from_json(json.dumps(m)).spec_version() == "4.3.0"


def test_spec_version_falls_back_to_top_level_tdf_spec_version():
    m = _minimal(tdf_spec_version="9.9.9")
    m["payload"]["tdf_spec_version"] = "8.8.8"
    assert Manifest.from_json(json.dumps(m)).spec_version() == "9.9.9"


def test_spec_version_falls_back_to_payload_tdf_spec_version():
    m = _minimal()
    m["payload"]["tdf_spec_version"] = "8.8.8"
    assert Manifest.from_json(json.dumps(m)).spec_version() == "8.8.8"


def test_spec_version_absent_is_none():
    assert Manifest.from_json(json.dumps(_minimal())).spec_version() is None


def test_tdf_spec_version_never_serialized():
    m = _minimal(schemaVersion="4.3.0", tdf_spec_version="9.9.9")
    m["payload"]["tdf_spec_version"] = "8.8.8"
    out = json.loads(Manifest.from_json(json.dumps(m)).to_json())
    assert "tdf_spec_version" not in out
    assert "tdf_spec_version" not in out["payload"]
    assert out["schemaVersion"] == "4.3.0"
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_tdf_writer.py tests/test_tdf.py tests/test_manifest_format.py -v`
Expected: FAIL. Writer tests get `KeyError: manifest.json`; format tests get `TypeError: ManifestPayload.__init__() got an unexpected keyword argument 'tdf_spec_version'` and `AttributeError: 'Manifest' object has no attribute 'spec_version'`.

- [ ] **Step 3: Change the writer constants**

In `PY/packages/otdf-python/src/otdf_python/tdf_writer.py` replace lines 11-12 with:

```python
    # Spec: manifest entry MUST be `manifest.json` at the archive root.
    TDF_MANIFEST_FILE_NAME = "manifest.json"
    # Payload entry name; TDF.create_tdf writes this same value into manifest.payload.url.
    TDF_PAYLOAD_FILE_NAME = "0.payload"
```

- [ ] **Step 4: Derive `payload.url` from the constant**

In `PY/packages/otdf-python/src/otdf_python/tdf.py` inside `create_tdf`, change

```python
            url="0.payload",
```

to

```python
            url=TDFWriter.TDF_PAYLOAD_FILE_NAME,
```

- [ ] **Step 5: Add the version fields and accessor to the manifest model**

In `PY/packages/otdf-python/src/otdf_python/manifest.py`:

Change `ManifestPayload` to:

```python
@dataclass
class ManifestPayload:
    """Payload information in TDF manifest."""

    type: str
    url: str
    protocol: str
    mimeType: str
    isEncrypted: bool
    # Read-only: some spec revisions place the version here. Never written.
    tdf_spec_version: str | None = None
```

Change the `Manifest` field block to:

```python
    schemaVersion: str | None = None
    encryptionInformation: ManifestEncryptionInformation | None = None
    payload: ManifestPayload | None = None
    assertions: list[ManifestAssertion] = field(default_factory=list)
    # Read-only: spec prose places tdf_spec_version at the top level. Never written.
    tdf_spec_version: str | None = None

    def spec_version(self) -> str | None:
        """Resolve the spec version: schemaVersion, then tdf_spec_version, then payload.tdf_spec_version."""
        if self.schemaVersion:
            return self.schemaVersion
        if self.tdf_spec_version:
            return self.tdf_spec_version
        if self.payload and self.payload.tdf_spec_version:
            return self.payload.tdf_spec_version
        return None
```

In `to_json`, the `payload` branch currently does `manifest_dict["payload"] = asdict(self.payload)`. Change it to:

```python
        if self.payload is not None:
            payload_dict = asdict(self.payload)
            payload_dict.pop("tdf_spec_version", None)
            manifest_dict["payload"] = payload_dict
```

`to_json` never adds the top-level `tdf_spec_version` key, so nothing else is needed on the write side.

In `from_json`, change the final `return Manifest(...)` to include the new field:

```python
        return Manifest(
            schemaVersion=d.get("schemaVersion", d.get("tdf_version")),
            tdf_spec_version=d.get("tdf_spec_version"),
            encryptionInformation=_enc_info(
                d.get("encryptionInformation", d.get("encryption_information"))
            )
            if d.get("encryptionInformation") or d.get("encryption_information")
            else None,
            payload=_payload(d["payload"]) if d.get("payload") else None,
            assertions=[_assertion(a) for a in d.get("assertions", [])],
        )
```

`_payload(p)` is `ManifestPayload(**p)`, which now accepts `tdf_spec_version`.

- [ ] **Step 6: Update the remaining tests that hard-code the old manifest name**

- `PY/tests/test_tdf_key_management.py:93`: change `zf.writestr("0.manifest.json", manifest.to_json())` to `zf.writestr("manifest.json", manifest.to_json())`.
- `PY/tests/integration/test_cli_tdf_validation.py:93-101`: replace the `required_files = [TDF_MANIFEST_FILE_NAME, TDF_PAYLOAD_FILE_NAME]` loop and `zip_file.read(TDF_MANIFEST_FILE_NAME)` with:

```python
        names = zip_file.namelist()
        assert TDF_MANIFEST_FILE_NAME in names, f"Missing {TDF_MANIFEST_FILE_NAME} in {names}"
        manifest_content = zip_file.read(TDF_MANIFEST_FILE_NAME)
        manifest_data = json.loads(manifest_content)
        assert manifest_data["payload"]["url"] in names
```

Keep the import line at the top of that file; `TDF_MANIFEST_FILE_NAME` now resolves to `manifest.json`.

- [ ] **Step 7: Run the whole unit suite**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/ -v -m "not integration"`
Expected: all PASS. Then run `uv run ruff check . && uv run ruff format --check .` and fix any formatting.

- [ ] **Step 8: Commit**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk
git add -A packages/otdf-python/src/otdf_python tests
git commit -m "feat(tdf): write manifest.json, derive payload.url from writer constant, add spec_version()

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 4: Python CLI advertises `spec-container`

**Files:**
- Modify: `PY/packages/otdf-python/src/otdf_python/cli.py:206-236`
- Test: `PY/tests/test_cli_supports.py`

- [ ] **Step 1: Write the failing test**

Append to `PY/tests/test_cli_supports.py` (match the file's existing style for invoking `cmd_supports`; it already tests other features, so copy the pattern of one existing test):

```python
def test_supports_spec_container():
    from types import SimpleNamespace

    from otdf_python.cli import cmd_supports

    assert cmd_supports(SimpleNamespace(feature="spec-container")) == 0
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_cli_supports.py -v -k spec_container`
Expected: FAIL, returns 2 (unknown feature).

- [ ] **Step 3: Add the feature**

In `cli.py`, add `"spec-container",` to both `_SUPPORTED_FEATURES` and `_KNOWN_FEATURES` (alphabetical position, after `"obligations"` in `_KNOWN_FEATURES` and after `"kasallowlist"` in `_SUPPORTED_FEATURES`). Add a comment above `_SUPPORTED_FEATURES`:

```python
# "spec-container": writes manifest.json at the zip root and resolves the
# payload entry from manifest.payload.url (opentdf/spec container rules).
```

- [ ] **Step 4: Run and commit**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/test_cli_supports.py -v`
Expected: PASS.

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk
git add packages/otdf-python/src/otdf_python/cli.py tests/test_cli_supports.py
git commit -m "feat(cli): advertise spec-container capability

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Rust SDK

### Task 5: Rust manifest version accessor and `schemaVersion` 4.3.0

**Files:**
- Modify: `RS/crates/protocol/src/manifest.rs:14-28,244-280`
- Modify: `RS/src/manifest.rs:214-262` (test expecting `"3.0.0"`)
- Modify: `RS/examples/xtest_cli.rs:342-343`
- Test: `RS/crates/protocol/src/manifest.rs` (inline tests)

**Interfaces:**
- Produces: `TdfManifest::spec_version(&self) -> Option<&str>`; `TdfManifest::new` sets `schema_version = Some("4.3.0")`; new `pub const TDF_SPEC_VERSION: &str = "4.3.0";` in `crates/protocol/src/manifest.rs`, re-exported from `src/manifest.rs`.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-rs && git checkout -b tdf-container-spec-compliance
```

- [ ] **Step 2: Write the failing tests**

Append inside the existing `#[cfg(test)] mod gguf_index_tests` block in `RS/crates/protocol/src/manifest.rs` (or add a sibling `mod spec_version_tests`):

```rust
    fn minimal_json(top: &str, payload_extra: &str) -> String {
        format!(
            r#"{{
            "payload": {{"type":"reference","url":"0.payload","protocol":"zip","isEncrypted":true{payload_extra}}},
            "encryptionInformation": {{
                "type":"split","keyAccess":[],
                "method":{{"algorithm":"AES-256-GCM","isStreamable":true,"iv":""}},
                "integrityInformation":{{"rootSignature":{{"alg":"HS256","sig":""}},"segmentHashAlg":"GMAC","segments":[],"segmentSizeDefault":0,"encryptedSegmentSizeDefault":0}},
                "policy":""
            }}{top}
        }}"#
        )
    }

    #[test]
    fn spec_version_prefers_schema_version() {
        let m = TdfManifest::from_json(&minimal_json(
            r#","schemaVersion":"4.3.0","tdf_spec_version":"9.9.9""#,
            r#","tdf_spec_version":"8.8.8""#,
        ))
        .unwrap();
        assert_eq!(m.spec_version(), Some("4.3.0"));
    }

    #[test]
    fn spec_version_then_top_level_tdf_spec_version() {
        let m = TdfManifest::from_json(&minimal_json(
            r#","tdf_spec_version":"9.9.9""#,
            r#","tdf_spec_version":"8.8.8""#,
        ))
        .unwrap();
        assert_eq!(m.spec_version(), Some("9.9.9"));
    }

    #[test]
    fn spec_version_then_payload_tdf_spec_version() {
        let m = TdfManifest::from_json(&minimal_json("", r#","tdf_spec_version":"8.8.8""#)).unwrap();
        assert_eq!(m.spec_version(), Some("8.8.8"));
    }

    #[test]
    fn spec_version_absent_is_none() {
        let m = TdfManifest::from_json(&minimal_json("", "")).unwrap();
        assert_eq!(m.spec_version(), None);
    }

    #[test]
    fn new_manifest_writes_schema_version_4_3_0_and_no_tdf_spec_version() {
        let m = TdfManifest::new("0.payload".to_string(), "https://kas.example.com".to_string());
        let v: serde_json::Value = serde_json::from_str(&m.to_json().unwrap()).unwrap();
        assert_eq!(v["schemaVersion"], TDF_SPEC_VERSION);
        assert_eq!(v["schemaVersion"], "4.3.0");
        assert!(v.get("tdf_spec_version").is_none());
        assert!(v["payload"].get("tdf_spec_version").is_none());
    }
```

- [ ] **Step 3: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-rs && cargo test -p opentdf-protocol spec_version 2>&1 | tail -20`
(Use the actual package name from `crates/protocol/Cargo.toml` if it differs.)
Expected: compile error, `no method named spec_version` and `cannot find value TDF_SPEC_VERSION`.

- [ ] **Step 4: Implement**

In `RS/crates/protocol/src/manifest.rs`, above `pub struct TdfManifest` add:

```rust
/// The TDF spec version written into `schemaVersion` by every writer.
pub const TDF_SPEC_VERSION: &str = "4.3.0";
```

Inside `impl TdfManifest`, after `new`, add:

```rust
    /// Resolve the spec version a peer wrote, in priority order:
    /// root `schemaVersion` (what every SDK writes), then root `tdf_spec_version`
    /// (spec prose), then `payload.tdf_spec_version` (spec JSON schema).
    pub fn spec_version(&self) -> Option<&str> {
        [
            self.schema_version.as_deref(),
            self.tdf_spec_version.as_deref(),
            self.payload.tdf_spec_version.as_deref(),
        ]
        .into_iter()
        .flatten()
        .find(|v| !v.is_empty())
    }
```

In `new`, change `schema_version: Some("3.0.0".to_string()),` to `schema_version: Some(TDF_SPEC_VERSION.to_string()),`.

In `RS/src/manifest.rs` add `TDF_SPEC_VERSION` to the `pub use` re-export list at lines 12-15, and in `test_payload_omits_tdf_spec_version_by_default` change `Some("3.0.0")` to `Some("4.3.0")`.

In `RS/examples/xtest_cli.rs:342-343` delete the line `manifest.schema_version = Some("4.3.0".to_string());` and its comment line about `go@main hexless default` (the constructor now sets it).

- [ ] **Step 5: Run and commit**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-rs && cargo test --workspace 2>&1 | grep -E "^test result|FAILED|panicked" | head -20`
Expected: all `ok`.

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-rs
git add crates/protocol/src/manifest.rs src/manifest.rs examples/xtest_cli.rs
git commit -m "feat(manifest): spec_version() read priority; write schemaVersion 4.3.0

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 6: Rust archive reader resolves entry names; builders write `manifest.json`

**Files:**
- Modify: `RS/src/archive.rs:331-401` (reader), `:417-471` (file builder), `:497-549` (memory builder), `:570-673` (inline tests)
- Modify: `RS/tests/integration.rs:85-106`
- Modify: `RS/examples/xtest_cli.rs` (`supports`)
- Test: `RS/src/archive.rs` inline tests, `RS/tests/integration.rs`

**Interfaces:**
- Produces in `src/archive.rs`: `pub const TDF_MANIFEST_FILE_NAME: &str = "manifest.json";`, `pub const LEGACY_TDF_MANIFEST_FILE_NAME: &str = "0.manifest.json";`, `pub const TDF_PAYLOAD_FILE_NAME: &str = "0.payload";`. Re-export all three from `src/lib.rs` next to `TdfArchive`.
- `TdfArchive::len()` counts manifest entries instead of dividing by two.
- Builders write the payload under `manifest.payload.url` (falling back to `{index}.payload` when empty).

- [ ] **Step 1: Write the failing tests**

Replace the inline `mod tests` in `RS/src/archive.rs` (lines 570-673) with:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Cursor, Write};
    use tempfile::NamedTempFile;
    use zip::write::FileOptions;

    fn manifest_with_url(url: &str) -> TdfManifest {
        TdfManifest::new(url.to_string(), "http://kas.example.com".to_string())
    }

    fn create_test_archive() -> Result<Vec<u8>, TdfError> {
        let manifest = manifest_with_url("0.payload");
        let payload = b"test payload data".to_vec();
        let temp_file = NamedTempFile::new()?;
        let mut builder = TdfArchiveBuilder::new(temp_file.path())?;
        builder.add_entry(&manifest, &payload, 0)?;
        builder.finish()?;
        Ok(std::fs::read(temp_file.path())?)
    }

    /// Hand-build a zip with arbitrary member names, bypassing TdfArchiveBuilder.
    fn raw_zip(members: &[(&str, &[u8])]) -> Vec<u8> {
        let mut w = ZipWriter::new(Cursor::new(Vec::new()));
        for (name, data) in members {
            w.start_file::<_, ()>(
                *name,
                FileOptions::default().compression_method(zip::CompressionMethod::Stored),
            )
            .unwrap();
            w.write_all(data).unwrap();
        }
        w.finish().unwrap().into_inner()
    }

    fn names_of(bytes: &[u8]) -> Vec<String> {
        let mut z = ZipArchive::new(Cursor::new(bytes.to_vec())).unwrap();
        (0..z.len()).map(|i| z.by_index(i).unwrap().name().to_string()).collect()
    }

    #[test]
    fn builder_writes_spec_manifest_name_and_payload_from_url() -> Result<(), TdfError> {
        let bytes = create_test_archive()?;
        let names = names_of(&bytes);
        assert!(names.contains(&"manifest.json".to_string()), "{names:?}");
        assert!(!names.contains(&"0.manifest.json".to_string()), "{names:?}");
        assert!(names.contains(&"0.payload".to_string()), "{names:?}");
        Ok(())
    }

    #[test]
    fn builder_payload_entry_follows_manifest_url() -> Result<(), TdfError> {
        let temp_file = NamedTempFile::new()?;
        let mut builder = TdfArchiveBuilder::new(temp_file.path())?;
        builder.add_entry(&manifest_with_url("data.bin"), b"abc", 0)?;
        builder.finish()?;
        let bytes = std::fs::read(temp_file.path())?;
        assert_eq!(names_of(&bytes), vec!["manifest.json", "data.bin"]);
        let mut archive = TdfArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.by_index()?.payload, b"abc");
        Ok(())
    }

    #[test]
    fn memory_builder_matches_file_builder_names() -> Result<(), TdfError> {
        let mut b = TdfArchiveMemoryBuilder::new();
        b.add_entry(&manifest_with_url("0.payload"), b"x", 0)?;
        let bytes = b.finish()?;
        assert_eq!(names_of(&bytes), vec!["manifest.json", "0.payload"]);
        Ok(())
    }

    #[test]
    fn reader_accepts_legacy_manifest_name() -> Result<(), TdfError> {
        let m = manifest_with_url("0.payload").to_json()?;
        let bytes = raw_zip(&[("0.manifest.json", m.as_bytes()), ("0.payload", b"legacy")]);
        let mut archive = TdfArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.len(), 1);
        assert_eq!(archive.by_index()?.payload, b"legacy");
        Ok(())
    }

    #[test]
    fn reader_prefers_spec_manifest_name_when_both_present() -> Result<(), TdfError> {
        let spec = manifest_with_url("a").to_json()?;
        let legacy = manifest_with_url("b").to_json()?;
        let bytes = raw_zip(&[
            ("0.manifest.json", legacy.as_bytes()),
            ("manifest.json", spec.as_bytes()),
            ("a", b"A"),
            ("b", b"B"),
        ]);
        let mut archive = TdfArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.by_index()?.payload, b"A");
        Ok(())
    }

    #[test]
    fn reader_falls_back_to_0_payload_when_url_empty() -> Result<(), TdfError> {
        let m = manifest_with_url("").to_json()?;
        let bytes = raw_zip(&[("manifest.json", m.as_bytes()), ("0.payload", b"fb")]);
        let mut archive = TdfArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.by_index()?.payload, b"fb");
        Ok(())
    }

    #[test]
    fn reader_errors_when_url_names_missing_entry() -> Result<(), TdfError> {
        let m = manifest_with_url("missing.bin").to_json()?;
        let bytes = raw_zip(&[("manifest.json", m.as_bytes()), ("0.payload", b"x")]);
        let mut archive = TdfArchive::new(Cursor::new(bytes))?;
        let err = archive.by_index().unwrap_err();
        assert!(err.to_string().contains("missing.bin"), "{err}");
        Ok(())
    }

    #[test]
    fn reader_rejects_unsafe_payload_url() -> Result<(), TdfError> {
        for bad in ["../x", "/abs", "a\\b", "x/../y"] {
            let m = manifest_with_url(bad).to_json()?;
            // The safety check fires before any lookup, so no payload member is needed.
            let bytes = raw_zip(&[("manifest.json", m.as_bytes())]);
            let mut archive = TdfArchive::new(Cursor::new(bytes))?;
            let err = archive.by_index().unwrap_err();
            assert!(err.to_string().contains("unsafe"), "{bad}: {err}");
        }
        Ok(())
    }

    #[test]
    fn len_counts_manifests_not_members() -> Result<(), TdfError> {
        let m = manifest_with_url("0.payload").to_json()?;
        let bytes = raw_zip(&[
            ("manifest.json", m.as_bytes()),
            ("0.payload", b"x"),
            ("extra.txt", b"y"),
        ]);
        let mut archive = TdfArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.len(), 1);
        archive.validate()?;
        Ok(())
    }

    #[test]
    fn test_tdf_archive_validation() -> Result<(), TdfError> {
        let mut archive = TdfArchive::new(Cursor::new(create_test_archive()?))?;
        archive.validate()?;
        Ok(())
    }

    #[test]
    fn test_get_entry_multi_index_keeps_indexed_names() -> Result<(), Box<dyn std::error::Error>> {
        let entries = [
            (manifest_with_url("0.payload"), b"first payload data".to_vec()),
            (manifest_with_url("1.payload"), b"second payload data".to_vec()),
        ];
        let temp_file = NamedTempFile::new()?;
        let temp_path = temp_file.path().to_owned();
        let mut builder = TdfArchiveBuilder::new(&temp_path)?;
        for (index, (manifest, payload)) in entries.iter().enumerate() {
            builder.add_entry(manifest, payload, index)?;
        }
        builder.finish()?;

        let bytes = std::fs::read(&temp_path)?;
        assert_eq!(
            names_of(&bytes),
            vec!["manifest.json", "0.payload", "1.manifest.json", "1.payload"]
        );

        let mut archive = TdfArchive::open(&temp_path)?;
        assert_eq!(archive.len(), 2);
        assert_eq!(archive.get_entry(0)?.payload, b"first payload data");
        assert_eq!(archive.get_entry(1)?.payload, b"second payload data");
        assert!(archive.get_entry(2).is_err());
        Ok(())
    }
}
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-rs && cargo test --lib archive::tests 2>&1 | grep -E "^test |test result" | head -30`
Expected: `builder_writes_spec_manifest_name_and_payload_from_url`, `builder_payload_entry_follows_manifest_url`, `memory_builder_matches_file_builder_names`, `reader_prefers_spec_manifest_name_when_both_present`, `reader_falls_back_to_0_payload_when_url_empty`, `reader_errors_when_url_names_missing_entry`, `reader_rejects_unsafe_payload_url`, `len_counts_manifests_not_members`, `test_get_entry_multi_index_keeps_indexed_names` FAIL.

- [ ] **Step 3: Add constants and helper functions**

In `RS/src/archive.rs`, directly above `pub struct TdfEntry<'a>` (line 30) add:

```rust
/// Spec (opentdf/spec schema/OpenTDF/README.md): the manifest entry MUST be
/// `manifest.json` at the archive root.
pub const TDF_MANIFEST_FILE_NAME: &str = "manifest.json";
/// Name every SDK wrote before spec compliance; accepted on read forever.
pub const LEGACY_TDF_MANIFEST_FILE_NAME: &str = "0.manifest.json";
/// Default payload entry name. Written into `manifest.payload.url` by callers
/// of `TdfManifest::new`; on read it is only a fallback for an empty url.
pub const TDF_PAYLOAD_FILE_NAME: &str = "0.payload";

fn manifest_entry_name_for_index(index: usize) -> (String, Option<String>) {
    if index == 0 {
        (
            TDF_MANIFEST_FILE_NAME.to_string(),
            Some(LEGACY_TDF_MANIFEST_FILE_NAME.to_string()),
        )
    } else {
        (format!("{}.manifest.json", index), None)
    }
}

fn is_safe_entry_name(name: &str) -> bool {
    !name.is_empty()
        && !name.starts_with('/')
        && !name.contains('\\')
        && !name.split('/').any(|seg| seg == "..")
}

fn is_manifest_entry_name(name: &str) -> bool {
    if name == TDF_MANIFEST_FILE_NAME {
        return true;
    }
    match name.strip_suffix(".manifest.json") {
        Some(prefix) => !prefix.is_empty() && prefix.bytes().all(|b| b.is_ascii_digit()),
        None => false,
    }
}

fn payload_entry_name_for(manifest: &TdfManifest, index: usize) -> Result<String, TdfError> {
    let url = manifest.payload.url.as_str();
    if url.is_empty() {
        return Ok(if index == 0 {
            TDF_PAYLOAD_FILE_NAME.to_string()
        } else {
            format!("{}.payload", index)
        });
    }
    if !is_safe_entry_name(url) {
        return Err(TdfError::InvalidStructure {
            reason: format!("unsafe payload url in manifest: {url:?}"),
            expected: Some("a relative zip member name without '..' or leading '/'".to_string()),
        });
    }
    Ok(url.to_string())
}
```

- [ ] **Step 4: Rewrite `len`, `get_entry`**

Replace `len` and `get_entry` in `impl<R: Read + Seek> TdfArchive<R>` with:

```rust
    /// Returns the number of TDF entries in the archive (one per manifest member).
    pub fn len(&self) -> usize {
        let mut count = 0;
        let mut saw_index0 = false;
        for name in self.zip_archive.file_names() {
            if name == TDF_MANIFEST_FILE_NAME || name == LEGACY_TDF_MANIFEST_FILE_NAME {
                if !saw_index0 {
                    saw_index0 = true;
                    count += 1;
                }
            } else if is_manifest_entry_name(name) {
                count += 1;
            }
        }
        count
    }

    fn has_member(&self, name: &str) -> bool {
        self.zip_archive.index_for_name(name).is_some()
    }

    /// Gets a specific TDF entry by index
    pub fn get_entry(&mut self, index: usize) -> Result<TdfEntry<'_>, TdfError> {
        let (primary, legacy) = manifest_entry_name_for_index(index);
        let manifest_name = if self.has_member(&primary) {
            primary.clone()
        } else if let Some(l) = legacy.filter(|l| self.has_member(l)) {
            l
        } else {
            return Err(TdfError::InvalidStructure {
                reason: format!("Missing manifest file: {}", primary),
                expected: Some(format!(
                    "TDF archive should contain {} (or legacy {})",
                    TDF_MANIFEST_FILE_NAME, LEGACY_TDF_MANIFEST_FILE_NAME
                )),
            });
        };

        // Read manifest
        let manifest = {
            let mut manifest_file = self.zip_archive.by_name(&manifest_name)?;
            let mut manifest_contents = String::new();
            manifest_file.read_to_string(&mut manifest_contents)?;
            TdfManifest::from_json(&manifest_contents)?
        };

        // Read payload, named by manifest.payload.url
        let payload_name = payload_entry_name_for(&manifest, index)?;
        let payload = {
            let mut payload_file = self.zip_archive.by_name(&payload_name).map_err(|_| {
                TdfError::InvalidStructure {
                    reason: format!("Missing payload file: {payload_name:?}"),
                    expected: Some(
                        "TDF archive should contain the member named by manifest.payload.url"
                            .to_string(),
                    ),
                }
            })?;
            let mut payload = Vec::new();
            payload_file.read_to_end(&mut payload)?;
            payload
        };

        Ok(TdfEntry {
            manifest,
            payload,
            index,
            _lifetime: std::marker::PhantomData,
        })
    }
```

`ZipArchive::index_for_name` and `file_names` exist in `zip` 2.x. If `by_name` errors need explicit mapping to `TdfError` (check the existing `From<zip::result::ZipError> for TdfError`), keep the `.map_err` form used today.

- [ ] **Step 5: Rewrite the four builder methods**

In both `TdfArchiveBuilder` and `TdfArchiveMemoryBuilder`, change `add_entry` and `add_entry_with_segments` so that:

```rust
        let manifest_json = manifest.to_json()?;
        let (manifest_name, _) = manifest_entry_name_for_index(index);
        let payload_name = payload_entry_name_for(manifest, index)?;

        // Write manifest
        self.writer.start_file::<_, ()>(
            manifest_name,
            FileOptions::default().compression_method(zip::CompressionMethod::Stored),
        )?;
        self.writer.write_all(manifest_json.as_bytes())?;

        // Write payload
        self.writer.start_file::<_, ()>(
            payload_name,
            FileOptions::default().compression_method(zip::CompressionMethod::Stored),
        )?;
```

followed by the existing `write_all(payload)` or the segment loop. Apply to all four methods.

- [ ] **Step 6: Re-export and update integration test**

In `RS/src/lib.rs` where `TdfArchive` is re-exported, add `LEGACY_TDF_MANIFEST_FILE_NAME, TDF_MANIFEST_FILE_NAME, TDF_PAYLOAD_FILE_NAME`.

In `RS/tests/integration.rs:85-106` change `required_files` to `["manifest.json", "0.payload"]` and the two `by_name("0.manifest.json")` calls to `by_name("manifest.json")`. Leave `tests/data/sensitive.txt.tdf` untouched; find the test that opens it (grep `sensitive.txt.tdf` in `tests/`) and confirm it still passes via the legacy fallback.

In `RS/src/archive.rs:364` the old error text is replaced by Step 4.

- [ ] **Step 7: Advertise `spec-container` in the xtest CLI**

In `RS/examples/xtest_cli.rs` `fn supports`, add after the `"connectrpc" => Ok(true),` line:

```rust
        // Writes manifest.json at the zip root and resolves the payload entry
        // from manifest.payload.url (opentdf/spec container rules).
        "spec-container" => Ok(true),
```

- [ ] **Step 8: Run everything**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-rs && cargo fmt --all && cargo clippy --workspace --all-targets -- -D warnings 2>&1 | tail -5 && cargo test --workspace 2>&1 | grep -E "^test result|FAILED|panicked"`
Expected: clippy clean, all test results `ok`. `tests/multi_entry_archive.rs` is unaffected because it passes `"0.manifest.json"` explicitly to `finish_with_manifest`.

- [ ] **Step 9: Commit**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-rs
git add src/archive.rs src/lib.rs tests/integration.rs examples/xtest_cli.rs
git commit -m "feat(archive): write manifest.json; resolve payload from payload.url; legacy read fallback

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Swift SDK

### Task 7: Swift manifest model version fields and accessor

**Files:**
- Modify: `SW/OpenTDFKit/TDF/TDFManifest.swift:4-63`
- Modify: `SW/OpenTDFKitCLI/Commands.swift:94,145`
- Test: `SW/OpenTDFKitTests/TDFTests.swift`

**Interfaces:**
- Produces: `TDFManifest.schemaVersion: String?` (was `String`; init parameter stays `String`), `TDFManifest.tdfSpecVersion: String?` (CodingKey `tdf_spec_version`, decode-only), `TDFPayloadDescriptor.tdfSpecVersion: String?` (CodingKey `tdf_spec_version`, decode-only), `TDFManifest.effectiveSpecVersion: String?`.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/arkavo/Projects/opentdf/OpenTDFKit && git checkout -b tdf-container-spec-compliance
```

- [ ] **Step 2: Write the failing tests**

Append to `final class StandardTDFTests` in `SW/OpenTDFKitTests/TDFTests.swift`:

```swift
    private func manifestJSON(top: String, payloadExtra: String) -> Data {
        """
        {"payload":{"type":"reference","url":"0.payload","protocol":"zip","isEncrypted":true\(payloadExtra)},
         "encryptionInformation":{"type":"split","keyAccess":[],
           "method":{"algorithm":"AES-256-GCM","iv":"","isStreamable":true},
           "integrityInformation":{"rootSignature":{"alg":"HS256","sig":""},"segmentHashAlg":"GMAC","segmentSizeDefault":0,"segments":[]},
           "policy":""}\(top)}
        """.data(using: .utf8)!
    }

    func testEffectiveSpecVersionPrefersSchemaVersion() throws {
        let m = try JSONDecoder().decode(TDFManifest.self, from: manifestJSON(
            top: ",\"schemaVersion\":\"4.3.0\",\"tdf_spec_version\":\"9.9.9\"",
            payloadExtra: ",\"tdf_spec_version\":\"8.8.8\""))
        XCTAssertEqual(m.effectiveSpecVersion, "4.3.0")
    }

    func testEffectiveSpecVersionThenTopLevelTdfSpecVersion() throws {
        let m = try JSONDecoder().decode(TDFManifest.self, from: manifestJSON(
            top: ",\"tdf_spec_version\":\"9.9.9\"",
            payloadExtra: ",\"tdf_spec_version\":\"8.8.8\""))
        XCTAssertEqual(m.effectiveSpecVersion, "9.9.9")
    }

    func testEffectiveSpecVersionThenPayloadTdfSpecVersion() throws {
        let m = try JSONDecoder().decode(TDFManifest.self, from: manifestJSON(
            top: "", payloadExtra: ",\"tdf_spec_version\":\"8.8.8\""))
        XCTAssertEqual(m.effectiveSpecVersion, "8.8.8")
    }

    func testEffectiveSpecVersionAbsentIsNil() throws {
        let m = try JSONDecoder().decode(TDFManifest.self, from: manifestJSON(top: "", payloadExtra: ""))
        XCTAssertNil(m.effectiveSpecVersion)
    }

    func testTdfSpecVersionIsNeverEncoded() throws {
        var m = createTestManifest()
        m.tdfSpecVersion = "9.9.9"
        m.payload.tdfSpecVersion = "8.8.8"
        let data = try JSONEncoder().encode(m)
        let obj = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertNil(obj["tdf_spec_version"])
        XCTAssertNil((obj["payload"] as! [String: Any])["tdf_spec_version"])
        XCTAssertEqual(obj["schemaVersion"] as? String, "1.0.0")
    }
```

- [ ] **Step 3: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/OpenTDFKit && swift test --filter StandardTDFTests 2>&1 | tail -15`
Expected: compile error, `value of type 'TDFManifest' has no member 'effectiveSpecVersion'`.

- [ ] **Step 4: Implement**

Replace `public struct TDFManifest` in `SW/OpenTDFKit/TDF/TDFManifest.swift` with:

```swift
public struct TDFManifest: Codable, Sendable {
    /// Root version key every SDK writes. Optional on decode so peer manifests
    /// carrying only `tdf_spec_version` still load.
    public var schemaVersion: String?
    public var payload: TDFPayloadDescriptor
    public var encryptionInformation: TDFEncryptionInformation
    public var assertions: [TDFAssertion]?
    /// Spec prose places `tdf_spec_version` at the root. Decode-only; never encoded.
    public var tdfSpecVersion: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion
        case payload
        case encryptionInformation
        case assertions
        case tdfSpecVersion = "tdf_spec_version"
    }

    public init(
        schemaVersion: String,
        payload: TDFPayloadDescriptor,
        encryptionInformation: TDFEncryptionInformation,
        assertions: [TDFAssertion]? = nil,
    ) {
        self.schemaVersion = schemaVersion
        self.payload = payload
        self.encryptionInformation = encryptionInformation
        self.assertions = assertions
        tdfSpecVersion = nil
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try c.decodeIfPresent(String.self, forKey: .schemaVersion)
        payload = try c.decode(TDFPayloadDescriptor.self, forKey: .payload)
        encryptionInformation = try c.decode(TDFEncryptionInformation.self, forKey: .encryptionInformation)
        assertions = try c.decodeIfPresent([TDFAssertion].self, forKey: .assertions)
        tdfSpecVersion = try c.decodeIfPresent(String.self, forKey: .tdfSpecVersion)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(schemaVersion, forKey: .schemaVersion)
        try c.encode(payload, forKey: .payload)
        try c.encode(encryptionInformation, forKey: .encryptionInformation)
        try c.encodeIfPresent(assertions, forKey: .assertions)
        // tdfSpecVersion intentionally not encoded.
    }

    /// Resolve the spec version: `schemaVersion`, then root `tdf_spec_version`,
    /// then `payload.tdf_spec_version`. First non-empty wins.
    public var effectiveSpecVersion: String? {
        for candidate in [schemaVersion, tdfSpecVersion, payload.tdfSpecVersion] {
            if let v = candidate, !v.isEmpty { return v }
        }
        return nil
    }
}
```

In `TDFPayloadDescriptor` add a stored property and CodingKey, and custom coding so it never encodes:

```swift
    public var mimeType: String?
    /// Spec JSON schema places `tdf_spec_version` under payload. Decode-only.
    public var tdfSpecVersion: String?

    enum CodingKeys: String, CodingKey {
        case type
        case url
        case protocolValue = "protocol"
        case isEncrypted
        case mimeType
        case tdfSpecVersion = "tdf_spec_version"
    }

    public init(
        type: PayloadType,
        url: String,
        protocolValue: PayloadProtocol,
        isEncrypted: Bool,
        mimeType: String? = nil,
    ) {
        self.type = type
        self.url = url
        self.protocolValue = protocolValue
        self.isEncrypted = isEncrypted
        self.mimeType = mimeType
        tdfSpecVersion = nil
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(PayloadType.self, forKey: .type)
        url = try c.decode(String.self, forKey: .url)
        protocolValue = try c.decode(PayloadProtocol.self, forKey: .protocolValue)
        isEncrypted = try c.decode(Bool.self, forKey: .isEncrypted)
        mimeType = try c.decodeIfPresent(String.self, forKey: .mimeType)
        tdfSpecVersion = try c.decodeIfPresent(String.self, forKey: .tdfSpecVersion)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(type, forKey: .type)
        try c.encode(url, forKey: .url)
        try c.encode(protocolValue, forKey: .protocolValue)
        try c.encode(isEncrypted, forKey: .isEncrypted)
        try c.encodeIfPresent(mimeType, forKey: .mimeType)
    }
```

In `SW/OpenTDFKitCLI/Commands.swift` lines 94 and 145 change `manifest.schemaVersion` / `container.manifest.schemaVersion` to `manifest.effectiveSpecVersion ?? "unknown"` / `container.manifest.effectiveSpecVersion ?? "unknown"`.

- [ ] **Step 5: Fix compile fallout**

Run:

```bash
cd /Users/arkavo/Projects/opentdf/OpenTDFKit && swift build 2>&1 | grep error: ; grep -rn "\.schemaVersion" OpenTDFKit OpenTDFKitCLI OpenTDFKitTests | grep -v "keyAccess\|kao\|ka\.\|KeyAccess"
```

Known manifest-level uses today: `TDFProcessor.swift:14` (assignment inside an init, unaffected), `Commands.swift:94,145` (changed in Step 4), and the TDF-JSON / TDF-CBOR containers, which only call `TDFManifest(schemaVersion: "1.0")` through the init (a `String` parameter, unaffected). If the CBOR encoder in `TDFCBORFormat.swift` reads `manifest.schemaVersion` to emit its key 9, encode `manifest.effectiveSpecVersion ?? ""` there. Test assertions like `XCTAssertEqual(manifest.schemaVersion, "1.0.0")` compile unchanged against `String?`. Do not touch writer sites; they still pass a `String` to `init(schemaVersion:)`.

- [ ] **Step 6: Run and commit**

Run: `cd /Users/arkavo/Projects/opentdf/OpenTDFKit && swift test 2>&1 | tail -5`
Expected: all tests pass.

```bash
cd /Users/arkavo/Projects/opentdf/OpenTDFKit
git add OpenTDFKit/TDF/TDFManifest.swift OpenTDFKitCLI/Commands.swift OpenTDFKitTests/TDFTests.swift
git commit -m "feat(manifest): effectiveSpecVersion read priority; decode-only tdf_spec_version

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 8: Swift archive reader resolves entry names; writer emits `manifest.json`

**Files:**
- Modify: `SW/OpenTDFKit/TDF/TDFArchive.swift` (whole file)
- Modify: `SW/OpenTDFKit/TDF/TDFProcessor.swift:167,279,367`
- Modify: `SW/OpenTDFKit/TDF/TDFManifestBuilder.swift:48,88`
- Modify: `SW/OpenTDFKitCLI/main.swift:742-746` (supports)
- Modify: `SW/CLAUDE.md:228`, `SW/MIGRATION_GUIDE.md` (grep `0.manifest.json`)
- Test: `SW/OpenTDFKitTests/TDFTests.swift:295-345`

**Interfaces:**
- Produces: `public enum TDFArchiveEntryNames { public static let manifest = "manifest.json"; public static let legacyManifest = "0.manifest.json"; public static let payload = "0.payload" }`.
- `TDFArchiveReader.manifest()` unchanged signature; `payloadData()`, `payloadSize()`, `writePayload(to:)` now resolve the entry from the manifest.
- `TDFArchiveWriter.buildArchive(manifest:payload:)` writes the payload under `manifest.payload.url` (fallback `0.payload` when empty) and the manifest under `manifest.json`.
- New error case `TDFArchiveError.unsafePayloadURL(String)` and `TDFArchiveError.missingPayloadEntry(String)`.

- [ ] **Step 1: Write the failing tests**

In `SW/OpenTDFKitTests/TDFTests.swift` change line 305 `archive["0.manifest.json"]!` to `archive["manifest.json"]!` and line 332 `archive["0.payload"]!` stays. Append to `StandardTDFTests`:

```swift
    private func rawZip(_ members: [(String, Data)]) throws -> Data {
        let archive = try ZIPFoundation.Archive(data: Data(), accessMode: .create)
        for (name, data) in members {
            try archive.addEntry(with: name, type: .file, uncompressedSize: Int64(data.count),
                                 compressionMethod: .none, bufferSize: ZIPFoundation.defaultWriteChunkSize) { pos, size in
                let s = Int(pos); let e = min(s + size, data.count)
                return s < data.count ? data.subdata(in: s ..< e) : Data()
            }
        }
        return archive.data!
    }

    private func entryNames(_ data: Data) throws -> [String] {
        let a = try ZIPFoundation.Archive(data: data, accessMode: .read)
        return a.map(\.path)
    }

    private func manifestData(url: String) throws -> Data {
        var m = createTestManifest()
        m.payload.url = url
        return try JSONEncoder().encode(m)
    }

    func testWriterEmitsSpecManifestNameAndPayloadFromURL() throws {
        let data = try TDFArchiveWriter().buildArchive(manifest: createTestManifest(), payload: testPlaintext)
        let names = try entryNames(data)
        XCTAssertEqual(Set(names), ["manifest.json", "0.payload"])
        XCTAssertFalse(names.contains("0.manifest.json"))
    }

    func testWriterPayloadEntryFollowsManifestURL() throws {
        var m = createTestManifest()
        m.payload.url = "data.bin"
        let data = try TDFArchiveWriter().buildArchive(manifest: m, payload: testPlaintext)
        XCTAssertEqual(Set(try entryNames(data)), ["manifest.json", "data.bin"])
        let reader = try TDFArchiveReader(data: data)
        XCTAssertEqual(try reader.payloadData(), testPlaintext)
    }

    func testReaderAcceptsLegacyManifestName() throws {
        let data = try rawZip([("0.manifest.json", try manifestData(url: "0.payload")), ("0.payload", testPlaintext)])
        let reader = try TDFArchiveReader(data: data)
        XCTAssertEqual(try reader.manifest().payload.url, "0.payload")
        XCTAssertEqual(try reader.payloadData(), testPlaintext)
    }

    func testReaderPrefersSpecManifestName() throws {
        let data = try rawZip([
            ("0.manifest.json", try manifestData(url: "b")),
            ("manifest.json", try manifestData(url: "a")),
            ("a", Data("A".utf8)), ("b", Data("B".utf8)),
        ])
        XCTAssertEqual(try TDFArchiveReader(data: data).payloadData(), Data("A".utf8))
    }

    func testReaderFallsBackTo0PayloadWhenURLEmpty() throws {
        let data = try rawZip([("manifest.json", try manifestData(url: "")), ("0.payload", testPlaintext)])
        XCTAssertEqual(try TDFArchiveReader(data: data).payloadData(), testPlaintext)
    }

    func testReaderErrorsWhenURLNamesMissingEntry() throws {
        let data = try rawZip([("manifest.json", try manifestData(url: "missing.bin")), ("0.payload", testPlaintext)])
        XCTAssertThrowsError(try TDFArchiveReader(data: data).payloadData()) { error in
            XCTAssertEqual(error as? TDFArchiveError, .missingPayloadEntry("missing.bin"))
        }
    }

    func testReaderRejectsUnsafePayloadURL() throws {
        for bad in ["../x", "/abs", "a\\b", "x/../y"] {
            let data = try rawZip([("manifest.json", try manifestData(url: bad))])
            XCTAssertThrowsError(try TDFArchiveReader(data: data).payloadData(), bad) { error in
                XCTAssertEqual(error as? TDFArchiveError, .unsafePayloadURL(bad))
            }
        }
    }
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/OpenTDFKit && swift test --filter StandardTDFTests 2>&1 | tail -15`
Expected: compile error on `.missingPayloadEntry` / `.unsafePayloadURL`; after stubbing, `testWriterEmitsSpecManifestNameAndPayloadFromURL` fails with `0.manifest.json` present.

- [ ] **Step 3: Rewrite `TDFArchive.swift`**

Replace the two private constants and the reader with:

```swift
import Foundation
@preconcurrency import ZIPFoundation

/// Zip member names for the TDF container (opentdf/spec schema/OpenTDF/README.md).
public enum TDFArchiveEntryNames {
    /// The manifest MUST be `manifest.json` at the archive root.
    public static let manifest = "manifest.json"
    /// Name every SDK wrote before spec compliance; accepted on read forever.
    public static let legacyManifest = "0.manifest.json"
    /// Default payload member; writers put this same value in `payload.url`.
    public static let payload = "0.payload"

    static func isSafe(_ name: String) -> Bool {
        if name.isEmpty || name.hasPrefix("/") || name.contains("\\") { return false }
        return !name.split(separator: "/", omittingEmptySubsequences: false).contains("..")
    }

    /// Payload member for a manifest: `payload.url`, or `0.payload` when empty.
    static func payloadEntry(for manifest: TDFManifest) throws -> String {
        let url = manifest.payload.url
        if url.isEmpty { return payload }
        guard isSafe(url) else { throw TDFArchiveError.unsafePayloadURL(url) }
        return url
    }
}

public struct TDFArchiveReader {
    public static let defaultManifestMaxSize = 10 * 1024 * 1024

    private let archive: ZIPFoundation.Archive

    public init(data: Data) throws {
        do {
            archive = try ZIPFoundation.Archive(data: data, accessMode: .read)
        } catch {
            throw TDFArchiveError.unreadableArchive
        }
    }

    public init(url: URL) throws {
        do {
            archive = try ZIPFoundation.Archive(url: url, accessMode: .read)
        } catch {
            throw TDFArchiveError.unreadableArchive
        }
    }

    private func manifestEntry() throws -> ZIPFoundation.Entry {
        if let e = archive[TDFArchiveEntryNames.manifest] { return e }
        if let e = archive[TDFArchiveEntryNames.legacyManifest] { return e }
        throw TDFArchiveError.missingManifest
    }

    private func payloadEntry() throws -> ZIPFoundation.Entry {
        let name = try TDFArchiveEntryNames.payloadEntry(for: manifest())
        guard let entry = archive[name] else {
            if name == TDFArchiveEntryNames.payload { throw TDFArchiveError.missingPayload }
            throw TDFArchiveError.missingPayloadEntry(name)
        }
        try validateEntryPath(entry.path)
        return entry
    }

    public func manifestData(maxSize: Int = TDFArchiveReader.defaultManifestMaxSize) throws -> Data {
        let entry = try manifestEntry()
        try validateEntryPath(entry.path)

        var total = 0
        var result = Data()
        let _ = try archive.extract(entry) { chunk in
            total += chunk.count
            if total > maxSize {
                throw TDFArchiveError.manifestTooLarge
            }
            result.append(chunk)
        }
        return result
    }

    public func manifest(maxSize: Int = TDFArchiveReader.defaultManifestMaxSize) throws -> TDFManifest {
        let data = try manifestData(maxSize: maxSize)
        return try JSONDecoder().decode(TDFManifest.self, from: data)
    }

    public func payloadSize() throws -> Int64 {
        Int64(try payloadEntry().uncompressedSize)
    }

    public func payloadData() throws -> Data {
        let entry = try payloadEntry()
        var result = Data(capacity: Int(entry.uncompressedSize))
        let _ = try archive.extract(entry) { chunk in
            result.append(chunk)
        }
        return result
    }

    public func writePayload(to handle: FileHandle) throws {
        let entry = try payloadEntry()
        _ = try archive.extract(entry) { chunk in
            try handle.write(contentsOf: chunk)
        }
    }

    private func validateEntryPath(_ path: String) throws {
        if path.contains("../") || path.hasPrefix("/") || path.contains("\\") {
            throw TDFArchiveError.maliciousPath
        }
        let normalizedPath = path.replacingOccurrences(of: "//", with: "/")
        if normalizedPath != path {
            throw TDFArchiveError.maliciousPath
        }
    }
}
```

In `TDFArchiveWriter.buildArchive(manifest:payload:)` replace the two `addEntry` lines with:

```swift
        let payloadName = try TDFArchiveEntryNames.payloadEntry(for: manifest)
        try addEntry(named: TDFArchiveEntryNames.manifest, data: manifestData, to: archive)
        try addEntry(named: payloadName, data: payload, to: archive)
```

Replace `TDFArchiveError` with:

```swift
public enum TDFArchiveError: Error, CustomStringConvertible, Equatable {
    case unreadableArchive
    case missingManifest
    case missingPayload
    case missingPayloadEntry(String)
    case unsafePayloadURL(String)
    case manifestTooLarge
    case creationFailed
    case maliciousPath

    public var description: String {
        switch self {
        case .unreadableArchive:
            "Unable to read TDF archive: invalid ZIP format or corrupted file"
        case .missingManifest:
            "Missing manifest: neither manifest.json nor 0.manifest.json found in archive"
        case .missingPayload:
            "Missing payload: 0.payload not found in archive"
        case let .missingPayloadEntry(name):
            "Missing payload: manifest payload.url names '\(name)', which is not in the archive"
        case let .unsafePayloadURL(url):
            "Unsafe payload url in manifest: '\(url)'"
        case .manifestTooLarge:
            "Manifest exceeds maximum allowed size"
        case .creationFailed:
            "Failed to create TDF archive"
        case .maliciousPath:
            "Archive contains unsafe path: path traversal detected"
        }
    }
}
```

- [ ] **Step 4: Derive `payload.url` from the constant at the five writer sites**

In `SW/OpenTDFKit/TDF/TDFProcessor.swift` lines 167, 279, 367 and `SW/OpenTDFKit/TDF/TDFManifestBuilder.swift` lines 48, 88 change `url: "0.payload",` to `url: TDFArchiveEntryNames.payload,`.

- [ ] **Step 5: CLI capability and docs**

In `SW/OpenTDFKitCLI/main.swift` `supportsCommand`, add before `case "connectrpc":`:

```swift
        case "spec-container":
            // Writes manifest.json at the zip root; payload entry resolved from payload.url.
            return 0
```

In `SW/CLAUDE.md:228` change ``proper `0.manifest.json` and `0.payload` structure`` to ``spec `manifest.json` and `0.payload` structure (reads legacy `0.manifest.json` too)``. Run `grep -n "0.manifest.json" MIGRATION_GUIDE.md` and change each to `manifest.json`, adding "(legacy archives use `0.manifest.json` and are still readable)" once.

- [ ] **Step 6: Run and commit**

Run: `cd /Users/arkavo/Projects/opentdf/OpenTDFKit && swift test 2>&1 | tail -5 && swift build -c release --product OpenTDFKitCLI 2>&1 | tail -2`
Expected: all tests pass; CLI builds.

```bash
cd /Users/arkavo/Projects/opentdf/OpenTDFKit
git add OpenTDFKit/TDF OpenTDFKitCLI OpenTDFKitTests CLAUDE.md MIGRATION_GUIDE.md
git commit -m "feat(archive): write manifest.json; resolve payload from payload.url; legacy read fallback

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Go platform SDK

### Task 9: Go manifest version fields and `EffectiveTDFVersion`

**Files:**
- Modify: `GO/sdk/manifest.go:46-53,64-68`
- Modify: `GO/sdk/tdf.go:925,1020,1387,1489`
- Test: `GO/sdk/manifest_test.go` (create)

**Interfaces:**
- Produces: `Payload.TDFSpecVersion string \`json:"tdf_spec_version,omitempty"\``, `Manifest.TDFSpecVersion string \`json:"tdf_spec_version,omitempty"\``, `func (m Manifest) EffectiveTDFVersion() string`.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-platform && git checkout -b tdf-container-spec-compliance
```

- [ ] **Step 2: Write the failing test**

Create `GO/sdk/manifest_test.go`:

```go
package sdk

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEffectiveTDFVersionPriority(t *testing.T) {
	cases := []struct {
		name string
		json string
		want string
	}{
		{"schemaVersion wins", `{"schemaVersion":"4.3.0","tdf_spec_version":"9.9.9","payload":{"tdf_spec_version":"8.8.8"}}`, "4.3.0"},
		{"then top-level tdf_spec_version", `{"tdf_spec_version":"9.9.9","payload":{"tdf_spec_version":"8.8.8"}}`, "9.9.9"},
		{"then payload.tdf_spec_version", `{"payload":{"tdf_spec_version":"8.8.8"}}`, "8.8.8"},
		{"none is legacy", `{"payload":{}}`, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var m Manifest
			require.NoError(t, json.Unmarshal([]byte(c.json), &m))
			assert.Equal(t, c.want, m.EffectiveTDFVersion())
		})
	}
}

func TestTDFSpecVersionNeverWrittenByDefault(t *testing.T) {
	m := Manifest{TDFVersion: TDFSpecVersion}
	out, err := json.Marshal(m)
	require.NoError(t, err)
	var raw map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(out, &raw))
	_, has := raw["tdf_spec_version"]
	assert.False(t, has)
	var payload map[string]json.RawMessage
	require.NoError(t, json.Unmarshal(raw["payload"], &payload))
	_, has = payload["tdf_spec_version"]
	assert.False(t, has)
	assert.Contains(t, string(out), `"schemaVersion":"4.3.0"`)
}
```

- [ ] **Step 3: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-platform/sdk && go test ./ -run 'TestEffectiveTDFVersion|TestTDFSpecVersionNever' 2>&1 | tail -5`
Expected: compile error `m.EffectiveTDFVersion undefined`.

- [ ] **Step 4: Implement**

In `GO/sdk/manifest.go` change `Payload` to:

```go
type Payload struct {
	Type        string `json:"type"`
	URL         string `json:"url"`
	Protocol    string `json:"protocol"`
	MimeType    string `json:"mimeType"`
	IsEncrypted bool   `json:"isEncrypted"`
	// TDFSpecVersion is where the spec's JSON schema places the version. Read
	// only; the SDK never sets it. See Manifest.EffectiveTDFVersion.
	TDFSpecVersion string `json:"tdf_spec_version,omitempty"`
}
```

and `Manifest` to:

```go
type Manifest struct {
	EncryptionInformation `json:"encryptionInformation"`
	Payload               `json:"payload"`
	Assertions            []Assertion `json:"assertions,omitempty"`
	TDFVersion            string      `json:"schemaVersion,omitempty"`
	// TDFSpecVersion is where the spec prose places the version. Read only;
	// the SDK never sets it. See EffectiveTDFVersion.
	TDFSpecVersion string `json:"tdf_spec_version,omitempty"`
}

// EffectiveTDFVersion resolves the spec version a writer recorded, in priority
// order: root schemaVersion (what every SDK writes), root tdf_spec_version
// (spec prose), then payload.tdf_spec_version (spec JSON schema). Empty means
// a legacy (pre-4.3.0) TDF.
func (m Manifest) EffectiveTDFVersion() string {
	if m.TDFVersion != "" {
		return m.TDFVersion
	}
	if m.TDFSpecVersion != "" {
		return m.TDFSpecVersion
	}
	return m.Payload.TDFSpecVersion
}
```

`Manifest.TDFSpecVersion` shadows the promoted `Payload.TDFSpecVersion`, so `m.Payload.TDFSpecVersion` must be spelled with the explicit `Payload.` selector as above.

In `GO/sdk/tdf.go` at lines 925, 1020, 1387 change `isLegacyTDF := r.manifest.TDFVersion == ""` to `isLegacyTDF := r.manifest.EffectiveTDFVersion() == ""`, and at line 1489 change `isLegacyTDF := manifest.TDFVersion == ""` to `isLegacyTDF := manifest.EffectiveTDFVersion() == ""`.

- [ ] **Step 5: Run and commit**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-platform/sdk && go build ./... && go test ./ -run 'TestEffectiveTDFVersion|TestTDFSpecVersionNever|TestTDF' 2>&1 | tail -5`
Expected: PASS.

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-platform
git add sdk/manifest.go sdk/manifest_test.go sdk/tdf.go
git commit -m "feat(sdk): EffectiveTDFVersion read priority; decode-only tdf_spec_version fields

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 10: Go zipstream reader resolves entry names; writer emits `manifest.json`

**Files:**
- Modify: `GO/sdk/internal/zipstream/zip_headers.go:18-21`
- Modify: `GO/sdk/internal/zipstream/tdf3_reader.go` (whole file)
- Modify: `GO/sdk/internal/zipstream/segment_writer_test.go:66` (file count assertion stays 2; names change)
- Modify: `GO/sdk/tdf_test.go:1503,1522,1548` (`f.Name == "0.manifest.json"`)
- Modify: `GO/sdk/schema/manifest.schema.json`, `GO/sdk/schema/manifest-lax.schema.json` (add top-level `tdf_spec_version` string property, not required)
- Test: `GO/sdk/internal/zipstream/tdf3_reader_test.go` (create)

**Interfaces:**
- Produces: `zipstream.TDFManifestFileName = "manifest.json"`, `zipstream.LegacyTDFManifestFileName = "0.manifest.json"`, `zipstream.TDFPayloadFileName = "0.payload"` (unchanged), `TDFReader.ManifestFileName() string`, `TDFReader.PayloadFileName() string`.
- `NewTDFReader` resolves both names eagerly (it reads the manifest once, bounded by `manifestMaxSize`).

- [ ] **Step 1: Write the failing tests**

Create `GO/sdk/internal/zipstream/tdf3_reader_test.go`:

```go
package zipstream

import (
	"archive/zip"
	"bytes"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func rawZip(t *testing.T, members [][2]string) *bytes.Reader {
	t.Helper()
	var buf bytes.Buffer
	w := zip.NewWriter(&buf)
	for _, m := range members {
		// TDF members are Stored; zipstream.Reader returns raw bytes at an offset.
		f, err := w.CreateHeader(&zip.FileHeader{Name: m[0], Method: zip.Store})
		require.NoError(t, err)
		_, err = f.Write([]byte(m[1]))
		require.NoError(t, err)
	}
	require.NoError(t, w.Close())
	return bytes.NewReader(buf.Bytes())
}

func manifestJSON(url string) string {
	return `{"payload":{"type":"reference","url":"` + url + `","protocol":"zip","isEncrypted":true}}`
}

func TestTDFReader_SpecNames(t *testing.T) {
	r, err := NewTDFReader(rawZip(t, [][2]string{{"manifest.json", manifestJSON("0.payload")}, {"0.payload", "PAY"}}))
	require.NoError(t, err)
	assert.Equal(t, "manifest.json", r.ManifestFileName())
	assert.Equal(t, "0.payload", r.PayloadFileName())
	got, err := r.ReadPayload(0, 3)
	require.NoError(t, err)
	assert.Equal(t, "PAY", string(got))
}

func TestTDFReader_LegacyManifestName(t *testing.T) {
	r, err := NewTDFReader(rawZip(t, [][2]string{{"0.manifest.json", manifestJSON("0.payload")}, {"0.payload", "OLD"}}))
	require.NoError(t, err)
	assert.Equal(t, "0.manifest.json", r.ManifestFileName())
	m, err := r.Manifest()
	require.NoError(t, err)
	assert.Contains(t, m, `"url":"0.payload"`)
	size, err := r.PayloadSize()
	require.NoError(t, err)
	assert.Equal(t, int64(3), size)
}

func TestTDFReader_PrefersSpecManifestWhenBothPresent(t *testing.T) {
	r, err := NewTDFReader(rawZip(t, [][2]string{
		{"0.manifest.json", manifestJSON("b")},
		{"manifest.json", manifestJSON("a")},
		{"a", "A"}, {"b", "B"},
	}))
	require.NoError(t, err)
	got, err := r.ReadPayload(0, 1)
	require.NoError(t, err)
	assert.Equal(t, "A", string(got))
}

func TestTDFReader_PayloadFromURL(t *testing.T) {
	r, err := NewTDFReader(rawZip(t, [][2]string{{"manifest.json", manifestJSON("data.bin")}, {"data.bin", "XYZ"}}))
	require.NoError(t, err)
	assert.Equal(t, "data.bin", r.PayloadFileName())
	got, err := r.ReadPayload(1, 2)
	require.NoError(t, err)
	assert.Equal(t, "YZ", string(got))
}

func TestTDFReader_FallbackWhenURLEmpty(t *testing.T) {
	r, err := NewTDFReader(rawZip(t, [][2]string{{"manifest.json", manifestJSON("")}, {"0.payload", "FB"}}))
	require.NoError(t, err)
	assert.Equal(t, "0.payload", r.PayloadFileName())
}

func TestTDFReader_URLNamesMissingEntry(t *testing.T) {
	_, err := NewTDFReader(rawZip(t, [][2]string{{"manifest.json", manifestJSON("missing.bin")}, {"0.payload", "x"}}))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "missing.bin")
}

func TestTDFReader_UnsafeURL(t *testing.T) {
	for _, bad := range []string{"../x", "/abs", `a\b`, "x/../y"} {
		// The safety check fires before any lookup, so no payload member is needed.
		_, err := NewTDFReader(rawZip(t, [][2]string{{"manifest.json", manifestJSON(bad)}}))
		require.Error(t, err, bad)
		assert.Contains(t, err.Error(), "unsafe", bad)
	}
}

func TestTDFReader_MissingManifest(t *testing.T) {
	_, err := NewTDFReader(rawZip(t, [][2]string{{"0.payload", "x"}}))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "manifest.json")
}
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-platform/sdk && go test ./internal/zipstream/ -run TestTDFReader_ 2>&1 | tail -5`
Expected: compile error `r.ManifestFileName undefined`.

- [ ] **Step 3: Change the constants**

In `GO/sdk/internal/zipstream/zip_headers.go` replace the constant block with:

```go
const (
	// TDFManifestFileName is the manifest member name required by the OpenTDF
	// spec (schema/OpenTDF/README.md): manifest.json at the archive root.
	TDFManifestFileName = "manifest.json"
	// LegacyTDFManifestFileName is what every SDK wrote before spec
	// compliance. Readers accept it forever.
	LegacyTDFManifestFileName = "0.manifest.json"
	// TDFPayloadFileName is the payload member name the writer uses and
	// records in manifest.payload.url. Readers only fall back to it when the
	// manifest's payload.url is empty.
	TDFPayloadFileName = "0.payload"
)
```

- [ ] **Step 4: Rewrite `tdf3_reader.go`**

Replace the file body after the imports with:

```go
import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
)

type TDFReader struct {
	archiveReader    Reader
	manifestMaxSize  int64
	manifestFileName string
	payloadFileName  string
}

const (
	manifestMaxSize = 1024 * 1024 * 10 // 10 MB
)

var (
	errManifestNotFound = errors.New("zip: neither manifest.json nor 0.manifest.json found in archive")
	errUnsafePayloadURL = errors.New("manifest payload.url is unsafe")
)

type TDFReaderOptions func(*TDFReader)

func WithTDFManifestMaxSize(size int64) TDFReaderOptions {
	return func(tdfReader *TDFReader) {
		tdfReader.manifestMaxSize = size
	}
}

// NewTDFReader Create tdf reader instance. It locates the manifest member
// (manifest.json, else 0.manifest.json) and the payload member named by
// manifest.payload.url (else 0.payload).
func NewTDFReader(readSeeker io.ReadSeeker, opt ...TDFReaderOptions) (TDFReader, error) {
	archiveReader, err := NewReader(readSeeker)
	if err != nil {
		return TDFReader{}, err
	}

	tdfArchiveReader := TDFReader{manifestMaxSize: manifestMaxSize}
	tdfArchiveReader.archiveReader = archiveReader
	for _, o := range opt {
		o(&tdfArchiveReader)
	}

	if err := tdfArchiveReader.resolveEntryNames(); err != nil {
		return TDFReader{}, err
	}
	return tdfArchiveReader, nil
}

func (tdfReader *TDFReader) resolveEntryNames() error {
	for _, candidate := range []string{TDFManifestFileName, LegacyTDFManifestFileName} {
		if _, ok := tdfReader.archiveReader.fileEntries[candidate]; ok {
			tdfReader.manifestFileName = candidate
			break
		}
	}
	if tdfReader.manifestFileName == "" {
		return errManifestNotFound
	}

	manifestBytes, err := tdfReader.archiveReader.ReadAllFileData(tdfReader.manifestFileName, tdfReader.manifestMaxSize)
	if err != nil {
		return err
	}
	var probe struct {
		Payload struct {
			URL string `json:"url"`
		} `json:"payload"`
	}
	// A manifest that is not JSON is reported later by the schema/unmarshal
	// step; here we only need payload.url, so ignore decode errors.
	_ = json.Unmarshal(manifestBytes, &probe)

	name := probe.Payload.URL
	if name == "" {
		name = TDFPayloadFileName
	} else if !isSafeEntryName(name) {
		return fmt.Errorf("%w: %q", errUnsafePayloadURL, name)
	}
	if _, ok := tdfReader.archiveReader.fileEntries[name]; !ok {
		return fmt.Errorf("%w: payload entry %q named by manifest payload.url", errZipFileNotFound, name)
	}
	tdfReader.payloadFileName = name
	return nil
}

func isSafeEntryName(name string) bool {
	if name == "" || strings.HasPrefix(name, "/") || strings.Contains(name, `\`) {
		return false
	}
	for _, seg := range strings.Split(name, "/") {
		if seg == ".." {
			return false
		}
	}
	return true
}

// ManifestFileName returns the zip member the manifest was read from.
func (tdfReader TDFReader) ManifestFileName() string { return tdfReader.manifestFileName }

// PayloadFileName returns the zip member the payload is read from.
func (tdfReader TDFReader) PayloadFileName() string { return tdfReader.payloadFileName }

// Manifest Return the manifest of the tdf.
func (tdfReader TDFReader) Manifest() (string, error) {
	fileContent, err := tdfReader.archiveReader.ReadAllFileData(tdfReader.manifestFileName, tdfReader.manifestMaxSize)
	if err != nil {
		return "", err
	}
	return string(fileContent), nil
}

// ReadPayload Return the payload of given length from index.
func (tdfReader TDFReader) ReadPayload(index, length int64) ([]byte, error) {
	return tdfReader.archiveReader.ReadFileData(tdfReader.payloadFileName, index, length)
}

// PayloadSize Return the size of the payload.
func (tdfReader TDFReader) PayloadSize() (int64, error) {
	size, err := tdfReader.archiveReader.ReadFileSize(tdfReader.payloadFileName)
	if err != nil {
		return -1, err
	}
	return size, nil
}
```

`errZipFileNotFound` is defined at `reader.go:36`; `fileEntries` is the exact-name map at `reader.go:49`, accessible because both files are in package `zipstream`.

- [ ] **Step 5: Update existing tests and schemas**

- `GO/sdk/tdf_test.go:1503,1522,1548`: change `f.Name == "0.manifest.json"` / `f.Name != "0.manifest.json"` to compare against `zipstream.TDFManifestFileName` (the test file already imports the SDK package; add `"github.com/opentdf/platform/sdk/internal/zipstream"` to its imports if absent).
- `GO/sdk/internal/zipstream/segment_writer_test.go`: the payload lookups at 69, 149, 220, 280 use `"0.payload"` and stay valid. Add one assertion in the first test after line 66: `require.NotNil(t, findFileByName(zipReader, TDFManifestFileName), "Should have manifest.json")`.
- `GO/sdk/schema/manifest.schema.json` and `manifest-lax.schema.json`: under the top-level `"properties"`, add

```json
      "tdf_spec_version": {
        "description": "Semver version number of the TDF spec (spec prose placement). Read only.",
        "type": "string"
      },
```

next to `"payload"`. Do not add it to any `required` list. Preserve the trailing newline.

- [ ] **Step 6: Run the SDK suite**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-platform/sdk && go test ./... 2>&1 | tail -15`
Expected: `ok` for every package. The legacy `sample.tdf` at the repo root is covered by `TestTDFReader_LegacyManifestName`; no separate probe is needed.

- [ ] **Step 7: Commit**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-platform
git add sdk/internal/zipstream sdk/tdf_test.go sdk/schema
git commit -m "feat(zipstream): write manifest.json; resolve payload from payload.url; legacy read fallback

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Test harness

### Task 11: Harness resolvers, `spec-container` capability, and container-layout test

**Files:**
- Modify: `XT/xtest/tdfs.py:174` (feature list), `:441-515` (zip helpers)
- Modify: `XT/xtest/test_tdfs.py` (new test after `test_manifest_validity_with_assertions`)
- Modify: `XT/.gitignore` (add `/platform`)
- Test: `XT/xtest/test_tdfs_entry_names.py` (create, pure unit tests of the resolvers)

**Interfaces:**
- Produces in `tdfs`: `MANIFEST_ENTRY_NAMES = ("manifest.json", "0.manifest.json")`, `DEFAULT_PAYLOAD_ENTRY = "0.payload"`, `entry_names(tdf_file: Path) -> list[str]`, `manifest_entry_name(names) -> str`, `payload_entry_name(payload_url: str | None, names) -> str`, and `"spec-container"` in `feature_type`.

- [ ] **Step 1: Write the failing unit tests**

Create `XT/xtest/test_tdfs_entry_names.py`:

```python
import pytest

import tdfs


@pytest.mark.no_audit_logs
def test_manifest_entry_prefers_spec_name():
    assert tdfs.manifest_entry_name(["0.manifest.json", "manifest.json"]) == "manifest.json"


@pytest.mark.no_audit_logs
def test_manifest_entry_legacy_fallback():
    assert tdfs.manifest_entry_name(["0.manifest.json", "0.payload"]) == "0.manifest.json"


@pytest.mark.no_audit_logs
def test_manifest_entry_missing():
    with pytest.raises(KeyError):
        tdfs.manifest_entry_name(["0.payload"])


@pytest.mark.no_audit_logs
def test_payload_entry_from_url_and_fallback():
    assert tdfs.payload_entry_name("data.bin", ["manifest.json", "data.bin"]) == "data.bin"
    assert tdfs.payload_entry_name("", ["manifest.json", "0.payload"]) == "0.payload"
    assert tdfs.payload_entry_name(None, ["manifest.json", "0.payload"]) == "0.payload"
    with pytest.raises(KeyError):
        tdfs.payload_entry_name("data.bin", ["manifest.json", "0.payload"])
```

- [ ] **Step 2: Run to confirm failure**

Run: `cd /Users/arkavo/Projects/opentdf/opentdf-tests/xtest && uv run pytest test_tdfs_entry_names.py --no-audit-logs -q 2>&1 | tail -5`
Expected: `AttributeError: module 'tdfs' has no attribute 'manifest_entry_name'`.

- [ ] **Step 3: Add resolvers to `tdfs.py` and route the four helpers through them**

Insert directly above `def manifest(tdf_file: Path) -> Manifest:`:

```python
# opentdf/spec container rules: the manifest member MUST be `manifest.json` at
# the archive root; `0.manifest.json` is the pre-spec name every SDK wrote and
# every golden file in this repo uses, so readers accept it forever.
MANIFEST_ENTRY_NAMES = ("manifest.json", "0.manifest.json")
DEFAULT_PAYLOAD_ENTRY = "0.payload"


def entry_names(tdf_file: Path) -> list[str]:
    with zipfile.ZipFile(tdf_file, "r") as tdfz:
        return tdfz.namelist()


def manifest_entry_name(names: list[str]) -> str:
    present = set(names)
    for candidate in MANIFEST_ENTRY_NAMES:
        if candidate in present:
            return candidate
    raise KeyError(f"no manifest entry ({' or '.join(MANIFEST_ENTRY_NAMES)}) in {names}")


def payload_entry_name(payload_url: str | None, names: list[str]) -> str:
    present = set(names)
    if payload_url:
        if payload_url in present:
            return payload_url
        raise KeyError(f"payload.url {payload_url!r} not in archive entries {names}")
    if DEFAULT_PAYLOAD_ENTRY in present:
        return DEFAULT_PAYLOAD_ENTRY
    raise KeyError(f"no payload entry in {names}")
```

Rewrite `manifest`:

```python
def manifest(tdf_file: Path) -> Manifest:
    with zipfile.ZipFile(tdf_file, "r") as tdfz:
        with tdfz.open(manifest_entry_name(tdfz.namelist())) as manifestEntry:
            return Manifest.model_validate_json(manifestEntry.read())
```

In `update_manifest`, replace the two `unzipped_dir / "0.manifest.json"` with `unzipped_dir / mname` after computing `mname = manifest_entry_name(zipped.namelist())` inside the `with zipfile.ZipFile(tdf_file, "r") as zipped:` block (before `extractall`).

In `update_payload`, inside the same style of `with` block compute:

```python
        names = zipped.namelist()
        mname = manifest_entry_name(names)
        with zipped.open(mname) as mf:
            url = Manifest.model_validate_json(mf.read()).payload.url
        pname = payload_entry_name(url, names)
        zipped.extractall(unzipped_dir)
```

and replace the two `unzipped_dir / "0.payload"` with `unzipped_dir / pname`.

In `validate_manifest_schema`, replace `zipped.open("0.manifest.json")` with `zipped.open(manifest_entry_name(zipped.namelist()))`.

Add `"spec-container",` to the `feature_type` Literal (alphabetical, after `"obligations"` or wherever the list keeps `o`/`s` entries) with the comment:

```python
    # Container layout per opentdf/spec: manifest.json at the zip root and the
    # payload member named by manifest.payload.url.
    "spec-container",
```

- [ ] **Step 4: Add the conformance test**

Append to `XT/xtest/test_tdfs.py` after `test_manifest_validity_with_assertions`:

```python
@pytest.mark.stage1
def test_container_layout(
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
):
    """opentdf/spec container rules: manifest.json at the root; payload named by payload.url."""
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    # go/java/js shims (`xtest/sdk/*/cli.sh`) exit 2 on an unknown feature, so
    # upstream SDKs skip here rather than fail.
    if not encrypt_sdk.supports("spec-container"):
        pytest.skip(f"{encrypt_sdk} sdk doesn't yet write the spec container layout")
    ct_file = encrypted_tdf(
        encrypt_sdk,
        attr_values=attribute_default_rsa.value_fqns,
    )
    names = tdfs.entry_names(ct_file)
    assert "manifest.json" in names, names
    assert "0.manifest.json" not in names, names
    m = tdfs.manifest(ct_file)
    assert m.payload.url, "payload.url must be set"
    assert m.payload.url in names, (m.payload.url, names)
    assert m.schemaVersion, "schemaVersion must be written"
    assert m.payload.tdf_spec_version is None
```

- [ ] **Step 5: Gitignore the local symlink**

Append `/platform` to `XT/.gitignore` with the comment `# local symlink to xtest/platform/src/main created by developers`.

- [ ] **Step 6: Run lint, the unit tests, and a legacy-golden smoke check**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-tests/xtest
uv run ruff check . && uv run ruff format . && uv run pyright
uv run pytest test_tdfs_entry_names.py --no-audit-logs -q
uv run python -c "import tdfs, pathlib; m = tdfs.manifest(pathlib.Path('golden/small-java-4.3.0-e0f8caf.tdf')); print(m.payload.url, m.schemaVersion)"
```

Expected: lint clean, 4 passed, and the golden file prints `0.payload 4.3.0` through the legacy fallback.

- [ ] **Step 7: Commit**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-tests
git add xtest/tdfs.py xtest/test_tdfs.py xtest/test_tdfs_entry_names.py .gitignore
git commit -m "feat(xtest): resolve container entry names per spec; add stage-1 container-layout test

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Verification

### Task 12: Cross-SDK verification

**Files:** none modified.

- [ ] **Step 1: Per-repo full test runs**

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-python-sdk && uv run pytest tests/ -m "not integration" -q 2>&1 | tail -3
cd /Users/arkavo/Projects/opentdf/opentdf-rs && cargo test --workspace 2>&1 | grep -E "^test result" 
cd /Users/arkavo/Projects/opentdf/OpenTDFKit && swift test 2>&1 | tail -3
cd /Users/arkavo/Projects/opentdf/opentdf-platform/sdk && go test ./... 2>&1 | tail -8
```

Expected: every suite green.

- [ ] **Step 2: Offline cross-SDK container check**

Encrypt with each community SDK's CLI in offline mode where it supports it, and inspect the zip:

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-rs && cargo build --example xtest_cli && \
  echo hello > /tmp/pt.txt && \
  TDF_SYMMETRIC_KEY_PATH=$(mktemp) && head -c 32 /dev/urandom > "$TDF_SYMMETRIC_KEY_PATH" && \
  TDF_SYMMETRIC_KEY_PATH="$TDF_SYMMETRIC_KEY_PATH" ./target/debug/examples/xtest_cli encrypt /tmp/pt.txt /tmp/rs.tdf tdf && \
  unzip -l /tmp/rs.tdf
```

Expected listing contains `manifest.json` and `0.payload` and not `0.manifest.json`. If the Rust offline path needs different env (see `examples/xtest_cli.rs` header comment), follow it. Repeat for Swift with `swift run OpenTDFKitCLI encrypt /tmp/pt.txt /tmp/sw.tdf tdf` if it supports an offline key env; otherwise skip and rely on the unit tests.

- [ ] **Step 3: Harness stage-1 matrix among community SDKs (needs a running platform)**

Follow `XT/xtest/AGENTS.md` to start the platform (`otdf-local up`), install the three community SDKs from the local branches via `otdf-sdk-mgr` or by symlinking `xtest/sdk/<lang>/src/main` to the working copies and running `make VERSIONS=main` in each `xtest/sdk/<lang>`, then:

```bash
cd /Users/arkavo/Projects/opentdf/opentdf-tests/xtest
SCHEMA_FILE=manifest.schema.json uv run pytest -m stage1 --containers tdf \
  --sdks-encrypt "python@main rust@main swift@main" \
  --sdks-decrypt "python@main rust@main swift@main" \
  --focus python -ra -v test_tdfs.py 2>&1 | tail -30
```

Expected: `test_tdf_roundtrip` green for all nine community pairs and `test_container_layout` green for all three encrypt SDKs. If the go peer is included (`go@latest`), expect the community-encrypt / go-decrypt cells of `test_tdf_roundtrip` to FAIL with a zip "file not found" error and `test_container_layout[go]` to SKIP. That is the accepted outcome recorded in the spec.

- [ ] **Step 4: Report**

Summarize per repo: branch name, commit count, test command and result, and paste the `unzip -l` output from Step 2. State plainly which harness cells are red and why.
