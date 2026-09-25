"""Cross-SDK structural/adversarial ZIP conformance tests (DSPX-4591 follow-up).

``test_zip64.py`` covers *size-boundary offset placement* -- whether a
payload's local-header offset lands in the ``[2**31, 2**32)`` band where a
signed 32-bit read goes negative. This module covers a different dimension:
*structural* ZIP layout -- spec-legal-but-unusual central-directory/EOCD
shapes, and adversarial ones -- that any conformant reader must handle
correctly regardless of which SDK produced or is consuming the container.

web-sdk PR #1017 (DSPX-4591) fixed four bugs in exactly this area, found and
verified only by that one SDK's own unit tests, never cross-SDK:

1. backward byte-scanning for the central-directory signature instead of
   properly locating EOCD -> (ZIP64 locator ->) ZIP64 EOCD -> walking exactly
   ``entryCount`` records by declared length,
2. the ZIP64 extra field gated on ``versionNeededToExtract >= 45`` instead of
   purely on the presence of the ``0xFFFFFFFF`` sentinel (APPNOTE 4.5.3),
3. a non-ZIP64 data descriptor writing the uncompressed size into both size
   slots,
4. a signed 32-bit shift corrupting an error message for sizes >= 2 GiB.

The tests below exercise (1) and ZIP64 extra-field ordering cross-SDK, at a
128-byte payload rather than a multi-GiB one. ZIP64 records declare version
4.5 as APPNOTE 4.4.3 requires; tolerance of a 2.0 declaration is tested only
for the Python inspector in ``test_zip_conformance_units.py``. These tests
mutate the container's *trailer* after encryption
(see ``zipmutate.py``), so payload size has no bearing on what they test.
Only web-sdk (``js``) is used as ``encrypt_sdk`` -- it always writes ZIP64
regardless of size, per the ``zip64-at-2gib`` feature in ``tdfs.py`` -- so no
multi-GiB payload is ever needed to manufacture ZIP64 structure here. Every
``decrypt_sdk`` in the run matrix is exercised against each mutated
container.

Platform PR #3981 adds independent ZIP64 EOCD triggers, conditional per-entry
ZIP64 fields, and correct traversal past directory-entry comments. The small
fixtures here cover those behaviors without exercising writer size thresholds.
Platform PR #4043 adds bounds on untrusted ZIP64 sizes/offsets. Go unit tests
retain coverage of caller-supplied subread indexes and injected writer
thresholds, which CLI decryption cannot isolate.

Every mutated container below -- spec-legal and adversarial alike -- is held
to one rule: decrypt either exits 0 with byte-identical plaintext, or rejects
the container cleanly (a normal nonzero exit, no runtime-crash marker, and a
diagnostic this SDK's parser is known to emit). Silent corruption, a panic or
signal death, a timeout, and a failure about something other than the
container all fail the cell.

The point of a cross-SDK suite is to find wire disagreements and data loss,
not to fail nightly because one reader declines a 0xFFFF comment -- so
refusing a spec-legal structure, and accepting a malformed one, both pass.
Both also emit a :class:`ZipConformanceWarning` and record the SDK, the cell
and the matched diagnostic, so a green matrix still says which readers are
conformant and which are merely safe. ``zipreport.py`` collects those records
into the table printed at the end of the run.

A cell is ``adversarial`` when the container contradicts itself -- two fields
disagree, or one points outside the file -- so a wrong answer exists to be
returned and accepting it means declining to notice. A cell that is merely
unusual, or that crosses a recommendation while staying internally consistent
and unambiguous to parse, is ``spec-legal``: accepting is the conformant
answer and only a rejection is worth reporting. Readers should be liberal in
what they accept, and warning about correct behavior trains people to ignore
the warnings.

(3) and (4) are latent/cosmetic single-implementation issues with no
cross-SDK wire disagreement; see the module docstring discussion in the
project plan for why they are out of scope here.

Run it with::

    uv run pytest test_zip_conformance.py --sdks "go java js" -v

...and to see every cell where a reader was merely safe rather than
conformant, not just the first per source line::

    PYTHONPATH=. uv run pytest test_zip_conformance.py --sdks "go java js" \
        -W always::test_zip_conformance.ZipConformanceWarning

``-W`` resolves its category by importing the named module at
argument-parse time, before pytest has put the rootdir on ``sys.path``;
without ``PYTHONPATH=.`` the filter is dropped with a
``PytestConfigWarning`` and the warnings stay deduplicated. They are
reported either way -- the flag only defeats the once-per-location default.
"""

import dataclasses
import filecmp
import os
import re
import signal
import struct
import subprocess
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pytest

import tdfs
import zipinspect
import zipmutate
import zipreport
from abac import Attribute
from fixtures.encryption import EncryptFactory

# ``no_audit_logs``: nothing here requests the ``audit_logs`` fixture -- this
# module tests container encoding, not KAS rewrap events.
pytestmark = [pytest.mark.zip_conformance, pytest.mark.no_audit_logs]

#: An extended-timestamp extra-field record (header id 0x5455), the shape
#: real writers actually put ahead of a ZIP64 record in the wild.
_FOREIGN_EXTRA_TLV = struct.pack("<HH", 0x5455, 5) + b"\x01\x00\x00\x00\x00"

# Each field can independently defer to the ZIP64 extra field. STORED sizes
# are equal, so these cases test conditional presence, not swapped size values.
_ENTRY_ZIP64_FIELDS = ["c", "u", "o", "cu", "co", "uo", "cuo"]


def _with_zip64_fields(
    entry: zipmutate.MutableEntry, fields: str
) -> zipmutate.MutableEntry:
    return dataclasses.replace(
        entry,
        force_zip64_compressed_size="c" in fields,
        force_zip64_uncompressed_size="u" in fields,
        force_zip64_offset="o" in fields,
        version_needed_to_extract=45,
        extra_prefix=_FOREIGN_EXTRA_TLV,
    )


def _assert_faithful_roundtrip(
    decrypt_sdk: tdfs.SDK, ct_file: Path, rt_file: Path, pt_file: Path
) -> None:
    """The unmutated control: decrypt must succeed and be byte-correct.

    Mutated containers go through :class:`ZipOutcome`, which also accepts a
    clean rejection. This one does not, and has exactly one caller --
    ``readable_zip_base``. An SDK that cannot read the container it was
    handed before any mutation is a broken environment, not a finding about
    ZIP conformance, and every other assertion in this module is worthless
    until that is ruled out.
    """
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file, shallow=False), (
        f"{decrypt_sdk} decrypted {ct_file.name} without error but the "
        f"output does not match the original plaintext"
    )


def _bounded_decrypt(
    sdk: tdfs.SDK, ct_file: Path, rt_file: Path, *, timeout: float = 30
) -> subprocess.CompletedProcess[bytes]:
    """Bound malformed-input runs, including descendants of the CLI shim.

    PIPE output is drained by communicate; on timeout kill the whole process
    group so a shell's child cannot keep running or hold the pipes open.
    """
    command, local_env = sdk.decrypt_command(ct_file, rt_file, "ztdf")
    with subprocess.Popen(
        command,
        env=os.environ | local_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # The group exited between the timeout and the kill.
            process.communicate()
            pytest.fail(f"{sdk} ZIP decrypt timed out after {timeout}s")
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


_RUNTIME_FAILURE = re.compile(
    r"panic:|fatal error:|runtime error:|out of memory|outofmemoryerror|"
    r"negativearraysizeexception|indexoutofboundsexception|bufferunderflowexception|"
    r"rangeerror:|segmentation fault|core dumped|killed:",
    re.IGNORECASE,
)
# Match parser diagnostics, not arbitrary nonzero exits (auth/network/usage
# failures must not pass). Keep these tied to observed CLI errors, with
# offline tests for both expected rejection and unrelated/runtime failures.
#
# To add one: run with --html, pull the failing cells' captured logs out of
# the report's data-jsonblob, and copy the string _verbatim as a bytes
# literal_ into test_expected_parser_rejections_are_accepted first. Watch it
# fail, widen the regex until it passes, then re-run
# test_abnormal_or_unrelated_failures_do_not_pass to confirm the widening did
# not also swallow auth/network/usage. (--show-capture=no discards exactly
# the output you need here.)
#
# Deliberately absent, because noticing by accident downstream of the ZIP
# layer is not a parser diagnostic -- the same reason _RUNTIME_FAILURE
# refuses NegativeArraySizeException: java's message-less
# IllegalArgumentException from a 1<<63 seek reaching FileChannelImpl.position
# via ZipReader.extractZIP64CentralDirectoryInfo; js's "SyntaxError:
# Unexpected end of JSON input" from handing an empty read to JSON.parse in
# zip-reader.js; and go's "json.Unmarshal failed:invalid character 'P' after
# top-level value", which is the manifest decoder reading past the manifest
# into payload bytes. All three are filed upstream; all three are pinned as
# negative rows in test_abnormal_or_unrelated_failures_do_not_pass.
_ZIP_REJECTIONS = {
    "go": re.compile(
        r"zip: (?:not a valid|unable to read|file not found)|"
        r"zipstream\.NewTDFReader failed: (?:binary\.Read|readSeeker\.Seek|io\.ReadFull) failed:|"
        r"tdfReader\.Manifest failed:.*(?:EOF|0\.manifest\.json size too large)",
        re.IGNORECASE,
    ),
    "java": re.compile(
        r"InvalidZipException|EOFException|IllegalArgumentException: tdf doesn't contain a manifest",
        re.IGNORECASE,
    ),
    "js": re.compile(
        r"InvalidFileError(?: \[TdfError\])?: [^\n]*"
        r"(?:central directory|zip64|extra field|retrieve CD|manifest file too large)|"
        r"Value exceeds MAX_SAFE_INTEGER",
        re.IGNORECASE,
    ),
}


def _assert_zip_rejection(sdk: str, result: subprocess.CompletedProcess[bytes]) -> str:
    """Assert a clean parser rejection; return the diagnostic that was matched.

    The return value is the *matched substring*, deliberately not the output:
    callers warn and record it, and the go and java shims echo command lines
    carrying local client credentials on stdout (js redacts via
    ``echo_redacted``; the others do not). The matched slice comes from
    ``_ZIP_REJECTIONS``, so it can only ever be parser wording.

    The stderr tail in the final assertion message is load-bearing: it is how
    a diagnostic missing from the allowlist gets harvested. See the comment
    above ``_ZIP_REJECTIONS``.
    """
    output = (result.stdout + b"\n" + result.stderr).decode(errors="replace")
    # Do not let pytest's assertion expansion print CompletedProcess.stdout:
    # some CLI shims echo commands containing local client credentials.
    status = result.returncode
    assert 0 < status < 128, f"{sdk} did not reject normally: exit {status}"
    crash = _RUNTIME_FAILURE.search(output)
    assert crash is None, f"{sdk} runtime failure: {crash.group() if crash else ''}"
    match = _ZIP_REJECTIONS[sdk].search(output)
    assert match, (
        f"{sdk} failed without a recognized ZIP rejection (exit {status}):\n"
        + result.stderr.decode(errors="replace")[-2000:]
    )
    return match.group()


#: Whether a mutation produces a structure APPNOTE permits ("spec-legal") or
#: one it does not ("adversarial"). This never changes whether a cell passes
#: -- only which of the two passing outcomes is worth reporting.
Legality = Literal["spec-legal", "adversarial"]


class ZipConformanceWarning(UserWarning):
    """A cell that passes, but whose outcome belongs in the run log."""


class NonConformantZipReader(ZipConformanceWarning):
    """Refused a structure APPNOTE permits. Safe, but strict in the wrong place."""


class LenientZipReader(ZipConformanceWarning):
    """Read a deliberately malformed container. Right bytes, but no guard."""


class ZipOutcome:
    """Decrypt a mutated container and hold it to the one universal rule.

    Two outcomes pass:

    * exit 0 with byte-identical plaintext, or
    * a clean rejection -- exit ``0 < n < 128``, no runtime-crash marker, and
      a diagnostic this SDK's parser is known to emit.

    Everything else fails: exit 0 with the wrong bytes (silent corruption), a
    panic or signal death, a timeout, or a nonzero exit whose diagnostic is
    about something other than the container (auth, network, usage).

    Rejecting a spec-legal structure and accepting an adversarial one are the
    two ways to pass without being conformant, so each is recorded and warned
    about. ``legality`` selects which; it does not move the pass/fail line.
    """

    def __init__(
        self,
        decrypt_sdk: tdfs.SDK,
        pt_file: Path,
        node_id: str,
        record_property: Callable[[str, object], None],
    ) -> None:
        self._sdk = decrypt_sdk
        self._pt_file = pt_file
        self._node_id = node_id
        self._record_property = record_property

    def __call__(self, ct_file: Path, rt_file: Path, *, legality: Legality) -> None:
        result = _bounded_decrypt(self._sdk, ct_file, rt_file)
        if result.returncode:
            self._report(
                "rejected", legality, _assert_zip_rejection(self._sdk.sdk, result)
            )
            return
        assert rt_file.is_file(), (
            f"{self._sdk} exited 0 decrypting {ct_file.name} without writing "
            f"{rt_file.name}"
        )
        assert filecmp.cmp(self._pt_file, rt_file, shallow=False), (
            f"{self._sdk} exited 0 decrypting a deliberately mutated "
            f"{ct_file.name}, but the output does not match the original "
            f"plaintext -- this is silent corruption, not a clean failure"
        )
        self._report("accepted", legality, "")

    def _report(self, outcome: str, legality: Legality, diagnostic: str) -> None:
        # ``diagnostic`` is the allowlist-matched substring only, never
        # result.stdout: the go and java shims echo command lines carrying
        # local client credentials.
        self._record_property(
            zipreport.PROPERTY,
            zipreport.encode(self._sdk.sdk, legality, outcome, diagnostic),
        )
        if outcome == "rejected" and legality == "spec-legal":
            warnings.warn(
                f"{self._sdk} rejected a spec-legal structure "
                f"({self._node_id}): {diagnostic}",
                NonConformantZipReader,
                stacklevel=3,
            )
        elif outcome == "accepted" and legality == "adversarial":
            warnings.warn(
                f"{self._sdk} read a deliberately malformed container "
                f"({self._node_id}) and returned the correct plaintext -- it "
                f"has no guard here, only luck",
                LenientZipReader,
                stacklevel=3,
            )


@pytest.fixture
def zip_outcome(
    request: pytest.FixtureRequest,
    decrypt_sdk: tdfs.SDK,
    zip_conformance_pt_file: Path,
) -> ZipOutcome:
    """A decrypt-and-judge callable bound to this cell.

    The cell's outcomes are per-test state, so a module-level helper cannot
    reach them. Binding the recorder here along with the decrypting SDK and
    the plaintext is what keeps every call site a one-liner instead of
    threading three values through ten test signatures no test body reads.

    ``item.user_properties`` is appended to directly rather than through the
    ``record_property`` fixture. They are the same list -- the fixture is that
    append plus a warning that ``junit_family``'s default xunit2 schema has
    nowhere to put the result. ``conftest.py`` collects these in-process (see
    ``zipreport.py``), so the junit XML is not the channel and the warning's
    advice to set ``junit_family = xunit1`` would buy nothing.
    """
    item = request.node
    assert isinstance(item, pytest.Item)

    def record(name: str, value: object) -> None:
        item.user_properties.append((name, value))

    return ZipOutcome(
        decrypt_sdk,
        zip_conformance_pt_file,
        item.nodeid,
        record,
    )


def _base_container(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    zip_conformance_tdf: EncryptFactory,
    attribute_default_rsa: Attribute,
) -> Path:
    """The one real, unmutated TDF each case starts from.

    Only ``js`` (web-sdk) is used: it always writes ZIP64 regardless of
    payload size, so a 128-byte plaintext already has the structure these
    tests want to reshape. go/java cells for this fixture are skipped
    rather than parametrized away, so each test still reports one cell per
    ``decrypt_sdk`` instead of vanishing from the matrix.
    """
    if encrypt_sdk.sdk != "js":
        pytest.skip(
            "structural mutation needs exactly one producer; js is used "
            "because it always emits ZIP64 regardless of payload size"
        )
    return zip_conformance_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )


def test_zip64_extra_field_not_first_is_still_resolved(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """Resolve a ZIP64 offset after a foreign extra-field TLV.

    An extended timestamp precedes the ZIP64 record to prove the reader does
    not assume ZIP64 comes first. This entry requires extraction version 4.5
    because it uses ZIP64; the other entries retain version 2.0.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    true_offset: int | None = None
    for i, entry in enumerate(trailer.entries):
        if entry.name == "0.manifest.json":
            true_offset = entry.local_header_offset
            trailer.entries[i] = dataclasses.replace(
                entry,
                force_zip64_offset=True,
                extra_prefix=_FOREIGN_EXTRA_TLV,
                version_needed_to_extract=45,
            )
            break
    assert true_offset is not None, f"{ct_file} has no 0.manifest.json entry"

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    cd = zipinspect.central_directory(mutated)
    manifest_entry = next(e for e in cd.entries if e.name == "0.manifest.json")
    assert manifest_entry.has_zip64_extra, (
        "ZIP64 extra field was not resolved when preceded by a foreign extra "
        f"record with version_needed_to_extract=45\n{zipinspect.describe(cd.entries)}"
    )
    assert manifest_entry.uses_zip64_for_offset
    assert manifest_entry.local_header_offset == true_offset

    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


def test_eocd_with_max_length_comment(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """A maximum-length (0xFFFF) EOCD comment is spec-legal and must round-trip."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    trailer = dataclasses.replace(trailer, comment=b"c" * 0xFFFF)

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


def test_zip64_locator_pushed_past_first_1kib_by_comment(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """A ZIP64 EOCD + locator that is not size-mandated is spec-legal.

    Nothing here needs ZIP64 -- the container is a few hundred bytes -- but
    APPNOTE does not forbid using it anyway, and a maximum-length comment
    then pushes the locator behind whatever a reader's naive "look at the
    last 1 KiB" tail read would have found.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    trailer = dataclasses.replace(trailer, force_zip64_eocd=True, comment=b"c" * 0xFFFF)

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    cd = zipinspect.central_directory(mutated)
    assert {e.name for e in cd.entries} == {"0.payload", "0.manifest.json"}, (
        "zipinspect failed to find the ZIP64 locator behind the max-length "
        f"comment\n{zipinspect.describe(cd.entries)}"
    )

    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


@pytest.mark.parametrize("count_offset", [1, None], ids=["real_plus_one", "0xFFFF"])
def test_central_directory_entry_count_is_overstated(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
    count_offset: int | None,
):
    """DSPX-4591 finding 1, from the opposite direction.

    An entry count that overstates what the central directory actually holds
    must be refused, not walked past into whatever bytes happen to follow --
    which for a reader that trusts the declared count over the real content
    is exactly the shape of the misparse that finding fixed. The
    ``0xFFFF`` case is the boundary value APPNOTE reserves to mean "see the
    ZIP64 EOCD instead", asserted here with no such record to back it up.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    trailer, _ = zipmutate.load_trailer(ct_file)
    real_count = len(trailer.entries)
    declared_count = real_count + count_offset if count_offset is not None else 0xFFFF
    trailer = dataclasses.replace(trailer, entry_count_override=declared_count)

    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    with pytest.raises(zipinspect.MalformedZipError):
        zipinspect.central_directory(mutated)

    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="adversarial")


def test_comment_containing_a_fake_central_directory_record(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """DSPX-4591 finding 1, the case that motivated it.

    A ZIP comment can contain a complete central-directory record without
    making it an entry. The bogus record points past EOF, so interpreting it
    as structure causes a read failure. Unlike patching encrypted payload
    bytes, changing the comment preserves authentication -- so a reader that
    stays anchored to the trailer gets the plaintext back, and nothing here
    can be mistaken for an expected integrity failure. A reader that follows
    the planted record instead must say so as a ZIP error; the warning names
    it as non-conformant.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )

    cd_before = zipinspect.central_directory(ct_file)
    trailer, _ = zipmutate.load_trailer(ct_file)
    manifest = next(e for e in trailer.entries if e.name == "0.manifest.json")
    fake_record = dataclasses.replace(
        manifest, local_header_offset=ct_file.stat().st_size + 0x10000
    ).to_bytes()
    trailer = dataclasses.replace(trailer, comment=fake_record)
    mutated = tmp_path / "mutated.tdf"
    zipmutate.rewrite(ct_file, mutated, trailer)

    cd_after = zipinspect.central_directory(mutated)
    before = [(e.name, e.local_header_offset) for e in cd_before.entries]
    after = [(e.name, e.local_header_offset) for e in cd_after.entries]
    assert after == before, (
        "planting a central-directory record inside the ZIP comment changed "
        "what the trailer-anchored parser reports -- it should not\n"
        + zipinspect.describe(cd_after.entries)
    )

    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


@pytest.mark.parametrize("eocd_field", ["count", "size", "offset"])
def test_zip64_eocd_independent_sentinel(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
    eocd_field: str,
):
    """Any one sentinel can require ZIP64; other EOCD values stay truthful.

    Size-only is compatibility coverage: a reader ignoring directory size
    could pass it without ever consulting ZIP64. Count-only catches #3981's
    former dependence on the offset sentinel.
    """
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )
    trailer, _ = zipmutate.load_trailer(ct_file)
    trailer = dataclasses.replace(
        trailer, force_zip64_eocd=True, zip64_eocd_fields=frozenset({eocd_field})
    )
    mutated = zipmutate.rewrite(ct_file, tmp_path / "mutated.tdf", trailer)
    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


@pytest.mark.parametrize("fields", _ENTRY_ZIP64_FIELDS)
@pytest.mark.parametrize("zip64_eocd", [False, True], ids=["zip32_eocd", "zip64_eocd"])
def test_zip64_entry_independent_sentinels(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
    fields: str,
    zip64_eocd: bool,
):
    """Resolve only the sentinel-selected values, after a foreign extra TLV."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )
    trailer, _ = zipmutate.load_trailer(ct_file)
    trailer = dataclasses.replace(trailer, force_zip64_eocd=zip64_eocd)
    trailer.entries[:] = [
        _with_zip64_fields(e, fields) if e.name == "0.manifest.json" else e
        for e in trailer.entries
    ]
    mutated = zipmutate.rewrite(ct_file, tmp_path / "mutated.tdf", trailer)
    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


def test_central_directory_entry_comment(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_outcome: ZipOutcome,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
):
    """An entry comment must not desynchronize traversal to the manifest."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )
    trailer, _ = zipmutate.load_trailer(ct_file)
    assert [e.name for e in trailer.entries] == ["0.payload", "0.manifest.json"]
    trailer.entries[0] = dataclasses.replace(
        trailer.entries[0], comment=b"comment on the payload directory entry"
    )
    mutated = zipmutate.rewrite(ct_file, tmp_path / "mutated.tdf", trailer)
    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")


@pytest.fixture
def readable_zip_base(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    zip_conformance_tdf: EncryptFactory,
    zip_conformance_pt_file: Path,
    attribute_default_rsa: Attribute,
    tmp_path: Path,
) -> Path:
    """Prove this SDK/environment reads the control before testing rejection."""
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    ct_file = _base_container(
        encrypt_sdk, decrypt_sdk, zip_conformance_tdf, attribute_default_rsa
    )
    _assert_faithful_roundtrip(
        decrypt_sdk, ct_file, tmp_path / "control.bin", zip_conformance_pt_file
    )
    return ct_file


_MALFORMED_CASES = [
    "truncated_zip64_value",
    "extra_length_overrun",
    "manifest_size_int64",
    "manifest_size_eof",
    "payload_overlaps_directory",
    "header_offset_int64",
    "header_offset_eof",
    "locator_offset_int64",
    "locator_offset_eof",
    "directory_offset_int64",
    "directory_offset_eof",
    "impossible_entry_count",
]


def _malformed_trailer(src: Path, case: str) -> zipmutate.MutableTrailer:
    """One malformed declaration per fixture; ciphertext/local headers survive.

    No archive comment: the independent Go/JS comment bugs must not short
    circuit the reader before it reaches the declaration under test. Positive
    oversized values stay small enough that an old reader cannot allocate GiB.
    """
    trailer, cd_offset = zipmutate.load_trailer(src)
    manifest_index = next(
        i for i, e in enumerate(trailer.entries) if e.name == "0.manifest.json"
    )
    manifest = trailer.entries[manifest_index]
    # About 4 KiB past EOF, allowing for these small ZIP64 records.
    beyond = 1 << 63 if case.endswith("_int64") else src.stat().st_size + 4096
    if case in {"truncated_zip64_value", "extra_length_overrun"}:
        extra = (
            struct.pack("<HHI", 1, 4, 0)
            if case == "truncated_zip64_value"
            else struct.pack("<HHQ", 1, 0xFFFF, manifest.local_header_offset)
        )
        trailer.entries[manifest_index] = dataclasses.replace(
            manifest,
            force_zip64_offset=True,
            version_needed_to_extract=45,
            extra_override=extra,
        )
    elif case.startswith("manifest_size_"):
        trailer.entries[manifest_index] = dataclasses.replace(
            manifest,
            compressed_size=beyond,
            force_zip64_compressed_size=True,
            version_needed_to_extract=45,
        )
    elif case == "payload_overlaps_directory":
        cd = zipinspect.central_directory(src)
        payload = next(e for e in cd.entries if e.name == "0.payload")
        data_start = zipinspect.local_file_header_data_offset(src, payload)
        for i, entry in enumerate(trailer.entries):
            if entry.name == "0.payload":
                trailer.entries[i] = dataclasses.replace(
                    entry,
                    compressed_size=cd_offset - data_start + 1,
                    uncompressed_size=cd_offset - data_start + 1,
                )
    elif case.startswith("header_offset_"):
        trailer.entries[manifest_index] = dataclasses.replace(
            manifest,
            local_header_offset=beyond,
            force_zip64_offset=True,
            version_needed_to_extract=45,
        )
    elif case.startswith("locator_offset_"):
        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=True, zip64_locator_offset_override=beyond
        )
    elif case.startswith("directory_offset_"):
        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=True, cd_offset_override=beyond
        )
    elif case == "impossible_entry_count":
        trailer = dataclasses.replace(
            trailer, force_zip64_eocd=True, entry_count_override=(1 << 64) - 1
        )
    else:
        raise ValueError(f"unknown malformed ZIP case: {case}")
    return trailer


@pytest.mark.parametrize("case", _MALFORMED_CASES)
def test_malformed_zip_never_yields_wrong_plaintext(
    readable_zip_base: Path,
    zip_outcome: ZipOutcome,
    tmp_path: Path,
    case: str,
):
    """Malformed metadata must never produce the wrong bytes under exit 0.

    Rejecting is the conformant answer and the one #4043 adds bounds for: the
    manifest's 2**63 size targets its negative-allocation panic, and the
    payload overlapping the CD targets its tighter data boundary even when
    the manifest would otherwise allow decrypting just the real bytes.

    But a reader that ignores the lie, reads the honest records around it and
    hands back byte-correct plaintext has not lost anyone any data either --
    it is lenient, not broken. Both pass; the lenient one is warned about and
    recorded so the matrix still tells them apart. A panic, a signal death, a
    timeout, an unrelated failure, and above all exit 0 with the wrong bytes
    still fail. A passing cell alone is not evidence of a particular guard.
    """
    trailer = _malformed_trailer(readable_zip_base, case)
    mutated = zipmutate.rewrite(readable_zip_base, tmp_path / "mutated.tdf", trailer)
    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="adversarial")


@pytest.mark.parametrize(
    "record_length", [0xFFFF, 0x10000], ids=["at_limit", "over_limit"]
)
def test_directory_record_length_boundary(
    readable_zip_base: Path,
    zip_outcome: ZipOutcome,
    tmp_path: Path,
    record_length: int,
):
    """Keep names intact; a large foreign TLV exercises uint16 cursor addition.

    Both cells are spec-legal. APPNOTE 4.4.10-12 sizes each of the three
    length fields as its own uint16, so every field here is representable and
    only their *sum* crosses the 65535 the note recommends -- a SHOULD with no
    field behind it. Nothing in either record contradicts anything else: the
    declared lengths are truthful and the next record begins exactly where
    they say, so there is one possible parse and it is the right one. That is
    what separates this from the cells in
    ``test_malformed_zip_never_yields_wrong_plaintext``, where two parts of
    the container disagree and a wrong answer is available to be returned.

    So accepting is conformant at both lengths and only a rejection is worth
    reporting. Refusing ``over_limit`` costs real interop -- timestamp, Unix
    UID/GID, ACL and signing TLVs push third-party records past 65535, and a
    reader has to *add* code to compute the combined size and refuse it, since
    that check does not fall out of parsing. Marking it adversarial would warn
    about correct behavior.

    A reader that adds these in uint16 still cannot pass quietly: the cursor
    wraps, so it mis-parses into wrong bytes (a hard failure), a rejection
    (warned here) or a hang (the decrypt timeout). Go's unit test separately
    requires correct cursor arithmetic.
    """
    trailer, _ = zipmutate.load_trailer(readable_zip_base)
    first = trailer.entries[0]
    extra_length = record_length - zipinspect.CEN_FIXED_SIZE - len(first.name.encode())
    trailer.entries[0] = dataclasses.replace(
        first,
        extra_prefix=struct.pack("<HH", 0xBEEF, extra_length - 4)
        + b"x" * (extra_length - 4),
    )
    assert len(trailer.entries[0].to_bytes()) == record_length
    mutated = zipmutate.rewrite(readable_zip_base, tmp_path / "mutated.tdf", trailer)
    zip_outcome(mutated, tmp_path / "roundtrip.bin", legality="spec-legal")
