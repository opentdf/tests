"""Partial decrypt of a plaintext byte range, cross-SDK (DSPX-5117).

Every case decrypts a slice of the 5 MiB multi-segment payload and compares
it with the same slice of the plaintext, from a local file and over HTTP
through the DSPX-5111 range server in full mode. Over HTTP the server's
request log also bounds how much ciphertext the reader fetched: a reader that
quietly downloads the whole payload and slices afterwards passes the content
check, so the byte count is what proves the read was partial.

Gated on ``partial_decrypt`` (and ``http_range_source`` for the HTTP cells).
To run against unreleased SDK builds, set
``XT_FORCE_SUPPORTS=partial_decrypt,http_range_source``.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import rangeserve
import tdfs
from abac import Attribute
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory
from test_tdfs import assert_tamper_error, change_root_signature

#: Bytes a reader may fetch beyond head, covering segments and tail: room for
#: HEAD/probe reads and read-ahead, far short of the multi-MiB payload.
FETCH_ALLOWANCE = 64 * 1024

#: ``(offset, length)`` as a function of segment size and plaintext length.
#: A length of None means "to the end" (``--length`` omitted).
RANGES: dict[str, Callable[[int, int], tuple[int, int | None]]] = {
    "offset_zero": lambda seg, n: (0, 100),
    "inside_one_segment": lambda seg, n: (seg // 4, 100),
    "crosses_boundary": lambda seg, n: (seg - 50, 100),
    "spans_segments": lambda seg, n: (seg // 2, seg + 100),
    "one_whole_segment": lambda seg, n: (seg, seg),
    "last_segment": lambda seg, n: ((n - 1) // seg * seg, n - (n - 1) // seg * seg),
    "length_omitted": lambda seg, n: (n - 1000, None),
    "length_past_end": lambda seg, n: (n - 10, 1000),
    "length_zero": lambda seg, n: (100, 0),
}


def geometry(ct_file: Path, pt_len: int) -> int:
    ii = tdfs.manifest(ct_file).encryptionInformation.integrityInformation
    size = ii.segmentSizeDefault
    assert size and 2 * size < pt_len, (
        f"segmentSizeDefault={size} does not split the {pt_len}-byte payload "
        "into at least three segments"
    )
    return size


@pytest.fixture
def ranged_ct(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    chunky_tdf: EncryptFactory,
) -> Path:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    decrypt_sdk.skip_if_unsupported("partial_decrypt")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, tdfs.get_platform_features())
    ct_file = chunky_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    tdfs.skip_chunky_skew(ct_file, decrypt_sdk)
    return ct_file


def fetch_budget(ct_file: Path, seg: int, pt_len: int, start: int, end: int) -> int:
    """Head + covering segments + tail + allowance, in bytes."""
    first = rangeserve.payload_start(ct_file)
    payload_end = first + pt_len + -(-pt_len // seg) * rangeserve.PAYLOAD_GCM_OVERHEAD
    plan = rangeserve.retention_plan(
        [(start, end)], plaintext_length=pt_len, segment_size=seg, payload_start=first
    )
    tail = ct_file.stat().st_size - payload_end
    return sum(e - s for s, e in plan) + tail + FETCH_ALLOWANCE


@pytest.mark.parametrize("source", ["file", "http"])
@pytest.mark.parametrize("case", RANGES)
def test_partial_decrypt(
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    chunky_tdf: EncryptFactory,
    ranged_ct: Path,
    range_server: Callable[[rangeserve.Source], tuple[str, list[rangeserve.Request]]],
    audit_logs: AuditLogAsserter,
    case: str,
    source: str,
) -> None:
    pt = chunky_pt_file.read_bytes()
    seg = geometry(ranged_ct, len(pt))
    offset, length = RANGES[case](seg, len(pt))
    end = len(pt) if length is None else min(offset + length, len(pt))

    src: Path | str = ranged_ct
    log: list[rangeserve.Request] = []
    if source == "http":
        decrypt_sdk.skip_if_unsupported("http_range_source")
        src, log = range_server(rangeserve.FullFile(ranged_ct))

    rt_file = chunky_tdf.rt_file(ranged_ct, decrypt_sdk, variant=f"{case}-{source}")
    mark = audit_logs.mark("before_partial_decrypt")
    decrypt_sdk.decrypt(src, rt_file, "ztdf", plaintext_range=(offset, length))
    assert rt_file.read_bytes() == pt[offset:end]
    audit_logs.assert_rewrap_success(min_count=1, since_mark=mark)

    if source == "http" and end > offset:
        served = sum(r.bytes_served for r in log)
        budget = fetch_budget(ranged_ct, seg, len(pt), offset, end)
        assert served <= budget, (
            f"reader fetched {served} bytes of a {ranged_ct.stat().st_size}-byte "
            f"TDF for plaintext {offset}-{end}; budget {budget}. Requests: {log}"
        )


def test_partial_decrypt_offset_past_end_fails(
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    chunky_tdf: EncryptFactory,
    ranged_ct: Path,
) -> None:
    pt_len = chunky_pt_file.stat().st_size
    rt_file = chunky_tdf.rt_file(ranged_ct, decrypt_sdk, variant="past-end")
    with pytest.raises(subprocess.CalledProcessError):
        decrypt_sdk.decrypt(
            ranged_ct,
            rt_file,
            "ztdf",
            expect_error=True,
            plaintext_range=(pt_len + 1, 10),
        )
    assert not rt_file.exists() or rt_file.stat().st_size == 0


def flip_byte_in_segment(index: int, sizes: list[int]) -> Callable[[bytes], bytes]:
    def change(payload: bytes) -> bytes:
        # Past the 12-byte IV, inside the ciphertext proper.
        at = sum(sizes[:index]) + 20
        return payload[:at] + bytes([payload[at] ^ 0x01]) + payload[at + 1 :]

    return change


def test_partial_decrypt_tampered_segment_in_range_fails(
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    chunky_tdf: EncryptFactory,
    ranged_ct: Path,
) -> None:
    seg = geometry(ranged_ct, chunky_pt_file.stat().st_size)
    sizes = tdfs.encrypted_segment_sizes(tdfs.manifest(ranged_ct))
    b_file = tdfs.update_payload(
        "partial_tampered_segment", ranged_ct, flip_byte_in_segment(1, sizes)
    )
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk)
    with pytest.raises(subprocess.CalledProcessError) as exc:
        decrypt_sdk.decrypt(
            b_file,
            rt_file,
            "ztdf",
            expect_error=True,
            plaintext_range=(seg + 10, 100),
        )
    assert_tamper_error(exc.value, "segment", decrypt_sdk)


def test_partial_decrypt_tampered_root_signature_fails(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    ranged_ct: Path,
) -> None:
    b_file = tdfs.update_manifest(
        "partial_broken_root_sig", ranged_ct, change_root_signature
    )
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk)
    with pytest.raises(subprocess.CalledProcessError) as exc:
        decrypt_sdk.decrypt(
            b_file, rt_file, "ztdf", expect_error=True, plaintext_range=(0, 100)
        )
    assert_tamper_error(exc.value, "root", decrypt_sdk)
