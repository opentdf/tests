"""Offline tests for ``zipmutate.py`` (DSPX-4591 follow-up).

No platform or SDK; one isolated Python subprocess checks timeout cleanup.
Runs in ``check.yml`` on every PR for the same reason as ``test_zip64_units.py``: a builder
bug here would otherwise surface only as a mysterious failure in
``test_zip_conformance.py``'s cross-SDK cells.

``zipinspect.py`` is used throughout as the independent oracle: these tests
build something with ``zipmutate`` and then check what comes back out through
the (separately tested) reader, rather than asserting on ``zipmutate``'s own
internals.

The second half pins ``test_zip_conformance.py``'s *outcome contract* rather
than the builder: which decrypt results pass, which fail, and that a
tolerated result never leaks the client credentials the go and java shims
echo. That contract is what every cross-SDK cell rests on, and it is cheap to
get subtly wrong -- so it is checked here, offline, on every PR. Everything
added for it must stay offline: fake the process result, never spawn a CLI.
"""

import dataclasses
import struct
import subprocess
import warnings
import zipfile
from pathlib import Path
from unittest.mock import create_autospec

import pytest

import tdfs
import test_zip_conformance as conformance
import zipinspect
import zipmutate
from abac import Attribute
from fixtures.encryption import EncryptFactory
from zipinspect import MalformedZipError

#: The same extended-timestamp shape real writers emit, reused from
#: test_zip_conformance.py's fixture-level constant.
_FOREIGN_EXTRA_TLV = struct.pack("<HH", 0x5455, 5) + b"\x01\x00\x00\x00\x00"


def _ordinary_zip(path: Path) -> Path:
    """A small, real, STORED-entries ZIP -- the shape a TDF actually is."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("0.payload", b"payload-bytes-000")
        z.writestr("0.manifest.json", b'{"hello":"world"}')
    return path


class TestLoadTrailerAndRewrite:
    def test_unmodified_trailer_round_trips_exactly(self, tmp_path: Path):
        """The baseline: rewriting with no changes must reproduce the same
        entries, offsets and sizes zipinspect would report for the original.
        """
        src = _ordinary_zip(tmp_path / "src.zip")
        before = zipinspect.central_directory(src)

        trailer, cd_offset = zipmutate.load_trailer(src)
        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        after = zipinspect.central_directory(dest)
        assert [
            (e.name, e.local_header_offset, e.compressed_size) for e in after.entries
        ] == [
            (e.name, e.local_header_offset, e.compressed_size) for e in before.entries
        ]
        assert after.cd_offset == cd_offset
        zipinspect.assert_offsets_are_consistent(after)
        with zipfile.ZipFile(dest) as z:
            assert all(e.extract_version == 20 for e in z.infolist())

    def test_rejects_identical_src_and_dest(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)
        with pytest.raises(ValueError, match="distinct src and dest"):
            zipmutate.rewrite(src, src, trailer)

    @pytest.mark.parametrize("version_needed", [20, 45], ids=["compatibility", "zip64"])
    def test_zip64_offset_forced_with_a_foreign_extra_record_ahead_of_it(
        self, tmp_path: Path, version_needed: int
    ):
        """The inspector tolerates version 2.0 on a ZIP64 entry, although
        cross-SDK conformance requires a valid version 4.5 declaration.
        """
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        true_offset = None
        for i, entry in enumerate(trailer.entries):
            if entry.name == "0.manifest.json":
                true_offset = entry.local_header_offset

                trailer.entries[i] = dataclasses.replace(
                    entry,
                    force_zip64_offset=True,
                    extra_prefix=_FOREIGN_EXTRA_TLV,
                    version_needed_to_extract=version_needed,
                )
        assert true_offset is not None

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        cd = zipinspect.central_directory(dest)
        manifest = next(e for e in cd.entries if e.name == "0.manifest.json")
        assert manifest.has_zip64_extra
        assert manifest.uses_zip64_for_offset
        assert manifest.local_header_offset == true_offset
        with zipfile.ZipFile(dest) as z:
            assert z.getinfo("0.manifest.json").extract_version == version_needed
            assert z.getinfo("0.payload").extract_version == 20

    def test_zip64_sizes_forced_resolve_both_fields(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)
        payload = trailer.entries[0]
        assert payload.name == "0.payload"
        true_csize, true_usize = payload.compressed_size, payload.uncompressed_size
        trailer.entries[0] = dataclasses.replace(
            payload,
            force_zip64_compressed_size=True,
            force_zip64_uncompressed_size=True,
            version_needed_to_extract=45,
        )

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        entry = zipinspect.central_directory(dest).entries[0]
        assert entry.uses_zip64_for_sizes
        assert entry.compressed_size == true_csize
        assert entry.uncompressed_size == true_usize

    @pytest.mark.parametrize("force_zip64", [False, True], ids=["zip", "zip64"])
    @pytest.mark.parametrize("comment_length", [0xFFEB, 0xFFEC, 0xFFFF])
    def test_long_comment_round_trips(
        self, tmp_path: Path, force_zip64: bool, comment_length: int
    ):
        """Exercise the locator at, partly before, and wholly before the
        old EOCD-only search window, with ordinary ZIP controls as well.
        """
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=force_zip64, comment=b"c" * comment_length
        )

        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)
        cd = zipinspect.central_directory(dest)
        assert {e.name for e in cd.entries} == {"0.payload", "0.manifest.json"}
        with zipfile.ZipFile(src) as original, zipfile.ZipFile(dest) as rewritten:
            assert rewritten.comment == b"c" * comment_length
            for name in original.namelist():
                assert rewritten.read(name) == original.read(name)

    def test_comment_over_0xffff_is_rejected(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, cd_offset = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(trailer, comment=b"c" * (0xFFFF + 1))
        with pytest.raises(ValueError, match="0xFFFF"):
            trailer.to_bytes(cd_offset)


class TestEntryCountOverride:
    """The declared count is a lie the real CD bytes never agree to back up."""

    def test_plain_eocd_carries_the_overridden_count(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(trailer, entry_count_override=500)
        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        # Read the raw EOCD count field directly: central_directory() would
        # raise before ever reporting it, since the lie is the point.
        tail = dest.read_bytes()[-zipinspect.EOCD_SIZE :]
        assert tail[:4] == zipinspect.EOCD_SIG
        _, total_entries, _, _ = struct.unpack_from("<HHII", tail, 8)
        assert total_entries == 500

        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(dest)

    def test_forced_zip64_eocd_carries_the_overridden_count(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        trailer, _ = zipmutate.load_trailer(src)

        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=True, entry_count_override=70_000
        )
        dest = tmp_path / "dest.zip"
        zipmutate.rewrite(src, dest, trailer)

        data = dest.read_bytes()
        eocd64_at = data.rfind(zipinspect.EOCD64_SIG)
        assert eocd64_at >= 0
        total_this_disk, total = struct.unpack_from("<QQ", data, eocd64_at + 24)
        assert total_this_disk == 70_000
        assert total == 70_000

        eocd_at = data.rfind(zipinspect.EOCD_SIG)
        this_disk_count, total_count = struct.unpack_from("<HH", data, eocd_at + 8)
        assert (this_disk_count, total_count) == (0xFFFF, 0xFFFF)

        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(dest)


class TestCorruptEntryBytes:
    def test_patches_only_the_named_window(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        dest = tmp_path / "dest.zip"
        cd = zipinspect.central_directory(src)
        entry = next(e for e in cd.entries if e.name == "0.payload")
        data_offset = zipinspect.local_file_header_data_offset(src, entry)

        zipmutate.corrupt_entry_bytes(src, dest, "0.payload", at=2, patch=b"PK\x01\x02")

        before = src.read_bytes()
        after = dest.read_bytes()
        assert len(before) == len(after)
        patch_start = data_offset + 2
        patch_end = patch_start + 4
        assert after[patch_start:patch_end] == b"PK\x01\x02"
        assert before[:patch_start] == after[:patch_start]
        assert before[patch_end:] == after[patch_end:]

    def test_rejects_identical_src_and_dest(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        with pytest.raises(ValueError, match="distinct src and dest"):
            zipmutate.corrupt_entry_bytes(src, src, "0.payload", at=0, patch=b"x")

    def test_rejects_an_unknown_entry_name(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        dest = tmp_path / "dest.zip"
        with pytest.raises(ValueError, match="no entry named"):
            zipmutate.corrupt_entry_bytes(src, dest, "does.not.exist", at=0, patch=b"x")

    def test_rejects_a_patch_that_would_run_past_the_entrys_data(self, tmp_path: Path):
        src = _ordinary_zip(tmp_path / "src.zip")
        dest = tmp_path / "dest.zip"
        entry = next(
            e
            for e in zipinspect.central_directory(src).entries
            if e.name == "0.payload"
        )
        with pytest.raises(ValueError, match="outside entry"):
            zipmutate.corrupt_entry_bytes(
                src,
                dest,
                "0.payload",
                at=entry.compressed_size - 1,
                patch=b"too-long-for-the-remaining-space",
            )


#: A real go parser diagnostic, matched by conformance._ZIP_REJECTIONS["go"].
_GO_REJECTION = b"zipstream.NewTDFReader failed: zip: not a valid zip file"
#: What the go shim actually prints on stdout before every run. The secret is
#: the point: nothing a tolerated outcome reports may contain it.
_GO_STDOUT = (
    b"otdfctl decrypt --with-client-creds "
    b'{"clientId":"opentdf","clientSecret":"hunter2"} in.tdf\n'
)
_SECRET = "hunter2"


def _fake_sdk(name: str = "go") -> tdfs.SDK:
    """An SDK stand-in that is never invoked -- only named and dispatched on."""
    sdk = create_autospec(tdfs.SDK, instance=True)
    sdk.sdk = name
    sdk.version = "fake"
    sdk.__str__.return_value = f"{name}@fake"
    return sdk


#: outcome -> (exit status, stderr). Exit 0 rows write plaintext instead.
_DECRYPT_OUTCOMES: dict[str, tuple[int, bytes]] = {
    "roundtrip": (0, b""),
    "wrong_plaintext": (0, b""),
    "clean_rejection": (1, _GO_REJECTION),
    "unrelated_failure": (1, b"connection refused"),
    "runtime_crash": (2, b"panic: runtime error: makeslice: len out of range"),
    "signal_death": (-9, _GO_REJECTION),
}


@pytest.mark.parametrize("outcome", list(_DECRYPT_OUTCOMES))
def test_fake_record_conformance_accepts_only_safe_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
):
    """Run a real conformance cell offline against every outcome shape.

    The mutation is the same either way -- metadata stays readable and
    payload bytes stay intact, asserted inside the fake before it answers --
    so what this pins is the *verdict*. A faithful read and a clean rejection
    both pass; wrong bytes, an unrelated error, a panic and a signal death
    all fail. The cell is spec-legal, so its tolerated rejection must also
    warn.

    ``_bounded_decrypt`` is what gets faked, not ``SDK.decrypt``: the real
    path is ``decrypt_command`` -> ``Popen``, and faking one layer lower
    would mean spawning a process. ``_bounded_decrypt`` keeps its own
    coverage in ``test_bounded_decrypt_kills_descendants_on_timeout``.
    """
    src = _ordinary_zip(tmp_path / "src.zip")
    cd = zipinspect.central_directory(src)
    pt = tmp_path / "plaintext.bin"
    with zipfile.ZipFile(src) as z:
        pt.write_bytes(z.read("0.payload"))
    monkeypatch.setattr(conformance, "_base_container", lambda *args: src)
    sdk = _fake_sdk()
    calls: list[Path] = []

    def fake_decrypt(
        _sdk: tdfs.SDK, ct_file: Path, rt_file: Path, **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(ct_file)
        assert ct_file.read_bytes()[: cd.cd_offset] == src.read_bytes()[: cd.cd_offset]
        with zipfile.ZipFile(ct_file) as z:
            assert z.comment.startswith(zipinspect.CEN_SIG)
            (fake_offset,) = struct.unpack_from("<I", z.comment, 42)
            assert fake_offset > ct_file.stat().st_size
            assert z.namelist() == ["0.payload", "0.manifest.json"]
            payload = z.read("0.payload")  # also validates the CRC-32
            assert payload == pt.read_bytes()
        status, stderr = _DECRYPT_OUTCOMES[outcome]
        if status == 0:
            rt_file.write_bytes(b"wrong" if outcome == "wrong_plaintext" else payload)
        return subprocess.CompletedProcess(["fake-cli"], status, _GO_STDOUT, stderr)

    monkeypatch.setattr(conformance, "_bounded_decrypt", fake_decrypt)
    recorded: list[tuple[str, object]] = []

    def run_case() -> None:
        conformance.test_comment_containing_a_fake_central_directory_record(
            encrypt_sdk=sdk,
            decrypt_sdk=sdk,
            in_focus={sdk},
            zip_conformance_tdf=create_autospec(EncryptFactory, instance=True),
            attribute_default_rsa=create_autospec(Attribute, instance=True),
            tmp_path=tmp_path,
            zip_outcome=conformance.ZipOutcome(
                sdk, pt, "fake::node", lambda k, v: recorded.append((k, v))
            ),
        )

    failures = {
        "wrong_plaintext": "does not match",
        "unrelated_failure": "without a recognized ZIP rejection",
        "runtime_crash": "runtime failure",
        "signal_death": "did not reject normally",
    }
    if outcome in failures:
        with pytest.raises(AssertionError, match=failures[outcome]):
            run_case()
        assert not recorded, "a failed cell must not report an outcome"
    elif outcome == "clean_rejection":
        with pytest.warns(conformance.NonConformantZipReader):
            run_case()
        assert ("zip_conformance_outcome", "rejected") in recorded
        # The allowlist-matched slice, not the whole line: the line may be
        # anywhere in the combined output, including the credential-bearing
        # stdout the go shim echoes.
        diagnostics = [v for k, v in recorded if k == "zip_conformance_diagnostic"]
        assert diagnostics and str(diagnostics[0]) in _GO_REJECTION.decode()
    else:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_case()
        assert not [w for w in caught if issubclass(w.category, UserWarning)], (
            "a faithful roundtrip of a spec-legal structure is unremarkable "
            "and must not warn"
        )
        assert ("zip_conformance_outcome", "accepted") in recorded
    assert len(calls) == 1


@pytest.mark.parametrize("fields", conformance._ENTRY_ZIP64_FIELDS)
@pytest.mark.parametrize("zip64_eocd", [False, True])
def test_independent_entry_sentinels_preserve_contents(
    tmp_path: Path, fields: str, zip64_eocd: bool
):
    src = _ordinary_zip(tmp_path / "src.zip")
    trailer, cd_offset = zipmutate.load_trailer(src)
    original = trailer.entries[1]
    trailer.entries[1] = conformance._with_zip64_fields(original, fields)
    trailer = dataclasses.replace(trailer, force_zip64_eocd=zip64_eocd)
    dest = zipmutate.rewrite(src, tmp_path / "dest.zip", trailer)
    assert src.read_bytes()[:cd_offset] == dest.read_bytes()[:cd_offset]
    entry = zipinspect.central_directory(dest).entries[1]
    assert (entry.raw_compressed_size == 0xFFFFFFFF) == ("c" in fields)
    assert (entry.raw_uncompressed_size == 0xFFFFFFFF) == ("u" in fields)
    assert (entry.raw_local_header_offset == 0xFFFFFFFF) == ("o" in fields)
    assert entry.compressed_size == original.compressed_size
    assert entry.uncompressed_size == original.uncompressed_size
    assert entry.local_header_offset == original.local_header_offset
    with zipfile.ZipFile(src) as before, zipfile.ZipFile(dest) as after:
        for name in before.namelist():
            assert before.read(name) == after.read(name)
        assert after.getinfo("0.manifest.json").extract_version == 45
        assert after.getinfo("0.payload").extract_version == 20


@pytest.mark.parametrize("field", ["count", "size", "offset"])
def test_independent_eocd_sentinels(tmp_path: Path, field: str):
    src = _ordinary_zip(tmp_path / "src.zip")
    trailer, cd_offset = zipmutate.load_trailer(src)
    trailer = dataclasses.replace(
        trailer, force_zip64_eocd=True, zip64_eocd_fields=frozenset({field})
    )
    dest = zipmutate.rewrite(src, tmp_path / "dest.zip", trailer)
    tail = dest.read_bytes()[-zipinspect.EOCD_SIZE :]
    disk, cd_disk, count_disk, count, size, offset = struct.unpack_from(
        "<HHHHII", tail, 4
    )
    assert disk == cd_disk == 0
    assert count_disk == count == (0xFFFF if field == "count" else 2)
    assert size == (
        0xFFFFFFFF
        if field == "size"
        else sum(len(e.to_bytes()) for e in trailer.entries)
    )
    assert offset == (0xFFFFFFFF if field == "offset" else cd_offset)
    with zipfile.ZipFile(src) as before, zipfile.ZipFile(dest) as after:
        for name in before.namelist():
            assert before.read(name) == after.read(name)


def test_directory_entry_comment_preserves_following_entry(tmp_path: Path):
    src = _ordinary_zip(tmp_path / "src.zip")
    trailer, _ = zipmutate.load_trailer(src)
    trailer.entries[0] = dataclasses.replace(
        trailer.entries[0], comment=b"entry comment"
    )
    dest = zipmutate.rewrite(src, tmp_path / "dest.zip", trailer)
    assert len(zipinspect.central_directory(dest).entries) == 2
    with zipfile.ZipFile(src) as before, zipfile.ZipFile(dest) as after:
        assert after.getinfo("0.payload").comment == b"entry comment"
        assert after.comment == b""
        assert all(e.extract_version == 20 for e in after.infolist())
        for name in before.namelist():
            assert before.read(name) == after.read(name)


@pytest.mark.parametrize("case", conformance._MALFORMED_CASES)
def test_malformed_fixture_targets_metadata_only(tmp_path: Path, case: str):
    src = _ordinary_zip(tmp_path / "src.zip")
    before = zipinspect.central_directory(src)
    trailer = conformance._malformed_trailer(src, case)
    dest = zipmutate.rewrite(src, tmp_path / "dest.zip", trailer)
    raw = dest.read_bytes()
    assert raw[: before.cd_offset] == src.read_bytes()[: before.cd_offset]
    assert raw[-zipinspect.EOCD_SIZE : -zipinspect.EOCD_SIZE + 4] == zipinspect.EOCD_SIG
    assert raw[-2:] == b"\x00\x00"  # no archive comment masking the intended error
    if case in {
        "truncated_zip64_value",
        "extra_length_overrun",
        "impossible_entry_count",
    } or case.startswith(("locator_offset_", "directory_offset_")):
        with pytest.raises(MalformedZipError):
            zipinspect.central_directory(dest)
    else:
        cd = zipinspect.central_directory(dest)
        manifest = next(e for e in cd.entries if e.name == "0.manifest.json")
        if case.startswith("manifest_size_"):
            assert manifest.compressed_size > len(raw)
            assert manifest.uses_zip64_for_sizes
            assert manifest.compressed_size == (
                1 << 63 if case.endswith("_int64") else src.stat().st_size + 4096
            )
        elif case.startswith("header_offset_"):
            assert manifest.local_header_offset > len(raw)
            assert manifest.uses_zip64_for_offset
        else:
            payload = next(e for e in cd.entries if e.name == "0.payload")
            start = zipinspect.local_file_header_data_offset(dest, payload)
            assert start + payload.compressed_size == cd.cd_offset + 1
            assert payload.compressed_size == payload.uncompressed_size
            assert not payload.has_zip64_extra


@pytest.mark.parametrize(
    "sdk,diagnostic",
    [
        ("go", b"zipstream.NewTDFReader failed: zip: not a valid zip file"),
        ("go", b"zipstream.NewTDFReader failed: binary.Read failed: EOF"),
        (
            "go",
            b"tdfReader.Manifest failed: 0.manifest.json size too large: 4194303 KiB",
        ),
        ("go", b"tdfReader.Manifest failed: zip: file not found"),
        ("java", b"io.opentdf.platform.sdk.InvalidZipException: Invalid"),
        ("java", b"java.lang.IllegalArgumentException: tdf doesn't contain a manifest"),
        ("js", b"InvalidFileError: extra field length exceeds extra field buffer size"),
        (
            "js",
            b"InvalidFileError [TdfError]: zip64 extended information extra field does not include relative header offset",
        ),
        ("js", b"Error: Value exceeds MAX_SAFE_INTEGER: 9223372036854775808"),
    ],
)
def test_expected_parser_rejections_are_accepted(sdk: str, diagnostic: bytes):
    matched = conformance._assert_zip_rejection(
        sdk, subprocess.CompletedProcess(["fake-cli"], 1, b"", diagnostic)
    )
    assert matched, "a recognized rejection must name what it matched"
    assert matched in diagnostic.decode(), (
        "the returned diagnostic is what gets warned and recorded, so it must "
        "be a literal slice of the output, not a regex or a reconstruction"
    )


@pytest.mark.parametrize(
    "sdk,status,diagnostic",
    [
        ("go", 0, b""),
        ("go", -9, b"zip: not a valid zip file"),
        ("go", 137, b"zip: not a valid zip file"),
        ("go", 2, b"panic: runtime error: makeslice: len out of range"),
        ("go", 1, b"zip: not a valid zip file\njava.lang.OutOfMemoryError"),
        ("go", 1, b"zip: not a valid zip file\njava.lang.NegativeArraySizeException"),
        ("go", 1, b"zip: not a valid zip file\nRangeError: Invalid array length"),
        ("go", 1, b"authentication failed"),
        ("go", 1, b"connection refused"),
        ("go", 1, b"usage: decrypt input output"),
        ("go", 1, b"cipher: message authentication failed"),
        # Real diagnostics, deliberately not allowlisted: each is the SDK
        # noticing by accident downstream of its ZIP layer rather than
        # diagnosing the container, so none is evidence of a bounds check.
        # All three are filed upstream; see the comment above _ZIP_REJECTIONS.
        (
            "go",
            1,
            b"Failed to decrypt file: json.Unmarshal failed:"
            b"invalid character 'P' after top-level value",
        ),
        (
            "java",
            1,
            b"java.lang.IllegalArgumentException\n"
            b"\tat java.base/sun.nio.ch.FileChannelImpl.position"
            b"(FileChannelImpl.java:383)\n"
            b"\tat io.opentdf.platform.sdk.ZipReader."
            b"extractZIP64CentralDirectoryInfo(ZipReader.java:159)",
        ),
        (
            "js",
            1,
            b"SyntaxError: Unexpected end of JSON input\n"
            b"    at JSON.parse (<anonymous>)\n"
            b"    at ZipReader.getManifest (tdf3/src/utils/zip-reader.js:54:21)",
        ),
    ],
)
def test_abnormal_or_unrelated_failures_do_not_pass(
    sdk: str, status: int, diagnostic: bytes
):
    with pytest.raises(AssertionError):
        conformance._assert_zip_rejection(
            sdk, subprocess.CompletedProcess(["fake-cli"], status, b"", diagnostic)
        )


def _outcome_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reject: bool,
    faithful: bool = True,
) -> tuple[conformance.ZipOutcome, Path, Path, list[tuple[str, object]]]:
    """A ZipOutcome wired to a fake decrypt with a fixed verdict.

    The fake always answers with ``_GO_STDOUT`` so every path through
    ``_report`` is exercised against output that contains a credential.
    """
    pt = tmp_path / "plaintext.bin"
    pt.write_bytes(b"the original plaintext")
    ct = tmp_path / "mutated.tdf"
    ct.write_bytes(b"not actually read")
    rt = tmp_path / "roundtrip.bin"
    recorded: list[tuple[str, object]] = []

    def fake_decrypt(
        _sdk: tdfs.SDK, _ct: Path, rt_file: Path, **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        if not reject:
            rt_file.write_bytes(pt.read_bytes() if faithful else b"wrong bytes")
        return subprocess.CompletedProcess(
            ["fake-cli"],
            1 if reject else 0,
            _GO_STDOUT,
            _GO_REJECTION if reject else b"",
        )

    monkeypatch.setattr(conformance, "_bounded_decrypt", fake_decrypt)
    outcome = conformance.ZipOutcome(
        _fake_sdk(), pt, "fake::node", lambda k, v: recorded.append((k, v))
    )
    return outcome, ct, rt, recorded


@pytest.mark.parametrize("legality", ["spec-legal", "adversarial"])
@pytest.mark.parametrize("reject", [False, True], ids=["accepted", "rejected"])
def test_only_the_unexpected_quadrants_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legality: str, reject: bool
):
    """Both outcomes pass everywhere; exactly two of the four are remarkable.

    Refusing a structure APPNOTE permits, and reading a malformed one
    correctly, are the two ways to pass without being conformant. The other
    two quadrants are the expected result and must stay quiet, or the signal
    drowns in a nightly run's worth of noise.
    """
    outcome, ct, rt, recorded = _outcome_harness(tmp_path, monkeypatch, reject=reject)
    expected = {
        ("spec-legal", True): conformance.NonConformantZipReader,
        ("adversarial", False): conformance.LenientZipReader,
    }.get((legality, reject))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        outcome(ct, rt, legality=legality)  # type: ignore[arg-type]

    raised = [
        w for w in caught if issubclass(w.category, conformance.ZipConformanceWarning)
    ]
    if expected is None:
        assert not raised, (
            f"{legality}/{'rejected' if reject else 'accepted'} is the expected result"
        )
    else:
        assert [w.category for w in raised] == [expected]
    assert ("zip_conformance_outcome", "rejected" if reject else "accepted") in recorded
    assert ("zip_conformance_legality", legality) in recorded
    assert ("zip_conformance_sdk", "go") in recorded


@pytest.mark.parametrize("legality", ["spec-legal", "adversarial"])
@pytest.mark.parametrize("reject", [False, True], ids=["accepted", "rejected"])
def test_a_tolerated_outcome_never_echoes_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legality: str, reject: bool
):
    """The go and java shims print client credentials on stdout every run.

    Only the allowlist-matched slice of the output may reach a warning or a
    recorded property -- those end up in CI logs and junit artifacts. A
    well-meaning change to report "more context" is exactly how a secret
    would get published, so pin it on every quadrant.
    """
    outcome, ct, rt, recorded = _outcome_harness(tmp_path, monkeypatch, reject=reject)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        outcome(ct, rt, legality=legality)  # type: ignore[arg-type]

    assert _SECRET in _GO_STDOUT.decode(), "the fixture must actually carry a secret"
    for w in caught:
        assert _SECRET not in str(w.message)
    for key, value in recorded:
        assert _SECRET not in f"{key}{value}"


def test_silent_corruption_fails_whatever_the_legality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Exit 0 with the wrong bytes is the one outcome nothing tolerates."""
    outcome, ct, rt, recorded = _outcome_harness(
        tmp_path, monkeypatch, reject=False, faithful=False
    )
    with pytest.raises(AssertionError, match="silent corruption"):
        outcome(ct, rt, legality="adversarial")
    assert not recorded


def test_exit_zero_without_output_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A reader that claims success and writes nothing has not round-tripped.

    filecmp.cmp would raise FileNotFoundError here rather than fail the
    assertion, which reads as a harness bug instead of an SDK one.
    """
    pt = tmp_path / "plaintext.bin"
    pt.write_bytes(b"the original plaintext")
    monkeypatch.setattr(
        conformance,
        "_bounded_decrypt",
        lambda *_a, **_k: subprocess.CompletedProcess(["fake-cli"], 0, b"", b""),
    )
    outcome = conformance.ZipOutcome(_fake_sdk(), pt, "fake::node", lambda _k, _v: None)
    with pytest.raises(AssertionError, match="without writing"):
        outcome(
            tmp_path / "mutated.tdf", tmp_path / "missing.bin", legality="spec-legal"
        )


def test_bounded_decrypt_kills_descendants_on_timeout(tmp_path: Path):
    """Use a real fake CLI: its child would keep writing if only the shell died."""
    import sys
    import time

    heartbeat = tmp_path / "heartbeat"
    child_code = (
        "import pathlib, sys, time\n"
        "p = pathlib.Path(sys.argv[1])\n"
        "while True:\n"
        "    with p.open('ab') as f: f.write(b'x')\n"
        "    time.sleep(0.01)\n"
    )
    parent_code = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])\n"
        "time.sleep(30)\n"
    )
    sdk = create_autospec(tdfs.SDK, instance=True)
    sdk.decrypt_command.return_value = (
        [sys.executable, "-c", parent_code, child_code, str(heartbeat)],
        {},
    )
    with pytest.raises(pytest.fail.Exception, match="timed out"):
        conformance._bounded_decrypt(sdk, tmp_path / "in", tmp_path / "out", timeout=1)
    assert heartbeat.exists(), "fake CLI child never started"
    after_kill = heartbeat.read_bytes()
    time.sleep(0.1)
    assert heartbeat.read_bytes() == after_kill
