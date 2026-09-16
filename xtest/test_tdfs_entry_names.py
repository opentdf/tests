import pytest

import tdfs


@pytest.mark.no_audit_logs
def test_manifest_entry_prefers_spec_name():
    assert (
        tdfs.manifest_entry_name(["0.manifest.json", "manifest.json"])
        == "manifest.json"
    )


@pytest.mark.no_audit_logs
def test_manifest_entry_legacy_fallback():
    assert (
        tdfs.manifest_entry_name(["0.manifest.json", "0.payload"]) == "0.manifest.json"
    )


@pytest.mark.no_audit_logs
def test_manifest_entry_missing():
    with pytest.raises(KeyError):
        tdfs.manifest_entry_name(["0.payload"])


@pytest.mark.no_audit_logs
def test_payload_entry_from_url_and_fallback():
    assert (
        tdfs.payload_entry_name("data.bin", ["manifest.json", "data.bin"]) == "data.bin"
    )
    assert tdfs.payload_entry_name("", ["manifest.json", "0.payload"]) == "0.payload"
    assert tdfs.payload_entry_name(None, ["manifest.json", "0.payload"]) == "0.payload"
    with pytest.raises(KeyError):
        tdfs.payload_entry_name("data.bin", ["manifest.json", "0.payload"])
