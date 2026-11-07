"""Partial decrypt of a plaintext byte range, cross-SDK (DSPX-5117).

Every case decrypts a slice of a multi-segment, position-unique plaintext and
checks it against the generator, from a local file and over HTTP through the
DSPX-5111 range server in full mode. Over HTTP the server's request log also
bounds how much ciphertext the reader fetched: a reader that quietly downloads
the whole payload and slices afterwards passes the content check, so the byte
count is what proves the read was partial.

Gated on ``partial_decrypt`` (and ``http_range_source`` for the HTTP cells).
To run against unreleased SDK builds, set
``XT_FORCE_SUPPORTS=partial_decrypt,http_range_source``. The DSPX-5219
relabel cases also need ``segment_layout_verified``, which only forcing sets.
"""

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from itertools import accumulate, pairwise
from pathlib import Path

import pytest

import rangeserve
import tdfs
import zipinspect
from abac import Attribute
from audit_logs import AuditLogAsserter
from fixtures.encryption import EncryptFactory
from test_tdfs import assert_tamper_error, change_root_signature

#: A multiple of 16 for the line format, and not of 1 MiB, so every SDK ends
#: on a short segment.
PT_LENGTH = (5 << 20) + (112 << 10)


def line_bytes(start: int, end: int) -> bytes:
    """Plaintext ``[start, end)``. Line ``i`` is ``f"{i:15,d}\\n"``, so a
    misplaced read cannot match."""
    first = start // 16
    text = "".join(f"{i:15,d}\n" for i in range(first, -(-end // 16))).encode()
    return text[start - 16 * first : end - 16 * first]


@pytest.fixture(scope="session")
def partial_pt_file(tmp_dir: Path) -> Path:
    path = tmp_dir / "test-plain-partial.txt"
    if not (path.is_file() and path.stat().st_size == PT_LENGTH):
        with path.open("wb") as f:
            for at in range(0, PT_LENGTH, 1 << 20):
                f.write(line_bytes(at, min(at + (1 << 20), PT_LENGTH)))
    return path


@dataclass(frozen=True)
class Source:
    """How a cell hands the TDF to the CLI, and what its read log may show."""

    #: Features beyond ``partial_decrypt`` the decrypting SDK needs.
    features: tuple[tdfs.feature_type, ...] = ()
    #: Range server fixture serving the TDF, or None for the file itself.
    server: str | None = None
    #: Bytes a reader may fetch beyond head, covering segments and tail;
    #: None skips read accounting.
    allowance: int | None = None
    #: The :data:`RANGES` cases run through this source; None for all.
    cases: frozenset[str] | None = None


SOURCES: dict[str, Source] = {
    "file": Source(),
    # Room for HEAD/probe reads and read-ahead, far short of the payload. Only
    # cases whose budget leaves out segment 0 and most of the payload.
    "http": Source(
        ("http_range_source",),
        "range_server",
        64 * 1024,
        frozenset({"inside_one_segment", "length_omitted"}),
    ),
}

#: ``(offset, length)`` as a function of segment size and plaintext length.
#: A length of None means "to the end" (``--length`` omitted).
RANGES: dict[str, Callable[[int, int], tuple[int, int | None]]] = {
    "offset_zero": lambda seg, n: (0, 100),
    "inside_one_segment": lambda seg, n: (seg + seg // 4, 100),
    "crosses_boundary": lambda seg, n: (seg - 50, 100),
    "spans_segments": lambda seg, n: (seg - 50, seg + 100),
    "one_whole_segment": lambda seg, n: (seg, seg),
    "last_segment": lambda seg, n: ((n - 1) // seg * seg, n - (n - 1) // seg * seg),
    "length_omitted": lambda seg, n: (n - 1000, None),
    "length_past_end": lambda seg, n: (n - 10, 1000),
    "offset_at_eof": lambda seg, n: (n, None),
}

#: Range arithmetic is client-side, so off platform main one case per source
#: covers the rewrap.
FULL_TABLE = (os.environ.get("PLATFORM_TAG") or "main") == "main"
OFF_MAIN = frozenset({"inside_one_segment"})


def geometry(ct_file: Path, pt_len: int) -> int:
    ii = tdfs.manifest(ct_file).encryptionInformation.integrityInformation
    size = ii.segmentSizeDefault
    assert size and 2 * size < pt_len, (
        f"segmentSizeDefault={size} does not split the {pt_len}-byte payload "
        "into at least three segments"
    )
    return size


def skip_unless_in_play(
    encrypt_sdk: tdfs.SDK, decrypt_sdk: tdfs.SDK, in_focus: set[tdfs.SDK]
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    decrypt_sdk.skip_if_unsupported("partial_decrypt")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)
    tdfs.skip_connectrpc_skew(encrypt_sdk, decrypt_sdk, tdfs.get_platform_features())


@pytest.fixture
def source() -> str:
    return "file"


@dataclass
class Cell:
    pt: Path
    tdf: EncryptFactory
    ct: Path


@pytest.fixture
def cell(
    request: pytest.FixtureRequest,
    source: str,
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    partial_pt_file: Path,
    tmp_dir: Path,
    _encryption_cache: dict[tuple, Path],
) -> Cell:
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    decrypt_sdk.skip_if_unsupported(*SOURCES[source].features)
    label = request.node.originalname or request.node.name
    factory = EncryptFactory(label, partial_pt_file, tmp_dir, _encryption_cache)
    ct_file = factory(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    tdfs.skip_chunky_skew(ct_file, decrypt_sdk)
    return Cell(partial_pt_file, factory, ct_file)


def assert_plaintext(actual: bytes, start: int, end: int) -> None:
    expected = line_bytes(start, end)
    assert len(actual) == len(expected), (
        f"{len(actual)} bytes for plaintext {start}-{end}; want {len(expected)}"
    )
    if actual != expected:
        i = next(
            i for i, (a, b) in enumerate(zip(actual, expected, strict=True)) if a != b
        )
        pytest.fail(
            f"plaintext differs from offset {start + i}: "
            f"got {actual[i : i + 32]!r}, want {expected[i : i + 32]!r}"
        )


def payload_extent(ct_file: Path) -> tuple[int, int]:
    start = rangeserve.payload_start(ct_file)
    cd = zipinspect.central_directory(ct_file)
    entry = next(e for e in cd.entries if e.name == "0.payload")
    return start, start + entry.compressed_size


def fetch_budget(
    ct_file: Path, seg: int, pt_len: int, start: int, end: int, source: Source
) -> int:
    """Head + covering segments + tail + allowance, in bytes."""
    assert source.allowance is not None
    first, payload_end = payload_extent(ct_file)
    # web-sdk also reads the preceding segment to verify the size (DSPX-5219).
    if start // seg == -(-pt_len // seg) - 1 > 0:
        start -= seg
    plan = rangeserve.retention_plan(
        [(start, end)], plaintext_length=pt_len, segment_size=seg, payload_start=first
    )
    tail = ct_file.stat().st_size - payload_end
    return sum(e - s for s, e in plan) + tail + source.allowance


@pytest.mark.parametrize(
    ("case", "source"),
    [
        pytest.param(case, source, id=f"{case}-{source}")
        for source, spec in SOURCES.items()
        for case in RANGES
        if (spec.cases is None or case in spec.cases)
        and (FULL_TABLE or case in OFF_MAIN)
    ],
)
def test_partial_decrypt(
    request: pytest.FixtureRequest,
    decrypt_sdk: tdfs.SDK,
    cell: Cell,
    case: str,
    source: str,
) -> None:
    n = cell.pt.stat().st_size
    seg = geometry(cell.ct, n)
    offset, length = RANGES[case](seg, n)
    end = n if length is None else min(offset + length, n)

    spec = SOURCES[source]
    src: Path | str = cell.ct
    log: list[rangeserve.Request] = []
    if spec.server:
        serve = request.getfixturevalue(spec.server)
        src, log = serve(rangeserve.FullFile(cell.ct))

    rt_file = cell.tdf.rt_file(cell.ct, decrypt_sdk, variant=f"{case}-{source}")
    decrypt_sdk.decrypt(src, rt_file, "ztdf", plaintext_range=(offset, length))
    assert_plaintext(rt_file.read_bytes(), offset, end)

    if spec.allowance is not None and end > offset:
        served = sum(r.bytes_served for r in log)
        budget = fetch_budget(cell.ct, seg, n, offset, end, spec)
        assert served <= budget, (
            f"reader fetched {served} bytes of a {cell.ct.stat().st_size}-byte "
            f"TDF for plaintext {offset}-{end}; budget {budget}. Requests: {log}"
        )


def test_partial_decrypt_length_zero_rewraps(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    partial_pt_file: Path,
    tmp_dir: Path,
    audit_logs: AuditLogAsserter,
) -> None:
    """An empty read is still an access: KAS must log a rewrap of this policy."""
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    # Fresh, so no other cell's rewrap carries this policy's uuid.
    ct_file = tmp_dir / f"ct-partial-length-zero-{encrypt_sdk}-{decrypt_sdk}.tdf"
    encrypt_sdk.encrypt(
        partial_pt_file,
        ct_file,
        mime_type="text/plain",
        attr_values=attribute_default_rsa.value_fqns,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
    )
    tdfs.skip_chunky_skew(ct_file, decrypt_sdk)
    policy = tdfs.manifest(ct_file).encryptionInformation.policy_object.uuid
    rt_file = ct_file.with_suffix(".untdf")
    mark = audit_logs.mark("before_length_zero")
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf", plaintext_range=(100, 0))
    assert rt_file.read_bytes() == b""
    audit_logs.assert_rewrap_success(policy_uuid=policy, since_mark=mark)


def test_partial_decrypt_offset_past_end_fails(
    decrypt_sdk: tdfs.SDK, cell: Cell
) -> None:
    pt_len = cell.pt.stat().st_size
    rt_file = cell.tdf.rt_file(cell.ct, decrypt_sdk, variant="past-end")
    with pytest.raises(subprocess.CalledProcessError):
        decrypt_sdk.decrypt(
            cell.ct,
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
    decrypt_sdk: tdfs.SDK, cell: Cell
) -> None:
    seg = geometry(cell.ct, cell.pt.stat().st_size)
    sizes = tdfs.encrypted_segment_sizes(tdfs.manifest(cell.ct))
    b_file = tdfs.update_payload(
        "partial_tampered_segment", cell.ct, flip_byte_in_segment(1, sizes)
    )
    rt_file = cell.tdf.rt_file(b_file, decrypt_sdk)
    with pytest.raises(subprocess.CalledProcessError) as exc:
        decrypt_sdk.decrypt(
            b_file,
            rt_file,
            "ztdf",
            expect_error=True,
            plaintext_range=(seg + 10, 100),
        )
    assert_tamper_error(exc.value, "segment", decrypt_sdk)


def test_partial_decrypt_tampered_segment_out_of_range(
    record_property: Callable[[str, object], None],
    decrypt_sdk: tdfs.SDK,
    cell: Cell,
) -> None:
    """Seg 0 tampered, seg 2 read. Noticing is optional, so record, don't judge."""
    seg = geometry(cell.ct, cell.pt.stat().st_size)
    sizes = tdfs.encrypted_segment_sizes(tdfs.manifest(cell.ct))
    b_file = tdfs.update_payload(
        "partial_tampered_seg0", cell.ct, flip_byte_in_segment(0, sizes)
    )
    rt_file = cell.tdf.rt_file(b_file, decrypt_sdk)
    offset = 2 * seg + 10
    try:
        decrypt_sdk.decrypt(
            b_file,
            rt_file,
            "ztdf",
            expect_error=True,
            plaintext_range=(offset, 100),
        )
    except subprocess.CalledProcessError:
        outcome = "rejected"
    else:
        good = rt_file.read_bytes() == line_bytes(offset, offset + 100)
        outcome = "decrypted" if good else "wrong bytes"
    record_property("tampered_seg0_read_seg2", outcome)


def test_partial_decrypt_tampered_root_signature_fails(
    decrypt_sdk: tdfs.SDK, cell: Cell
) -> None:
    b_file = tdfs.update_manifest(
        "partial_broken_root_sig", cell.ct, change_root_signature
    )
    rt_file = cell.tdf.rt_file(b_file, decrypt_sdk)
    with pytest.raises(subprocess.CalledProcessError) as exc:
        decrypt_sdk.decrypt(
            b_file, rt_file, "ztdf", expect_error=True, plaintext_range=(0, 100)
        )
    assert_tamper_error(exc.value, "root", decrypt_sdk)


#: Bytes the DSPX-5219 cases splice into the payload; small enough that the
#: relabelled offset stays inside the real plaintext.
PAD = 4096


def inflate_first(m: tdfs.Manifest) -> tdfs.Manifest:
    ii = m.encryptionInformation.integrityInformation
    s = ii.segments[0]
    s.segmentSize = (s.segmentSize or ii.segmentSizeDefault or 0) + PAD
    s.encryptedSegmentSize = (
        s.encryptedSegmentSize or ii.encryptedSegmentSizeDefault or 0
    ) + PAD
    return m


def inflate_default(m: tdfs.Manifest) -> tdfs.Manifest:
    ii = m.encryptionInformation.integrityInformation
    *body, last = ii.segments
    last.segmentSize = last.segmentSize or ii.segmentSizeDefault
    last.encryptedSegmentSize = (
        last.encryptedSegmentSize or ii.encryptedSegmentSizeDefault
    )
    for s in body:
        if s.segmentSize:
            s.segmentSize += PAD
        if s.encryptedSegmentSize:
            s.encryptedSegmentSize += PAD
    ii.segmentSizeDefault = (ii.segmentSizeDefault or 0) + PAD
    ii.encryptedSegmentSizeDefault = (ii.encryptedSegmentSizeDefault or 0) + PAD
    return m


@dataclass(frozen=True)
class Relabel:
    """Recorded sizes grow by PAD and the payload is padded to match, so the
    segment hashes and the root still verify but every later offset shifts."""

    change: Callable[[tdfs.Manifest], tdfs.Manifest]
    #: How many leading segments get PAD bytes after them, of ``count``.
    padded: Callable[[int], int]
    #: Offset to read by the relabelled arithmetic, from ``(seg, count)``.
    offset: Callable[[int, int], int]


RELABELS: dict[str, Relabel] = {
    # Seg 0 claims PAD more bytes; read seg 1.
    "seg0_inflated": Relabel(inflate_first, lambda k: 1, lambda seg, k: seg + PAD + 10),
    # Every non-last segment claims PAD more; read the last, whose own size is
    # true, so only checking another segment against the default notices.
    "default_relabeled": Relabel(
        inflate_default, lambda k: k - 1, lambda seg, k: (k - 1) * (seg + PAD) + 10
    ),
}


def pad_after(sizes: list[int], count: int) -> Callable[[bytes], bytes]:
    def change(payload: bytes) -> bytes:
        bounds = [0, *accumulate(sizes[:count])]
        pieces = [payload[a:b] + bytes(PAD) for a, b in pairwise(bounds)]
        return b"".join(pieces) + payload[bounds[-1] :]

    return change


@pytest.mark.parametrize("relabel", RELABELS)
def test_partial_decrypt_relabeled_layout(
    decrypt_sdk: tdfs.SDK, cell: Cell, relabel: str
) -> None:
    """Fail, or return the bytes really at the offset; never a shifted read."""
    decrypt_sdk.skip_if_unsupported("segment_layout_verified")
    r = RELABELS[relabel]
    n = cell.pt.stat().st_size
    seg = geometry(cell.ct, n)
    sizes = tdfs.encrypted_segment_sizes(tdfs.manifest(cell.ct))
    offset = r.offset(seg, len(sizes))
    assert offset + 100 <= n
    padded = tdfs.update_payload(
        f"{relabel}_payload", cell.ct, pad_after(sizes, r.padded(len(sizes)))
    )
    b_file = tdfs.update_manifest(f"{relabel}_manifest", padded, r.change)
    rt_file = cell.tdf.rt_file(b_file, decrypt_sdk)
    try:
        decrypt_sdk.decrypt(
            b_file,
            rt_file,
            "ztdf",
            expect_error=True,
            plaintext_range=(offset, 100),
        )
    except subprocess.CalledProcessError:
        return
    assert_plaintext(rt_file.read_bytes(), offset, offset + 100)
