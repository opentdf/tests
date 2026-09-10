"""Integrity-algorithm selection (DSPX-4736) and the GMAC root downgrade (DSPX-4703).

Two halves of one boundary, which is why they share a module.

**Segments.** ``segmentHashAlg: GMAC`` means "the trailing 16 bytes of this
segment's ciphertext". AES-GCM has just produced a tag over exactly those
bytes under the DEK, so reading it out is a genuine MAC obtained for free.
Both GMAC and HS256 are legitimate here and must round-trip on every SDK
pair -- that is DSPX-4736, and the tests below gate on ``integrity_algs``.

**Root.** ``rootSignature.alg: GMAC`` means "the trailing 16 bytes of the
aggregate hash" -- the concatenation of the segment hashes, which AES-GCM has
never touched. There is no tag to extract, so the result is a copy of the last
segment hash: manifest data the attacker already controls, computed without
the key. Since ``alg`` is read from the unauthenticated manifest, any ordinary
HS256-rooted TDF can be downgraded onto that branch. That is DSPX-4703. The
two writer tests gate on ``gmac_root_option``; the reader exploit cases have
no flag to ask about and gate on an observed rejection instead -- see
:func:`skip_unless_gmac_root_rejected`.

Per-segment AEAD tags do not close the gap: nothing binds a segment to its
index or to the total segment count, so the ordered segment list is precisely
what the root signature -- and only the root signature -- protects. The
exploit cases below therefore truncate, reorder, and duplicate segments while
every individual segment keeps decrypting cleanly.

The controls are not optional. Without them ("untouched round-trips", "each
tamper without the forged signature already fails") an exploit case that
passes proves only that decryption is broken somehow, not that the downgrade
is what defeated the check.

Reference implementation of the attack, including the keyless forging helper:
``platform/sdk/tdf_root_signature_test.go``.
"""

import filecmp
import random
import string
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

import tdfs
from abac import Attribute
from fixtures.encryption import EncryptFactory

ManifestChange = Callable[[tdfs.Manifest], tdfs.Manifest]
PayloadChange = Callable[[bytes], bytes]

#: Both values of ``--segment-integrity-algorithm``. Both are valid at the
#: segment level; only ``hs256`` is valid at the root.
SEGMENT_ALGS: list[tdfs.integrity_algorithm] = ["gmac", "hs256"]

#: Decoded length of a segment hash, per algorithm. This is what catches an
#: SDK that accepts the flag and then ignores it: the manifest would still
#: claim the requested algorithm while carrying the other one's digests.
EXPECTED_HASH_BYTES: dict[tdfs.integrity_algorithm, int] = {
    "gmac": tdfs.GMAC_TAG_BYTES,
    "hs256": tdfs.HS256_DIGEST_BYTES,
}


# --- shared gating -----------------------------------------------------------


def skip_unless_in_play(
    encrypt_sdk: tdfs.SDK, decrypt_sdk: tdfs.SDK, in_focus: set[tdfs.SDK]
) -> None:
    if not in_focus & {encrypt_sdk, decrypt_sdk}:
        pytest.skip("Not in focus")
    tdfs.skip_hexless_skew(encrypt_sdk, decrypt_sdk)


# --- manifest and payload surgery --------------------------------------------


def compose(*changes: ManifestChange) -> ManifestChange:
    """Apply manifest changes left to right.

    Order matters for the exploit cases: the forged signature is computed from
    the segment list, so it has to be applied *after* whatever edits that list.
    """

    def change(manifest: tdfs.Manifest) -> tdfs.Manifest:
        for c in changes:
            manifest = c(manifest)
        return manifest

    return change


def keep_segments(n: int) -> ManifestChange:
    """Drop all but the first ``n`` segments.

    The payload entry keeps every segment's ciphertext; the reader walks the
    manifest, so the trailing bytes are simply never read.
    """

    def change(manifest: tdfs.Manifest) -> tdfs.Manifest:
        ii = manifest.encryptionInformation.integrityInformation
        ii.segments = ii.segments[:n]
        return manifest

    return change


def reverse_segments(manifest: tdfs.Manifest) -> tdfs.Manifest:
    ii = manifest.encryptionInformation.integrityInformation
    ii.segments = list(reversed(ii.segments))
    return manifest


def declare_root_alg(alg: str) -> ManifestChange:
    """Flip ``rootSignature.alg`` and leave the signature alone.

    The downgrade without the forgery -- one half of the attack, which must
    stay insufficient on its own.
    """

    def change(manifest: tdfs.Manifest) -> tdfs.Manifest:
        manifest.encryptionInformation.integrityInformation.rootSignature.alg = alg
        return manifest

    return change


def forge_root(alg: str = "GMAC") -> ManifestChange:
    def change(manifest: tdfs.Manifest) -> tdfs.Manifest:
        return tdfs.forge_gmac_root_signature(manifest, alg)

    return change


def reverse_payload_segments(sizes: list[int]) -> PayloadChange:
    """Reverse the ciphertext segments to match a reversed segment list.

    Still a keyless edit: the bytes are moved, never rewritten, so every
    segment keeps the GCM tag it was written with. Nothing in AES-GCM binds a
    segment to its index, which is exactly why per-segment authentication
    cannot notice a permutation.
    """

    def change(payload: bytes) -> bytes:
        assert sum(sizes) == len(payload), (
            f"manifest describes {sum(sizes)} ciphertext bytes but 0.payload "
            f"holds {len(payload)}; cannot slice it into segments"
        )
        chunks: list[bytes] = []
        offset = 0
        for n in sizes:
            chunks.append(payload[offset : offset + n])
            offset += n
        return b"".join(reversed(chunks))

    return change


def duplicate_segment(index: int) -> ManifestChange:
    """Insert a second copy of segment ``index`` right after the original.

    A replay within a single file: the duplicate is a byte-for-byte copy of a
    segment the recipient was always going to receive, just repeated. Neither
    its own GCM tag nor any other segment's tag has an opinion about how many
    times it appears.
    """

    def change(manifest: tdfs.Manifest) -> tdfs.Manifest:
        ii = manifest.encryptionInformation.integrityInformation
        seg = ii.segments[index]
        ii.segments = ii.segments[: index + 1] + [seg] + ii.segments[index + 1 :]
        return manifest

    return change


def duplicate_payload_segment(sizes: list[int], index: int) -> PayloadChange:
    """Repeat the ciphertext segment at ``index`` to match ``duplicate_segment``."""

    def change(payload: bytes) -> bytes:
        assert sum(sizes) == len(payload), (
            f"manifest describes {sum(sizes)} ciphertext bytes but 0.payload "
            f"holds {len(payload)}; cannot slice it into segments"
        )
        chunks: list[bytes] = []
        offset = 0
        for n in sizes:
            chunks.append(payload[offset : offset + n])
            offset += n
        chunks = chunks[: index + 1] + [chunks[index]] + chunks[index + 1 :]
        return b"".join(chunks)

    return change


def change_payload_end(payload: bytes) -> bytes:
    """Flip the last three payload bytes, which lands inside a segment's GCM tag."""
    replacement = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=3)
    ).encode()
    if replacement == payload[-3:]:
        return change_payload_end(payload)
    return payload[:-3] + replacement


# --- assertions ---------------------------------------------------------------


#: Substrings that mean decrypt died before it ever reached the integrity
#: check: an unreachable platform, a rejected token, DNS. Scoring one of those
#: as "the tamper was detected" is the vacuous green this module exists to rule
#: out, so they fail the test instead of passing it.
#:
#: Observed, not guessed -- go prints "Failed to connect to the platform." and
#: "Failed to authenticate with flag-provided client credentials.", node
#: surfaces ECONNREFUSED behind "fetch failed", and the JVM raises
#: ConnectException. A denylist cannot be exhaustive; an allowlist of accepted
#: rejection phrases could be, but it would break every time an SDK reworded an
#: error. This catches what a broken environment actually produces.
INFRA_FAILURE_MARKERS: tuple[bytes, ...] = (
    b"failed to connect to the platform",
    b"failed to authenticate",
    b"connection refused",
    b"econnrefused",
    b"fetch failed",
    b"getaddrinfo",
    b"no such host",
    b"unauthorized_client",
    b"invalid_client",
    b"connectexception",
    b"unknownhostexception",
)


def decrypt_failure(
    decrypt_sdk: tdfs.SDK, ct_file: Path, rt_file: Path
) -> subprocess.CalledProcessError | None:
    """Attempt a decrypt: the error if the file was refused, None if accepted.

    A non-zero exit on its own does not distinguish "the forgery was caught"
    from "KAS was down", and both arrive here as the same exception. Every
    tamper case in this module depends on that distinction, so screen the
    output for :data:`INFRA_FAILURE_MARKERS` and raise rather than report an
    environment outage as a rejection.
    """
    try:
        decrypt_sdk.decrypt(ct_file, rt_file, "ztdf", expect_error=True)
    except subprocess.CalledProcessError as exc:
        # expect_error folds stderr into stdout; read both so this survives
        # that changing.
        combined = ((exc.output or b"") + (exc.stderr or b"")).lower()
        for marker in INFRA_FAILURE_MARKERS:
            if marker in combined:
                raise AssertionError(
                    f"{decrypt_sdk} failed on {ct_file.name}, but with "
                    f"{marker.decode()!r} -- a broken environment, not a "
                    f"rejection. Nothing here is verified until that is fixed: "
                    f"[{combined!r}]"
                ) from exc
        assert combined.strip(), (
            f"{decrypt_sdk} exited {exc.returncode} on {ct_file.name} without "
            "saying anything; a silent non-zero exit could be any failure"
        )
        return exc
    return None


def assert_decrypt_fails(
    decrypt_sdk: tdfs.SDK, ct_file: Path, rt_file: Path, why: str
) -> subprocess.CalledProcessError:
    """Require decrypt to reject the file on the merits, returning the error."""
    exc = decrypt_failure(decrypt_sdk, ct_file, rt_file)
    if exc is None:
        raise AssertionError(f"{decrypt_sdk} accepted {ct_file.name}: {why}")
    return exc


def assert_root_is_hs256(manifest: tdfs.Manifest, encrypt_sdk: tdfs.SDK) -> None:
    alg = manifest.encryptionInformation.integrityInformation.rootSignature.alg
    # Absent or empty means HS256 in every reader; anything else -- GMAC above
    # all -- is a root a keyless attacker can reproduce.
    assert (alg or "HS256").upper() == "HS256", (
        f"{encrypt_sdk} wrote rootSignature.alg={alg!r}; only HS256 is an "
        "authenticated root construction (DSPX-4703)"
    )


def assert_segment_integrity(
    ct_file: Path, requested: tdfs.integrity_algorithm, encrypt_sdk: tdfs.SDK
) -> None:
    """The manifest carries the algorithm that was asked for, and its digests.

    Checking the digest lengths as well as the label is the point: an SDK that
    parses the flag and then hashes with the other algorithm would satisfy the
    label check alone, and its files would round-trip against itself.
    """
    manifest = tdfs.manifest(ct_file)
    ii = manifest.encryptionInformation.integrityInformation
    assert ii.segmentHashAlg.upper() == requested.upper(), (
        f"{encrypt_sdk} was asked for segmentHashAlg={requested!r} and wrote "
        f"{ii.segmentHashAlg!r}"
    )
    assert_root_is_hs256(manifest, encrypt_sdk)

    legacy = tdfs.is_legacy_manifest(manifest)
    want = EXPECTED_HASH_BYTES[requested]
    assert ii.segments, "a manifest with no segments proves nothing"
    for i, segment in enumerate(ii.segments):
        got = len(tdfs.decode_integrity_value(segment.hash, legacy))
        assert got == want, (
            f"{encrypt_sdk} segment {i} hash decodes to {got} bytes; "
            f"{requested} implies {want}"
        )


# --- DSPX-4736: segment integrity algorithm ----------------------------------


@pytest.mark.parametrize("segment_alg", SEGMENT_ALGS)
def test_segment_integrity_roundtrip(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
    segment_alg: tdfs.integrity_algorithm,
) -> None:
    """Both segment algorithms round-trip across the encrypt x decrypt matrix."""
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    encrypt_sdk.skip_if_unsupported("integrity_algs")

    ct_file = encrypted_tdf(
        encrypt_sdk,
        segment_integrity_alg=segment_alg,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    assert_segment_integrity(ct_file, segment_alg, encrypt_sdk)

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file, shallow=False)


@pytest.mark.parametrize("segment_alg", SEGMENT_ALGS)
def test_chunky_segment_integrity_roundtrip(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    chunky_tdf: EncryptFactory,
    segment_alg: tdfs.integrity_algorithm,
) -> None:
    """The same, over a payload that spans several segments.

    A single-segment file exercises the aggregate hash trivially -- the
    aggregate *is* the one segment hash -- so the multi-segment case is where
    a per-segment algorithm change can actually go wrong.
    """
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    encrypt_sdk.skip_if_unsupported("integrity_algs")

    ct_file = chunky_tdf(
        encrypt_sdk,
        segment_integrity_alg=segment_alg,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    assert_segment_integrity(ct_file, segment_alg, encrypt_sdk)
    assert_multi_segment(ct_file, encrypt_sdk, chunky_pt_file)
    tdfs.skip_chunky_skew(ct_file, decrypt_sdk)

    rt_file = chunky_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(chunky_pt_file, rt_file, shallow=False)


def test_default_integrity_algs(
    encrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> None:
    """With no flags, every SDK emits an HS256 root and GMAC segments.

    Ungated: this is what all three SDKs hardcode today, and all 8 golden TDFs
    in ``golden/`` carry it. Writing it down turns an undocumented assumption
    into a tripwire -- if adding the flags changes a default, this fails
    instead of quietly shifting what every other test measures.
    """
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")

    ct_file = encrypted_tdf(encrypt_sdk, attr_values=attribute_default_rsa.value_fqns)
    manifest = tdfs.manifest(ct_file)
    ii = manifest.encryptionInformation.integrityInformation

    assert_root_is_hs256(manifest, encrypt_sdk)
    assert ii.segmentHashAlg.upper() == "GMAC", (
        f"{encrypt_sdk} default segmentHashAlg is {ii.segmentHashAlg!r}, not GMAC"
    )


@pytest.mark.parametrize("segment_alg", SEGMENT_ALGS)
def test_segment_integrity_detects_payload_tamper(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
    segment_alg: tdfs.integrity_algorithm,
) -> None:
    """A flipped payload byte is caught under either segment algorithm."""
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    encrypt_sdk.skip_if_unsupported("integrity_algs")

    ct_file = encrypted_tdf(
        encrypt_sdk,
        segment_integrity_alg=segment_alg,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    b_file = tdfs.update_payload(
        f"altered_payload_{segment_alg}", ct_file, change_payload_end
    )
    rt_file = encrypted_tdf.rt_file(b_file, decrypt_sdk)
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        f"payload tampering went undetected with segmentHashAlg={segment_alg}",
    )


def test_encrypt_accepts_hs256_root(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    encrypted_tdf: EncryptFactory,
) -> None:
    """``--root-integrity-algorithm hs256`` is accepted and is a no-op change."""
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    encrypt_sdk.skip_if_unsupported("gmac_root_option")

    ct_file = encrypted_tdf(
        encrypt_sdk,
        root_integrity_alg="hs256",
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    assert_root_is_hs256(tdfs.manifest(ct_file), encrypt_sdk)

    rt_file = encrypted_tdf.rt_file(ct_file, decrypt_sdk)
    decrypt_sdk.decrypt(ct_file, rt_file, "ztdf")
    assert filecmp.cmp(pt_file, rt_file, shallow=False)


def test_encrypt_rejects_gmac_root(
    encrypt_sdk: tdfs.SDK,
    pt_file: Path,
    tmp_dir: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
) -> None:
    """``--root-integrity-algorithm gmac`` is refused at config validation.

    Not routed through :class:`EncryptFactory`: the factory memoizes successes
    and asserts the output exists, and this call is required to produce
    neither.
    """
    if not in_focus & {encrypt_sdk}:
        pytest.skip("Not in focus")
    encrypt_sdk.skip_if_unsupported("gmac_root_option")

    ct_file = tmp_dir / f"gmac-root-refused-{encrypt_sdk}.tdf"
    try:
        encrypt_sdk.encrypt(
            pt_file,
            ct_file,
            root_integrity_alg="gmac",
            attr_values=attribute_default_rsa.value_fqns,
        )
    except subprocess.CalledProcessError as exc:
        combined = ((exc.stderr or b"") + (exc.output or b"")).lower()
        assert b"unsupported root integrity algorithm" in combined, (
            f"{encrypt_sdk} refused a GMAC root but not with the agreed "
            f"message: [{combined!r}]"
        )
        return
    raise AssertionError(
        f"{encrypt_sdk} wrote a TDF with --root-integrity-algorithm gmac; a "
        "GMAC root is forgeable without any key (DSPX-4703)"
    )


# --- DSPX-4703: the GMAC root downgrade --------------------------------------


def assert_multi_segment(
    ct_file: Path, encrypt_sdk: tdfs.SDK, pt_file: Path
) -> tdfs.Manifest:
    """Require more than one segment, and return the manifest.

    An assertion and not a skip. Truncating or reordering a one-segment file
    is a no-op, so a single segment would let every exploit case below pass
    without exercising anything -- the vacuous green this whole module exists
    to rule out.
    """
    manifest = tdfs.manifest(ct_file)
    ii = manifest.encryptionInformation.integrityInformation
    assert len(ii.segments) > 1, (
        f"{encrypt_sdk} wrote {len(ii.segments)} segment(s) from a "
        f"{pt_file.stat().st_size}-byte payload "
        f"(segmentSizeDefault={ii.segmentSizeDefault}); sizes.CHUNKY_BYTES is "
        "no longer larger than this SDK's default segment"
    )
    return manifest


@pytest.fixture
def multi_segment_ct(
    encrypt_sdk: tdfs.SDK,
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    in_focus: set[tdfs.SDK],
    attribute_default_rsa: Attribute,
    chunky_tdf: EncryptFactory,
) -> Path:
    """An ordinary, untampered multi-segment TDF for the surgery below.

    Written with default options -- an HS256 root and GMAC segments -- because
    the finding is that a *normal* file can be downgraded, not that an opted-in
    GMAC root is weak. No SDK feature gate here: producing this file needs
    nothing new, and the attack itself needs no key at all.
    """
    skip_unless_in_play(encrypt_sdk, decrypt_sdk, in_focus)
    ct_file = chunky_tdf(
        encrypt_sdk,
        target_mode=tdfs.select_target_version(encrypt_sdk, decrypt_sdk),
        attr_values=attribute_default_rsa.value_fqns,
    )
    assert_multi_segment(ct_file, encrypt_sdk, chunky_pt_file)
    tdfs.skip_chunky_skew(ct_file, decrypt_sdk)
    return ct_file


def apply_reorder(scenario: str, ct_file: Path, *changes: ManifestChange) -> Path:
    """Reverse both the segment list and the ciphertext it describes.

    Two passes because ``update_manifest`` and ``update_payload`` each rewrite
    one zip entry; the sizes are read from the original manifest before either
    runs.
    """
    sizes = tdfs.encrypted_segment_sizes(tdfs.manifest(ct_file))
    moved = tdfs.update_payload(
        f"{scenario}_payload", ct_file, reverse_payload_segments(sizes)
    )
    return tdfs.update_manifest(
        f"{scenario}_manifest", moved, compose(reverse_segments, *changes)
    )


def apply_duplicate(
    scenario: str, ct_file: Path, index: int, *changes: ManifestChange
) -> Path:
    """Duplicate both the segment list entry and the ciphertext at ``index``.

    Same two-pass shape as :func:`apply_reorder`: sizes come from the
    original manifest before either the payload or the manifest is rewritten.
    """
    sizes = tdfs.encrypted_segment_sizes(tdfs.manifest(ct_file))
    moved = tdfs.update_payload(
        f"{scenario}_payload", ct_file, duplicate_payload_segment(sizes, index)
    )
    return tdfs.update_manifest(
        f"{scenario}_manifest", moved, compose(duplicate_segment(index), *changes)
    )


#: Whether a reader refuses a forged GMAC root, probed once and cached for the
#: session. Keyed on the decrypting SDK alone: this is a property of the
#: reader, and who wrote the file does not change the answer.
_reader_rejects_gmac_root: dict[tdfs.SDK, bool] = {}


def skip_unless_gmac_root_rejected(
    decrypt_sdk: tdfs.SDK, chunky_tdf: EncryptFactory, multi_segment_ct: Path
) -> None:
    """Skip unless this reader is observed to refuse a forged GMAC root.

    Observed, because there is nothing to ask. The DSPX-4703 fix is entirely
    reader-side: it lives in the root-signature validation, which needs the
    unwrapped payload key and therefore runs after the KAS rewrap, and it adds
    no flag, subcommand or version field a ``cli.sh supports`` probe could
    reach.

    ``gmac_root_option`` is not a stand-in for it. Both writer behaviours --
    the ``--root-integrity-algorithm`` flag and its config-time refusal of
    ``gmac`` -- arrive with DSPX-4736, one commit *below* the reader fix in
    every SDK, so 4736 must land first. A release carrying 4736 without 4703
    would advertise a reader fix it does not have and turn every exploit case
    below red against a build nobody claimed was fixed. The mirror image is a
    reader fixed without the writer flag, which would skip silently.

    So forge one root and see what happens. One extra encrypt/decrypt per
    reader per session, no version numbers to keep up to date, and the answer
    stays right through every release ordering.

    The cost is that :func:`test_gmac_root_forged_signature_rejected` now
    restates the probe and can only pass or skip. The other five exploit cases
    keep their teeth: a reader can reject the bare downgrade and still be
    fooled by a truncation, a reorder, a replay, or a casing variant.

    The second cost is that a vulnerable build skips instead of going red,
    which is the wrong answer when the vulnerability is what you are trying to
    demonstrate. ``XT_FORCE_SUPPORTS=gmac_root_rejected`` is the escape hatch:
    every shim answers no to that feature, so it is only ever true when
    forced, and forcing it runs all six cases unconditionally.
    """
    if decrypt_sdk.supports("gmac_root_rejected"):
        return

    known = _reader_rejects_gmac_root.get(decrypt_sdk)
    if known is None:
        b_file = tdfs.update_manifest("gmac_root_probe", multi_segment_ct, forge_root())
        rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant="probe")
        # Deliberately uncached on an environment failure: decrypt_failure
        # raises there, so a flaky KAS cannot pin this reader as vulnerable
        # for the rest of the session.
        known = decrypt_failure(decrypt_sdk, b_file, rt_file) is not None
        _reader_rejects_gmac_root[decrypt_sdk] = known
    if not known:
        pytest.skip(
            f"{decrypt_sdk} accepts a keyless forged GMAC root signature, so "
            "it does not carry the DSPX-4703 reader fix"
        )


## CONTROLS -- ungated; these must pass today and after the fix


def test_root_signature_control_untouched_roundtrips(
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
) -> None:
    """The positive control: the unmodified file decrypts to the original.

    Establishes that the surgery below is the only reason anything fails.
    """
    rt_file = chunky_tdf.rt_file(multi_segment_ct, decrypt_sdk, variant="untouched")
    decrypt_sdk.decrypt(multi_segment_ct, rt_file, "ztdf")
    assert filecmp.cmp(chunky_pt_file, rt_file, shallow=False)


def test_root_signature_control_rewrite_roundtrips(
    decrypt_sdk: tdfs.SDK,
    chunky_pt_file: Path,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
) -> None:
    """The second positive control: an unzip/rezip with no edit still decrypts.

    Every tamper case reaches the reader through :func:`tdfs.update_payload`
    and :func:`tdfs.update_manifest`, which extract, re-serialize and re-zip.
    That round-trip is lossy-prone -- :class:`tdfs.Manifest` silently drops
    fields it does not model and re-emits defaults the original may have
    omitted -- so a rewrite that mangled the container would satisfy every
    "must fail" assertion below for entirely the wrong reason.

    Today the exploit cases happen to disprove that on their own: an unfixed
    reader accepts the rewritten files and returns the plaintext. That
    evidence disappears the moment every SDK rejects them, which is the whole
    point of the fix, and then this control is the only thing left pinning
    that the rewrite is faithful. Hence both passes, in the same order
    :func:`apply_reorder` and :func:`apply_duplicate` use.
    """
    moved = tdfs.update_payload("identity_payload", multi_segment_ct, lambda p: p)
    rewritten = tdfs.update_manifest("identity_manifest", moved, lambda m: m)
    rt_file = chunky_tdf.rt_file(rewritten, decrypt_sdk, variant="identity")
    decrypt_sdk.decrypt(rewritten, rt_file, "ztdf")
    assert filecmp.cmp(chunky_pt_file, rt_file, shallow=False)


@pytest.mark.parametrize("scenario", ["truncate", "reverse", "duplicate", "alg_only"])
def test_root_signature_control_tamper_without_forgery(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
    scenario: str,
) -> None:
    """Negative controls: neither half of the attack suffices on its own.

    ``truncate``, ``reverse``, and ``duplicate`` edit the segment list but
    leave the honest HS256 signature, so the root check catches them.
    ``alg_only`` performs the downgrade but keeps the HS256 signature, which
    the GMAC branch will not reproduce. Only the combination -- and it needs
    no key -- gets through.
    """
    manifest = tdfs.manifest(multi_segment_ct)
    n = len(manifest.encryptionInformation.integrityInformation.segments)

    match scenario:
        case "truncate":
            b_file = tdfs.update_manifest(
                "control_truncate", multi_segment_ct, keep_segments(n - 1)
            )
        case "reverse":
            b_file = apply_reorder("control_reverse", multi_segment_ct)
        case "duplicate":
            b_file = apply_duplicate("control_duplicate", multi_segment_ct, 0)
        case "alg_only":
            b_file = tdfs.update_manifest(
                "control_alg_only", multi_segment_ct, declare_root_alg("GMAC")
            )
        case _:
            raise AssertionError(f"unknown control scenario {scenario!r}")

    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant=scenario)
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        f"{scenario} without a forged root signature must not validate",
    )


## EXPLOITS -- gated on the reader actually rejecting a forged GMAC root


def test_gmac_root_forged_signature_rejected(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
) -> None:
    """The downgrade alone, with nothing else touched, must be refused.

    The narrowest case: only ``alg`` and ``sig`` change, and both new values
    are derived from data already in the manifest. If this is accepted then
    the root signature is a self-consistency check rather than an integrity
    check, whether or not anything else is tampered with.
    """
    skip_unless_gmac_root_rejected(decrypt_sdk, chunky_tdf, multi_segment_ct)
    b_file = tdfs.update_manifest("gmac_root", multi_segment_ct, forge_root())
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant="gmac_root")
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        "a GMAC root signature is computable without the key and must be rejected",
    )


def test_gmac_root_forged_truncation_rejected(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
) -> None:
    """Downgrade plus forged signature plus dropped trailing segments.

    The consequence the finding is about: the recipient decrypts successfully
    and receives an attacker-chosen prefix of the plaintext.
    """
    skip_unless_gmac_root_rejected(decrypt_sdk, chunky_tdf, multi_segment_ct)
    manifest = tdfs.manifest(multi_segment_ct)
    n = len(manifest.encryptionInformation.integrityInformation.segments)

    b_file = tdfs.update_manifest(
        "gmac_truncate",
        multi_segment_ct,
        compose(keep_segments(n - 1), forge_root()),
    )
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant="gmac_truncate")
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        f"keyless truncation from {n} to {n - 1} segments passed every check",
    )


def test_gmac_root_forged_reorder_rejected(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
) -> None:
    """Downgrade plus forged signature plus reversed segments.

    Reordering moves ciphertext as well as manifest entries, but the bytes are
    never rewritten, so every segment still carries the GCM tag it was born
    with. Per-segment authentication cannot see a permutation; only the root
    signature can.
    """
    skip_unless_gmac_root_rejected(decrypt_sdk, chunky_tdf, multi_segment_ct)
    b_file = apply_reorder("gmac_reorder", multi_segment_ct, forge_root())
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant="gmac_reorder")
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        "keyless segment reordering passed every check",
    )


def test_gmac_root_forged_duplicate_rejected(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
) -> None:
    """Downgrade plus forged signature plus a replayed segment.

    A third shape for the same finding: repeating a segment is neither a drop
    nor a permutation, so it is worth pinning separately from truncation and
    reorder. The duplicate carries the GCM tag it was issued with, so the
    per-segment check has nothing to object to; only the root signature
    covers how many times a segment may appear.
    """
    skip_unless_gmac_root_rejected(decrypt_sdk, chunky_tdf, multi_segment_ct)
    b_file = apply_duplicate("gmac_duplicate", multi_segment_ct, 0, forge_root())
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant="gmac_duplicate")
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        "keyless segment duplication passed every check",
    )


@pytest.mark.parametrize("alg", ["gmac", "GMac"])
def test_gmac_root_casing_variants_rejected(
    decrypt_sdk: tdfs.SDK,
    chunky_tdf: EncryptFactory,
    multi_segment_ct: Path,
    alg: str,
) -> None:
    """The rejection is case-insensitive.

    go and java already compare the algorithm with ``EqualFold`` /
    ``compareToIgnoreCase``, so a case-sensitive rejection would leave
    ``"gmac"`` on the vulnerable branch while looking fixed.
    """
    skip_unless_gmac_root_rejected(decrypt_sdk, chunky_tdf, multi_segment_ct)
    b_file = tdfs.update_manifest(f"gmac_root_{alg}", multi_segment_ct, forge_root(alg))
    rt_file = chunky_tdf.rt_file(b_file, decrypt_sdk, variant=f"gmac_{alg}")
    assert_decrypt_fails(
        decrypt_sdk,
        b_file,
        rt_file,
        f"rootSignature.alg={alg!r} must be rejected in every casing",
    )
