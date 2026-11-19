"""Regenerate a real SDK's TDF from its DEK (DSPX-5547).

Streams the 5 MiB multi-segment TDF through a sparse sink that keeps only
the ZIP head and tail, plus every segment's IV and tag; unwraps the DEK with
the platform's own RSA KAS key; and serves the whole file over HTTP with
every segment re-encrypted from the plaintext. It must come back
byte-identical.

Needs ``kas-private.pem`` under ``PLATFORM_DIR``, which otdf-local and the
CI platform both write. Key-management and HSM-held keys are out of reach,
so without that file the test skips.
"""

import urllib.request
from collections.abc import Callable
from pathlib import Path

import pytest

import rangeserve
import regenerate
import tdfs
from abac import Attribute
from fixtures.encryption import EncryptFactory
from fixtures.kas import PLATFORM_DIR


def test_regenerated_tdf_is_byte_identical(
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    chunky_pt_file: Path,
    chunky_tdf: EncryptFactory,
    range_server: Callable[[rangeserve.Source], tuple[str, list[rangeserve.Request]]],
    tmp_path: Path,
) -> None:
    if encrypt_sdk not in in_focus:
        pytest.skip("Not in focus")
    kas_key = Path(PLATFORM_DIR) / "kas-private.pem"
    if not kas_key.is_file():
        pytest.skip(f"no file-based KAS private key at {kas_key}")
    ct_file = chunky_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, encrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    data = ct_file.read_bytes()
    pt = chunky_pt_file.read_bytes()
    # A streaming harness knows these before encrypting; here the file says.
    ii = tdfs.manifest(ct_file).encryptionInformation.integrityInformation
    assert ii.segmentSizeDefault
    layout = {
        "payload_start": rangeserve.payload_start(ct_file),
        "segment_size": ii.segmentSizeDefault,
        "plaintext_length": len(pt),
    }

    plan = rangeserve.retention_plan([], **layout)
    sink = rangeserve.SparseSink(tmp_path, plan, tail_ceiling=1 << 20, **layout)
    recorder = regenerate.SegmentRecorder(tmp_path, **layout)
    for i in range(0, len(data), 1 << 16):
        sink.write(data[i : i + (1 << 16)])
        recorder.write(data[i : i + (1 << 16)])
    store, segments = sink.close(), recorder.close()
    assert store.physical_size < len(data) // 100, "the payload should be dropped"

    dek = regenerate.unwrap_dek(regenerate.read_manifest(store), [kas_key.read_bytes()])
    source = regenerate.RegeneratingSource(
        store, segments, dek, lambda offset, n: pt[offset : offset + n]
    )
    url, _ = range_server(source)
    with urllib.request.urlopen(url, timeout=60) as r:
        assert r.read() == data
    store.close()
    segments.close()
