"""Serve a whole TDF whose payload was never stored, by re-encrypting it.

DSPX-5547. AES-GCM output is fixed by the key, the IV and the plaintext, and
xtest's plaintext comes from a deterministic generator. So a sparse store
that kept the ZIP head and tail (:class:`rangeserve.SparseSink`), plus every
segment's IV and tag (:class:`SegmentRecorder`), is enough to serve the whole
file once the DEK is known: each dropped segment is rebuilt on read and its
tag checked against the recorded one.

The DEK comes from the manifest and the KAS private key, so this works only
where the harness holds that key: otdf-local's and CI's file-based dev keys,
not key management or an HSM.
"""

import base64
import hmac
import os
import zipfile
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import tdfs
from rangeserve import PAYLOAD_GCM_OVERHEAD, Dropped, ExtentStore, Source

IV_SIZE = 12
TAG_SIZE = 16
DEK_SIZE = 32

#: ``(offset, length) -> bytes`` of the plaintext that was encrypted.
Plaintext = Callable[[int, int], bytes]

#: What the KAS and every SDK use for ``wrapped`` KAOs: SHA-1 for both the
#: OAEP digest and MGF1.
_OAEP = padding.OAEP(
    mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None
)


class RegenerationError(Exception):
    """The store, the recorded segments, the DEK and the plaintext disagree."""


class KeyUnavailable(Exception):
    """No private key we hold unwraps some key split."""


class Layout(NamedTuple):
    """Where each payload segment sits, as :func:`rangeserve.retention_plan` assumes.

    Uniform segments with a short last one. Segment ``data_segments`` is the
    empty one java appends when the plaintext is a whole number of segments.
    """

    payload_start: int
    segment_size: int
    plaintext_length: int

    @property
    def data_segments(self) -> int:
        return -(-self.plaintext_length // self.segment_size)

    def plaintext_extent(self, i: int) -> tuple[int, int]:
        start = min(i * self.segment_size, self.plaintext_length)
        return start, min(start + self.segment_size, self.plaintext_length)

    def extent(self, i: int) -> tuple[int, int]:
        """Ciphertext ``(start, end)`` of segment ``i``: IV, ciphertext, tag."""
        pt_start, pt_end = self.plaintext_extent(i)
        start = self.payload_start + i * PAYLOAD_GCM_OVERHEAD + pt_start
        return start, start + PAYLOAD_GCM_OVERHEAD + pt_end - pt_start


class SegmentTable:
    """Every recorded segment's IV and tag: flat files of 12- and 16-byte records.

    Nothing per segment in memory. On disk it is 28 bytes a segment, about
    1.4 MB at 100 GiB and 730 MB at 50 TiB with 2 MiB segments.
    """

    def __init__(self, directory: Path, layout: Layout, count: int):
        self.layout, self.count = layout, count
        self.ivs_path = directory / "ivs.bin"
        self.tags_path = directory / "tags.bin"
        self._ivs = self.ivs_path.open("rb")
        self._tags = self.tags_path.open("rb")

    def close(self) -> None:
        self._ivs.close()
        self._tags.close()

    def iv(self, i: int) -> bytes:
        return os.pread(self._ivs.fileno(), IV_SIZE, i * IV_SIZE)

    def tag(self, i: int) -> bytes:
        return os.pread(self._tags.fileno(), TAG_SIZE, i * TAG_SIZE)

    def tags(self, n: int) -> bytes:
        """The first ``n`` tags, concatenated."""
        return os.pread(self._tags.fileno(), n * TAG_SIZE, 0)


class SegmentRecorder:
    """Keep each payload segment's IV and tag as a TDF streams past.

    Feed it the same in-order ``write`` calls as :class:`rangeserve.SparseSink`,
    then ``close`` it for the :class:`SegmentTable`. It needs the layout facts
    :func:`rangeserve.retention_plan` needs, and also keeps the 28 bytes after
    the last data segment, in case they are java's empty segment.
    """

    def __init__(
        self,
        directory: Path,
        *,
        payload_start: int,
        segment_size: int,
        plaintext_length: int,
    ):
        if segment_size <= 0:
            raise ValueError(f"segment_size must be positive, got {segment_size}")
        self.layout = Layout(payload_start, segment_size, plaintext_length)
        self._dir = directory
        self._slots = self.layout.data_segments + 1
        self._done = 0  # segments whose IV and tag are complete
        self._pos = 0
        self._ivs = (directory / "ivs.bin").open("wb")
        self._tags = (directory / "tags.bin").open("wb")

    def write(self, data: bytes) -> None:
        start, end = self._pos, self._pos + len(data)
        while self._done < self._slots:
            s, e = self.layout.extent(self._done)
            if s >= end:
                break
            for f, lo, hi in (
                (self._ivs, s, s + IV_SIZE),
                (self._tags, e - TAG_SIZE, e),
            ):
                lo, hi = max(lo, start), min(hi, end)
                if lo < hi:
                    f.write(data[lo - start : hi - start])
            if e > end:
                break
            self._done += 1
        self._pos = end

    def close(self) -> SegmentTable:
        self._ivs.close()
        self._tags.close()
        return SegmentTable(self._dir, self.layout, self._done)


def unwrap_dek(manifest: tdfs.Manifest, private_keys: Iterable[bytes]) -> bytes:
    """Unwrap every key split with one of the RSA private-key PEMs, and XOR them.

    KAOs that share a split id are alternatives for the same share. Only
    ``wrapped`` (RSA) KAOs are supported; a split with only ``ec-wrapped``
    ones raises :class:`KeyUnavailable`, as does one no key opens.
    """
    keys: list[rsa.RSAPrivateKey] = []
    for pem in private_keys:
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError(f"not an RSA private key: {type(key).__name__}")
        keys.append(key)
    splits: dict[str, list[tdfs.KeyAccessObject]] = {}
    for kao in manifest.encryptionInformation.keyAccess:
        splits.setdefault(kao.sid or "", []).append(kao)
    if not splits:
        raise KeyUnavailable("the manifest has no keyAccess objects")
    dek = 0
    for sid, kaos in splits.items():
        dek ^= int.from_bytes(_unwrap_share(sid, kaos, keys))
    return dek.to_bytes(DEK_SIZE)


def _unwrap_share(
    sid: str, kaos: list[tdfs.KeyAccessObject], keys: list[rsa.RSAPrivateKey]
) -> bytes:
    for kao in kaos:
        if kao.type != "wrapped":
            continue
        wrapped = base64.b64decode(kao.wrappedKey)
        for key in keys:
            try:
                share = key.decrypt(wrapped, _OAEP)
            except ValueError:
                continue
            if len(share) != DEK_SIZE:
                raise RegenerationError(
                    f"split {sid!r} unwrapped to {len(share)} bytes, not {DEK_SIZE}"
                )
            return share
    tried = ", ".join(f"{k.type} kid={k.kid} at {k.url}" for k in kaos)
    raise KeyUnavailable(
        f"split {sid!r}: none of {len(keys)} RSA key(s) unwraps {tried}; "
        "only RSA-wrapped KAOs are supported"
    )


class _SourceFile:
    """Just enough of a read-only file over a :class:`rangeserve.Source` for zipfile."""

    def __init__(self, source: Source):
        self._source, self._pos = source, 0

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = os.SEEK_SET, /) -> int:
        self._pos = (0, self._pos, self._source.length)[whence] + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, n: int = -1, /) -> bytes:
        end = self._source.length if n < 0 else min(self._pos + n, self._source.length)
        data = self._source.read(self._pos, end) if end > self._pos else b""
        self._pos += len(data)
        return data


def read_manifest(source: Source) -> tdfs.Manifest:
    """The manifest, read from the tail alone."""
    with zipfile.ZipFile(_SourceFile(source)) as z:
        return tdfs.Manifest.model_validate_json(z.read("0.manifest.json"))


class RegeneratingSource:
    """A :class:`rangeserve.Source` for a whole TDF, most of it regenerated.

    Kept bytes come from the store as stored. Every other payload segment is
    rebuilt as ``IV || AES-GCM(DEK, IV, plaintext) || tag``, and a rebuilt tag
    that differs from the recorded one raises :class:`RegenerationError`
    before any of that segment is returned. Under :func:`rangeserve.serve`
    that aborts the response mid-body.

    Refuses to build unless the recorded tags are the manifest's segment
    hashes and the root signature verifies under ``dek``, which proves the
    layout and the DEK before anything is served.
    """

    def __init__(
        self,
        store: ExtentStore,
        segments: SegmentTable,
        dek: bytes,
        plaintext: Plaintext,
    ):
        manifest = read_manifest(store)
        ei = manifest.encryptionInformation
        ii = ei.integrityInformation
        if ei.method.algorithm != "AES-256-GCM":
            raise RegenerationError(
                f"payload is {ei.method.algorithm}, not AES-256-GCM"
            )
        if ii.segmentHashAlg.upper() != "GMAC":
            raise RegenerationError(
                f"segmentHashAlg is {ii.segmentHashAlg}; only GMAC hashes are tags"
            )
        if (ii.rootSignature.alg or "HS256").upper() != "HS256":
            raise RegenerationError(f"root signature is {ii.rootSignature.alg}")
        legacy = tdfs.is_legacy_manifest(manifest)
        count = len(ii.segments)
        hashes = b"".join(
            tdfs.decode_integrity_value(s.hash, legacy) for s in ii.segments
        )
        if count > segments.count or segments.tags(count) != hashes:
            raise RegenerationError(
                f"the {segments.count} recorded tags are not the manifest's {count} "
                f"segment hashes; is {segments.layout} right?"
            )
        root = tdfs.decode_integrity_value(ii.rootSignature.sig, legacy)
        if not hmac.compare_digest(
            hmac.digest(dek, tdfs.aggregate_hash(manifest), "sha256"), root
        ):
            raise RegenerationError("root signature does not verify: wrong DEK")

        self.length = store.length
        self._store, self._segments, self._plaintext = store, segments, plaintext
        self._aead = AESGCM(dek)
        self._layout = segments.layout
        self._payload_end = (
            self._layout.extent(count - 1)[1] if count else self._layout.payload_start
        )
        self._last: tuple[int, bytes] = (-1, b"")

    def _pieces(self, start: int, end: int) -> Iterator[tuple[int, int, int | None]]:
        """Split ``[start, end)`` at segment edges; the index is None off the payload."""
        lay = self._layout
        stride = lay.segment_size + PAYLOAD_GCM_OVERHEAD
        pos = start
        while pos < end:
            if pos < lay.payload_start:
                i, hi = None, min(end, lay.payload_start)
            elif pos >= self._payload_end:
                i, hi = None, end
            else:
                i = (pos - lay.payload_start) // stride
                while lay.extent(i)[1] <= pos:  # an empty segment after a short one
                    i += 1
                hi = min(end, lay.extent(i)[1])
            yield pos, hi, i
            pos = hi

    def _segment(self, i: int) -> bytes:
        if self._last[0] == i:
            return self._last[1]
        pt_start, pt_end = self._layout.plaintext_extent(i)
        pt = self._plaintext(pt_start, pt_end - pt_start)
        if len(pt) != pt_end - pt_start:
            raise RegenerationError(
                f"segment {i}: the plaintext generator returned {len(pt)} bytes, "
                f"not {pt_end - pt_start}"
            )
        iv = self._segments.iv(i)
        sealed = self._aead.encrypt(iv, pt, None)
        if sealed[-TAG_SIZE:] != self._segments.tag(i):
            raise RegenerationError(
                f"segment {i}: regenerated tag differs from the recorded one; "
                "wrong IV or plaintext"
            )
        self._last = (i, iv + sealed)
        return self._last[1]

    def check(self, start: int, end: int) -> None:
        for lo, hi, i in self._pieces(start, end):
            if i is None:
                self._store.check(lo, hi)

    def read(self, start: int, end: int) -> bytes:
        out: list[bytes] = []
        for lo, hi, i in self._pieces(start, end):
            try:
                out.append(self._store.read(lo, hi))
            except Dropped:
                if i is None:
                    raise
                seg_start = self._layout.extent(i)[0]
                out.append(self._segment(i)[lo - seg_start : hi - seg_start])
        return b"".join(out)
