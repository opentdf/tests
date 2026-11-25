"""The zip-* fixtures: the web-basic tamper base with a rewritten trailer (central
directory and end records); every byte before the directory is the base's.

Each case reuses the construction of its cell in test_zip_conformance.py, via
zipmutate. Legal shapes must stay readable; adversarial ones contradict
themselves at the container layer. Offline: nothing here talks to the platform.
"""

import dataclasses
import sys
from collections.abc import Callable
from pathlib import Path

import zipinspect
import zipmutate
from corpus_gen import tamper

BASE = "web-basic"
MANIFEST = tamper.MANIFEST
PAYLOAD = tamper.PAYLOAD
FAKE_COMMENT = "zip-legal-comment-with-fake-cd-record"

Trailer = Callable[[Path], zipmutate.MutableTrailer]


def _replace_entry(trailer: zipmutate.MutableTrailer, name: str, **changes: object):
    i = next(i for i, e in enumerate(trailer.entries) if e.name == name)
    trailer.entries[i] = dataclasses.replace(trailer.entries[i], **changes)  # type: ignore[arg-type]


def _entry(src: Path, name: str, **changes: object) -> zipmutate.MutableTrailer:
    trailer, _ = zipmutate.load_trailer(src)
    _replace_entry(trailer, name, **changes)
    return trailer


def _with(src: Path, **changes: object) -> zipmutate.MutableTrailer:
    trailer, _ = zipmutate.load_trailer(src)
    return dataclasses.replace(trailer, **changes)  # type: ignore[arg-type]


def _malformed(case: str) -> Trailer:
    """A zipmutate.malformed_trailer case, as test_zip_conformance.py builds it."""
    return lambda src: zipmutate.malformed_trailer(src, case)


ZIP_TRAILERS: dict[str, Trailer] = {
    "zip-adversarial-directory-offset-past-eof": _malformed("directory_offset_eof"),
    "zip-adversarial-entry-count-overstated": lambda s: _with(
        s, entry_count_override=len(zipmutate.load_trailer(s)[0].entries) + 1
    ),
    "zip-adversarial-extra-length-overrun": _malformed("extra_length_overrun"),
    "zip-adversarial-header-offset-int64": _malformed("header_offset_int64"),
    "zip-adversarial-impossible-entry-count": _malformed("impossible_entry_count"),
    "zip-adversarial-manifest-size-past-eof": _malformed("manifest_size_eof"),
    "zip-adversarial-payload-overlaps-directory": _malformed(
        "payload_overlaps_directory"
    ),
    FAKE_COMMENT: zipmutate.fake_record_comment_trailer,
    "zip-legal-entry-comment": lambda s: _entry(
        s, PAYLOAD, comment=b"comment on the payload directory entry"
    ),
    "zip-legal-trailer-rebuilt": lambda s: zipmutate.load_trailer(s)[0],
    "zip-legal-zip64-entry-sentinels": lambda s: zipmutate.entry_sentinel_trailer(
        s, "cuo", zip64_eocd=True
    ),
    "zip-legal-zip64-eocd-count-sentinel": lambda s: _with(
        s, force_zip64_eocd=True, zip64_eocd_fields=frozenset({"count"})
    ),
    "zip-legal-zip64-extra-not-first": zipmutate.manifest_offset_after_foreign_extra,
}


def _case(trailer: Trailer) -> Callable[[Path, Path], None]:
    def build(base: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        zipmutate.rewrite(base, dest, trailer(base))

    return build


# name -> build(base, dest): rewrite the base's trailer into dest.
ZIP_CASES: dict[str, Callable[[Path, Path], None]] = {
    name: _case(t) for name, t in ZIP_TRAILERS.items()
}


def entry_bytes(tdf: Path, name: str) -> bytes:
    """A STORED entry's data as the central directory describes it; raises
    MalformedZipError if the directory or the entry's bounds do not hold."""
    cd = zipinspect.central_directory(tdf)
    entry = next((e for e in cd.entries if e.name == name), None)
    if entry is None:
        raise zipinspect.MalformedZipError(f"{tdf.name} has no {name}")
    start = zipinspect.local_file_header_data_offset(tdf, entry)
    end = start + entry.compressed_size
    if end > cd.cd_offset:
        raise zipinspect.MalformedZipError(f"{name} runs into the directory")
    return tdf.read_bytes()[start:end]


class ZipCaseError(ValueError):
    pass


def check_derived(name: str, base: Path, out: Path) -> None:
    """Fail unless ``out`` is ``base`` with only its trailer rebuilt as the case
    says, and the result is readable (legal) or differs from the base trailer
    (adversarial)."""
    _, cd_offset = zipmutate.load_trailer(base)
    raw = out.read_bytes()
    if raw[:cd_offset] != base.read_bytes()[:cd_offset]:
        raise ZipCaseError("local headers or entry data changed")
    if raw[cd_offset:] != ZIP_TRAILERS[name](base).to_bytes(cd_offset):
        raise ZipCaseError("trailer is not the case's")
    if name.startswith("zip-adversarial-"):
        want, _ = zipmutate.load_trailer(base)
        if ZIP_TRAILERS[name](base) == want:
            raise ZipCaseError("trailer is the base's")
        return
    if name == FAKE_COMMENT:
        # The comment plants a record; the trailer-anchored parse ignores it.
        a, b = (zipinspect.central_directory(p).entries for p in (base, out))
        if [(e.name, e.local_header_offset) for e in a] != [
            (e.name, e.local_header_offset) for e in b
        ]:
            raise ZipCaseError("the comment changed what the directory reports")
        return
    for entry in (MANIFEST, PAYLOAD):
        if entry_bytes(out, entry) != entry_bytes(base, entry):
            raise ZipCaseError(f"{entry} does not read back unchanged")


def run(scratch: Path) -> int:
    """Derive every zip-* fixture into scratch/stage and check each one."""
    stage = scratch / "stage"
    base = tamper.base_path(scratch, BASE)
    if not base.is_file():
        print(f"missing base {base.name}; run `write` first", file=sys.stderr)
        return 2
    for old in stage.glob("zip-*.tdf"):
        old.unlink()
    failed: list[str] = []
    for name, build in ZIP_CASES.items():
        out = stage / f"{name}.tdf"
        try:
            build(base, out)
            check_derived(name, base, out)
        except (
            ValueError,
            KeyError,
            OSError,
            zipinspect.MalformedZipError,
        ) as e:
            out.unlink(missing_ok=True)
            failed.append(f"{name}: {e!r}")
            continue
        print(f"ok   {name} (from {base.name})")
    for f in failed:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"{len(ZIP_CASES) - len(failed)}/{len(ZIP_CASES)} zip fixtures in {stage}")
    return 1 if failed else 0
