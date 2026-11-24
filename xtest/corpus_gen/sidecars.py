"""Validator sidecars for the generated fixtures, the synthetic-* copies, and install.

`sidecars` keeps the validator fields and [sdk] table of each fixture's previous
sidecar (from --from, by default xtest/corpus), rebuilds its key references from
the staged key files and writes fresh comments. `install` copies the stage into
xtest/corpus once every fixture there is complete and current. Offline.
"""

import glob
import json
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import corpus
import corpus_kas
from corpus_gen import runtime, tamper, variants, zipcases
from corpus_gen.variants import Keys

SUFFIX = corpus.SIDECAR_SUFFIX
GENERATED = tuple(p for p in corpus.PREFIXES if p != "golden-")
FORGED = "tamper-assertion-x5c-forged"

_SYNTHETIC = (
    "archive-comment.tdf",
    "augmented-extensions.tdf",
    "ec-wrapped.tdf",
    "encrypted-metadata-malformed.tdf",
    "encrypted-metadata-tampered.tdf",
    "gmac-root-downgrade.tdf",
    "kas-url-invalid.tdf",
    "legacy-string-policybinding.tdf",
    "missing-payload.tdf",
    "no-keyaccess.tdf",
    "no-manifest.tdf",
    "no-method.tdf",
    "no-mimetype.tdf",
    "not-a-tdf.bin",
    "remote-no-wrappedkey.tdf",
    "schemaversion-toplevel.tdf",
    "strict-warning.tdf",
    "trailing-data.tdf",
    "valid-tdf.tdf",
)
# Hand-built fixtures, copied byte for byte under their corpus names.
RENAMES: dict[str, str] = {n: f"synthetic-{n}" for n in _SYNTHETIC}
_EARLIER_NAME = {new: old for old, new in RENAMES.items()}

HEAD_FIELDS = ("expect", "format", "strict", "verify_crypto")
KEY_FIELDS = ("key", "share_keys", "assertion_keys")
TAIL_FIELDS = ("must_contain", "must_not_contain", "note")

_X = tamper.CIPHERTEXT_BYTE
# Each fixture's edit, as its sidecar comment states it. Prefixed "Edit: ".
TAMPER_CHANGES: dict[str, str] = {
    "tamper-assertion-binding-dropped": (
        "assertions[0] keeps its statement but has no binding member any more."
    ),
    "tamper-assertion-hs256-statement": (
        '"plan9" replaces the writing host\'s OS as operating_system inside the'
        " system-metadata statement value."
    ),
    "tamper-assertion-rs256-statement": (
        '"none" replaces "corpus" as the caveat inside the handling statement'
        " value; this copy's validator entry names no signer key."
    ),
    "tamper-assertion-rs256-statement-keyed": (
        "as for tamper-assertion-rs256-statement (this file repeats its bytes"
        " exactly), but the validator entry here adds the RS256 verification key."
    ),
    FORGED: (
        '"forged" replaces "x5c" as the caveat inside the handling statement'
        " value; the JWS then had its assertionHash and assertionSig worked out"
        " again from the edited manifest, and was signed RS256 by a separate"
        " certificate, self-signed and outside the test chain, that carries the"
        " genuine leaf's subject and is the lone x5c entry."
    ),
    "tamper-binding-hex-bitflip": (
        "policyBinding.hash keeps the SDK's base64-of-hex encoding, but the HMAC"
        " it encodes has its first byte's low bit toggled."
    ),
    "tamper-binding-hexless-bitflip": (
        "policyBinding.hash now encodes the raw HMAC bytes in base64, with no hex"
        " layer, and the first byte's low bit is toggled."
    ),
    "tamper-binding-hexless-control": (
        "policyBinding.hash now encodes the raw HMAC bytes in base64, with no hex"
        " layer; the HMAC value itself is still right."
    ),
    "tamper-ciphertext-body": (
        f"payload byte {_X}, which lies in the first segment's ciphertext between"
        " its IV and its GCM tag, has its low bit toggled."
    ),
    "tamper-deflate": (
        "manifest and payload bytes are untouched; the archive now holds both"
        " entries DEFLATE-compressed."
    ),
    "tamper-duplicate-kao": "keyAccess lists its single object twice in a row.",
    "tamper-encrypted-segment-size": (
        "segments[0].encryptedSegmentSize is one smaller than the writer's value."
    ),
    "tamper-gmac-root-lower": (
        'rootSignature claims alg "gmac" now; anyone holding the manifest could'
        " compute its sig, which is just the last 16 bytes of all segment hashes"
        " joined."
    ),
    "tamper-gmac-root-mixed": (
        'rootSignature claims alg "GMac" now; anyone holding the manifest could'
        " compute its sig, which is just the last 16 bytes of all segment hashes"
        " joined."
    ),
    "tamper-gmac-root-upper": (
        'rootSignature claims alg "GMAC" now; anyone holding the manifest could'
        " compute its sig, which is just the last 16 bytes of all segment hashes"
        " joined."
    ),
    "tamper-identity-go-assertion-hs256": "nothing; this copy is a control.",
    "tamper-identity-go-assertion-rs256": "nothing; this copy is a control.",
    "tamper-identity-go-basic": "nothing; this copy is a control.",
    "tamper-identity-web-multi-segment": "nothing; this copy is a control.",
    "tamper-kas-url-malicious": (
        f"{tamper.ATTACKER_KAS}, a hostile address, now stands in the KAO's url."
    ),
    "tamper-multi-segment-duplicate": (
        "segment 0 now occurs twice at the start, in the manifest's list as in"
        " the payload's ciphertext chunks."
    ),
    "tamper-multi-segment-reverse": (
        "both the manifest's list and the payload's ciphertext chunks now run"
        " from last segment to first."
    ),
    "tamper-multi-segment-truncate": (
        "the manifest's list omits the final segment, whose ciphertext the"
        " payload still contains."
    ),
    "tamper-payload-in-place": (
        f"payload byte {_X} has its low bit toggled where it sits in the base"
        " archive, which is not repacked, so the entry's recorded CRC-32 no longer"
        " fits."
    ),
    "tamper-payload-tag": (
        "the payload's final 3 bytes, which end the last segment's GCM tag, are"
        " XORed with 0xFF."
    ),
    "tamper-policy-body": (
        "the decoded policy's dissem, null in the base, now lists"
        ' "mallory@example.com"; policyBinding is left as the SDK wrote it.'
    ),
    "tamper-root-signature": (
        "rootSignature.sig, an HS256 value, has its final 3 bytes XORed with 0xFF."
    ),
    "tamper-root-signature-keyless": (
        "as for tamper-root-signature (this file repeats its bytes exactly), but"
        " the validator entry here gives no DEK."
    ),
    "tamper-segment-hash": "segments[0].hash has its first byte's low bit toggled.",
}

# Each fixture's trailer, as its sidecar comment states it.
ZIP_CHANGES: dict[str, str] = {
    "zip-adversarial-directory-offset-past-eof": (
        "a ZIP64 end record places the central directory at the file's size plus"
        " 4096 bytes."
    ),
    "zip-adversarial-entry-count-overstated": (
        "the end record claims n+1 entries for a directory of n records."
    ),
    "zip-adversarial-extra-length-overrun": (
        "in the manifest's directory record, a ZIP64 extra with a length field"
        " of 0xFFFF carries only 8 bytes."
    ),
    "zip-adversarial-header-offset-int64": (
        "through a ZIP64 extra, the manifest's directory record points at a"
        " local header 2^63 bytes in."
    ),
    "zip-adversarial-impossible-entry-count": (
        "a ZIP64 end record with an entry count of 2^64-1."
    ),
    "zip-adversarial-manifest-size-past-eof": (
        "a ZIP64 extra sets the manifest record's compressed size to the file's"
        " size plus 4096 bytes."
    ),
    "zip-adversarial-payload-overlaps-directory": (
        "the payload's directory record inflates both sizes, so that, taken at"
        " face value, its data would end on the central directory's first byte."
    ),
    zipcases.FAKE_COMMENT: (
        "what looks like a second manifest directory entry, pointing 2^63 bytes"
        " in through ZIP64, sits inside the end record's comment."
    ),
    "zip-legal-entry-comment": (
        "the payload's directory record has a short text in its file comment field."
    ),
    "zip-legal-trailer-rebuilt": (
        "nothing altered; the trailer is just re-serialized from what was parsed,"
        " as a control."
    ),
    "zip-legal-zip64-entry-sentinels": (
        "each directory record now stores its sizes and local header offset in a"
        " ZIP64 extra, preceded by an extended-timestamp extra, and the archive"
        " gains a ZIP64 end record."
    ),
    "zip-legal-zip64-eocd-count-sentinel": (
        "alongside a new ZIP64 end record and locator, the classic end record's"
        " entry count becomes 0xFFFF while its other fields stay real."
    ),
    "zip-legal-zip64-extra-not-first": (
        "two extras follow the manifest's directory record, extended-timestamp"
        " then ZIP64, and the ZIP64 one now holds the local header offset."
    ),
}

_STUB = "Built by hand around a stub KAO (url https://kas.example.com, wrappedKey QQ==)"
_GO_METADATA = (
    "Made from a metadata-mimetype TDF that the Go SDK v0.34.0 wrote, whose KAO no"
    " key in kas-keys.json unwraps"
)
SYNTHETIC_TEXT: dict[str, str] = {
    "synthetic-archive-comment.tdf": (
        "Same as synthetic-valid-tdf.tdf except that its end record now declares"
        " 35 bytes of comment text, the last bytes in the file."
    ),
    "synthetic-augmented-extensions.tdf": (
        f"{_STUB}. Otherwise valid, it adds fields that no spec defines:"
        " keyAccess[0].vendorExtension, payload.x-vendor and a top-level"
        " x-company-profile."
    ),
    "synthetic-ec-wrapped.tdf": (
        f"{_STUB}, typed ec-wrapped and holding an ephemeralPublicKey."
    ),
    "synthetic-encrypted-metadata-malformed.tdf": (
        f"{_GO_METADATA}; its encryptedMetadata was overwritten with the base64"
        ' form of "not json".'
    ),
    "synthetic-encrypted-metadata-tampered.tdf": (
        f"{_GO_METADATA}; one ciphertext byte inside its encryptedMetadata was"
        " flipped. Its DEK file is the original TDF's."
    ),
    "synthetic-gmac-root-downgrade.tdf": (
        "A reworked synthetic-valid-tdf.tdf: its payload is now two 44-byte"
        " segments, each hashed as its own GCM tag; rootSignature switches from"
        " HS256 to GMAC with the last segment's hash as its sig, which needs no"
        " key; and schemaVersion appears at the top level. This is the keyless"
        " root forgery of DSPX-4703, which test_root_signature.py also covers."
    ),
    "synthetic-kas-url-invalid.tdf": (
        "Built by hand; everything else is well formed, but keyAccess[0].url is"
        " ftp://nope."
    ),
    "synthetic-legacy-string-policybinding.tdf": (
        f"{_STUB}. Its policyBinding is a plain base64 string, where an object"
        " holding alg and hash is expected."
    ),
    "synthetic-missing-payload.tdf": (
        "A hand-made ZIP whose sole entry is 0.manifest.json, a short manifest"
        " lacking integrityInformation; 0.payload is absent."
    ),
    "synthetic-no-keyaccess.tdf": (
        "Built by hand; encryptionInformation has no keyAccess member, so the file"
        " names no KAS and holds no wrapped key."
    ),
    "synthetic-no-manifest.tdf": (
        "A hand-made ZIP whose only entry is 0.payload; 0.manifest.json is missing."
    ),
    "synthetic-no-method.tdf": (
        f"{_STUB}; the method member is missing from its encryptionInformation."
    ),
    "synthetic-no-mimetype.tdf": f"{_STUB}; its payload object omits mimeType.",
    "synthetic-not-a-tdf.bin": (
        "One 48-byte line of ASCII prose, in neither ZIP nor any other TDF format."
    ),
    "synthetic-remote-no-wrappedkey.tdf": (
        "Built by hand; its one KAO is typed remote, points at"
        " https://kas.example.com and keeps a policyBinding, but has no wrappedKey."
    ),
    "synthetic-schemaversion-toplevel.tdf": (
        f"{_STUB}. A top-level schemaVersion of 4.3.0 is its only spec version;"
        " tdf_spec_version is absent."
    ),
    "synthetic-strict-warning.tdf": (
        f"{_STUB}. No tdf_spec_version is given anywhere; no other required part"
        " is missing."
    ),
    "synthetic-trailing-data.tdf": (
        "Same as synthetic-valid-tdf.tdf apart from 34 bytes of junk following"
        " its final end record."
    ),
    "synthetic-valid-tdf.tdf": (
        f"{_STUB}. Nothing the spec requires is missing: it has a policy, that"
        " KAO, a method block and integrityInformation."
    ),
}

# Notes replaced outright rather than carried.
NOTES: dict[str, str] = {
    "tamper-assertion-rs256-statement": (
        "RS256 assertion statement tampered, no signer key supplied: the signature"
        " is unverifiable, so only a warning."
    ),
    "zip-legal-zip64-extra-not-first": (
        "Spec-legal ZIP trailer: the manifest's offset deferred to a ZIP64 extra"
        " placed after a foreign extended-timestamp extra (version 4.5)."
    ),
}

# Earlier KAS details in carried notes, and what replaced them.
_HOSTS = {"localhost:8080": "localhost:8585", "localhost:8282": "localhost:8686"}
_KIDS = {
    "r1": "corpus-r2048",
    "b1": "corpus-r2048-b",
    "x1": "corpus-xwing",
    "h1": "corpus-p256mlkem768",
    "h2": "corpus-p384mlkem1024",
    "m1": "corpus-mlkem768",
    "m2": "corpus-mlkem1024",
}
_KID = re.compile(r"\bkey ([a-z]\d)\b")
_HOST = re.compile(r"localhost:\d+")
_TICKET = re.compile(r"\bDSPX-\d+\b")
_PUBLIC_TICKETS = {"DSPX-4703", "DSPX-5744"}
_V = r"v?\d+\.\d+\.\d+"
_WRITER = re.compile(rf"^(?:Go|Java|Web) SDK (?:{_V}|main \([0-9a-f]+, after {_V}\)): ")
_OLD_NAME = re.compile(
    r"(?<![\w-])(" + "|".join(map(re.escape, RENAMES)) + r")(?![\w-])"
)

LABELS = {"go": "Go SDK", "java": "Java SDK", "js": "Web SDK"}
_TAG_PREFIX = {"java": "v", "js": "sdk-v"}


class SidecarGenError(Exception):
    pass


@dataclass(frozen=True)
class KeyRefs:
    """Key references as a sidecar writes them, relative to the corpus."""

    key: str | None = None
    share_keys: tuple[str, ...] = ()
    assertion_keys: tuple[str, ...] = ()


def staged_refs(keys_dir: Path, stem: str) -> KeyRefs:
    """The DEK, shares and assertion public keys staged as keys/<stem>.*."""
    for suffix in ("dek", "x.share", "pub.pem"):
        runtime.inside(keys_dir, f"{stem}.{suffix}", "key stem")
    pattern = glob.escape(stem)
    dek = keys_dir / f"{stem}.dek"
    shares = sorted(keys_dir.glob(f"{pattern}.*.share"))
    pems = sorted(keys_dir.glob(f"{pattern}.*pub.pem"))
    return KeyRefs(
        key=f"keys/{dek.name}" if dek.is_file() else None,
        share_keys=tuple(
            f"{p.name[len(stem) + 1 : -len('.share')]}=keys/{p.name}" for p in shares
        ),
        assertion_keys=tuple(f"keys/{p.name}" for p in pems),
    )


def check_public(text: str) -> None:
    """Refuse ticket ids and local hosts that do not belong in the public corpus."""
    bad = [t for t in _TICKET.findall(text) if t not in _PUBLIC_TICKETS]
    bad += [h for h in _HOST.findall(text) if h not in _HOSTS.values()]
    if bad:
        raise SidecarGenError(f"{sorted(set(bad))} do not belong in the corpus")


def rewrite_note(note: str, writer: str | None = None) -> str:
    """A carried note with earlier hosts, kids and names replaced and, given the
    fixture's writer, its leading writer version too."""
    if writer:
        note = _WRITER.sub(lambda _m: f"{writer}: ", note, count=1)
    for old, new in _HOSTS.items():
        note = note.replace(old, new)

    def kid(m: re.Match[str]) -> str:
        if m.group(1) not in _KIDS:
            raise SidecarGenError(f"note names an unknown KAS key: {note!r}")
        return f"key {_KIDS[m.group(1)]}"

    note = _KID.sub(kid, note)
    note = _OLD_NAME.sub(lambda m: RENAMES[m.group(1)], note)
    check_public(note)
    return note


def comment_lines(comments: Sequence[str]) -> str:
    lines: list[str] = []
    for c in comments:
        lines += textwrap.wrap(
            c,
            98,
            initial_indent="# ",
            subsequent_indent="# ",
            break_long_words=False,
            break_on_hyphens=False,
        )
    return "".join(f"{line}\n" for line in lines)


def render(comments: Sequence[str], fields: dict[str, Any]) -> str:
    # A dev dependency, imported here so collecting the tests does not need it.
    import tomli_w

    text = comment_lines(comments) + tomli_w.dumps(fields)
    check_public(text)
    return text


_SDK_HEADER = re.compile(r"^\[sdk\][ \t]*$", re.M)


def split_sdk_table(text: str) -> tuple[str, str]:
    """Sidecar text before its [sdk] table, less the blank line that separates
    them, and the table through to the end ("" when there is none)."""
    m = _SDK_HEADER.search(text)
    if m is None:
        return text, ""
    head = text[: m.start()]
    return (head[:-1] if head.endswith("\n\n") else head), text[m.start() :]


def with_sdk_table(text: str, table: str) -> str:
    """``text`` with ``table`` appended after a blank line."""
    if not table:
        return text
    check_public(table)
    return f"{text}\n{table}"


def kept_sdk_table(src: Path) -> str:
    return split_sdk_table(src.read_text())[1]


def _load(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _key_fields(src: Path, old: dict[str, Any], refs: KeyRefs) -> dict[str, Any]:
    """Key fields the old sidecar had, rebuilt from ``refs``, plus the shares a
    keyed check needs."""

    def need(what: str, value: object) -> None:
        if not value:
            raise SidecarGenError(f"{src.name} has {what}, but none is staged")

    out: dict[str, Any] = {}
    if "key" in old:
        need("key", refs.key)
        out["key"] = refs.key
    if "share_keys" in old or (refs.share_keys and "key" in old):
        need("share_keys", refs.share_keys)
        out["share_keys"] = list(refs.share_keys)
    if "assertion_keys" in old:
        need("assertion_keys", refs.assertion_keys)
        out["assertion_keys"] = list(refs.assertion_keys)
    return out


def carry_sidecar(
    src: Path,
    comments: Sequence[str],
    refs: KeyRefs,
    writer: str | None = None,
    note: str | None = None,
) -> str:
    """Sidecar text: ``comments``, then the validator fields of ``src`` with its
    note rewritten (or replaced by ``note``) and its key fields rebuilt, then
    its [sdk] table unchanged."""
    old = _load(src)
    unknown = set(old) - {*HEAD_FIELDS, *KEY_FIELDS, *TAIL_FIELDS, "sdk"}
    if unknown:
        raise SidecarGenError(f"{src.name}: unknown keys {sorted(unknown)}")
    fields = {k: old[k] for k in HEAD_FIELDS if k in old}
    fields |= _key_fields(src, old, refs)
    fields |= {k: old[k] for k in TAIL_FIELDS if k in old}
    if note is not None:
        fields["note"] = note
    elif "note" in fields:
        fields["note"] = rewrite_note(fields["note"], writer)
    return with_sdk_table(render(comments, fields), kept_sdk_table(src))


def forged_sidecar(comments: Sequence[str], refs: KeyRefs) -> str:
    if refs.key is None or not refs.assertion_keys:
        raise SidecarGenError(f"{FORGED}: base DEK or leaf public key not staged")
    return render(
        comments,
        {
            "expect": "invalid",
            "format": "tdf",
            "verify_crypto": True,
            "key": refs.key,
            "assertion_keys": list(refs.assertion_keys),
            "must_contain": ["TDF.CRYPTO.ASSERTION_SIGNATURE_INVALID"],
            "note": (
                "Forged x5c assertion (self-signed certificate, recomputed claims);"
                " invalid with the genuine signer key."
            ),
        },
    )


def provenance_from_describe(
    label: str, version: str, prefix: str, described: str
) -> str:
    """``label version`` on a release tag, else main at its commit."""
    tag, ahead, commit = described.strip().rsplit("-", 2)
    if tag.removeprefix(prefix) != version.removeprefix("v"):
        raise SidecarGenError(
            f"{label} reported {version}, but its checkout describes as {described}"
        )
    if ahead == "0":
        return f"{label} {version}"
    return f"{label} main ({commit.removeprefix('g')}, after {version})"


def provenance(sdk: str, version: str) -> str:
    """How comments name a writer. Go is a pinned module; Java and JS are
    source builds, so the checkout says whether they sit on a release."""
    label = LABELS[sdk]
    checkout = runtime.XTEST / "sdk" / sdk / "src" / "main"
    if sdk not in _TAG_PREFIX or not checkout.is_dir():
        return f"{label} {version}"
    prefix = _TAG_PREFIX[sdk]
    described = subprocess.run(
        ["git", "-C", str(checkout), "describe", "--tags", "--long"]
        + ["--match", f"{prefix}*"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return provenance_from_describe(label, version, prefix, described)


def _kaos(job: variants.WriteJob, keys: Keys) -> str:
    prefix = f"{corpus_kas.ATTR_BASE}/"
    kids = [
        corpus_kas.VALUE_KEYS[a.removeprefix(prefix)] for a in job.get("attributes", [])
    ] or [k["kid"] for k in job.get("kas", [])]
    parts = []
    for kid in dict.fromkeys(kids):
        n, k = kids.count(kid), keys[kid]
        times = f"{n} x " if n > 1 else ""
        parts.append(
            f"{times}{kid} ({k['alg']}) on {k['kas']}, {variants.KAS_URL[k['kas']]}"
        )
    return f"KAO{'s' if len(kids) > 1 else ''}: {'; '.join(parts)}."


def _facts(
    entry: dict[str, Any], stem: str, keys: Keys, refs: KeyRefs, scratch: Path
) -> list[str]:
    """What a writer job produced: KAOs, split ids, plaintext and assertions."""
    job: variants.WriteJob = entry["job"]
    out = []
    if attrs := job.get("attributes"):
        out.append(f"Attributes: {', '.join(attrs)}.")
    out.append(_kaos(job, keys))
    if refs.share_keys:
        sids = [s.partition("=")[0] for s in refs.share_keys]
        label = "Split ids" if len(sids) > 1 else "Split id"
        out.append(f"{label} {', '.join(sids)}; shares in keys/{stem}.<id>.share.")
    pt = runtime.inside(scratch / "plaintexts", entry["plaintext"], "plaintext")
    size = pt.stat().st_size
    seg = job.get("segment_size")
    if not size:
        out.append("Plaintext: empty.")
    else:
        out.append(
            f"Plaintext: {size} bytes" + (f" in {seg}-byte segments." if seg else ".")
        )
    if mode := job.get("target_mode"):
        out.append(f"Target spec version {mode}.")
    if mime := job.get("mime_type"):
        out.append(f"MIME type {mime}.")
    if job.get("encrypted_metadata"):
        out.append("Encrypted KAO metadata.")
    for a in job.get("assertions", []):
        if a["kind"] == "system-metadata":
            out.append(
                "Assertion system-metadata: the statement the SDK fills with its"
                " own system metadata, HS256-bound under the payload key."
            )
        elif a.get("x5c") is not None:
            out += [
                f"Assertion {a.get('id')}: handling, signed RS256 by a test leaf"
                " certificate under a throwaway test CA, with x5c = [leaf,"
                " intermediate].",
                f"To verify it, use the leaf's public key in keys/{stem}.leaf.pub.pem.",
            ]
        else:
            out += [
                f"Assertion {a.get('id')}: handling, signed RS256 by a generated key.",
                f"To verify it, use the signer's public key in keys/{stem}.pub.pem.",
            ]
    return out


@dataclass(frozen=True)
class _Context:
    scratch: Path
    src: Path
    manifest: dict[str, Any]
    keys: Keys
    writers: dict[tuple[str, str], str]

    def writer(self, entry: dict[str, Any]) -> str:
        return self.writers[(entry["sdk"], entry["version"])]

    @property
    def keys_dir(self) -> Path:
        return self.scratch / "stage" / "keys"


def _previous(src: Path, name: str, suffix: str = SUFFIX) -> Path:
    """``name`` (plus ``suffix``) in ``src``, under its corpus name or the name
    it had before RENAMES."""
    for n in (name, _EARLIER_NAME.get(name)):
        if n and (src / f"{n}{suffix}").is_file():
            return src / f"{n}{suffix}"
    raise SidecarGenError(f"no {name}{suffix} in {src}")


def _base_comments(ctx: _Context, base: str) -> list[str]:
    entry = ctx.manifest[tamper.base_path(ctx.scratch, base).name]
    writer = ctx.writer(entry)
    if base not in variants.TAMPER_BASES:
        return [f"Derived from {base}.tdf, which the {writer} wrote."]
    stem = tamper.key_stem(base)
    facts = _facts(entry, stem, ctx.keys, staged_refs(ctx.keys_dir, stem), ctx.scratch)
    return [
        f"Derived from the generator's {base} base, which the {writer} wrote.",
        *facts,
    ]


def sidecar_text(ctx: _Context, name: str) -> str:
    stem = name.removesuffix(".tdf")
    if name.startswith("sdk-"):
        entry = ctx.manifest[name]
        key_stem, writer = entry["key_stem"], ctx.writer(entry)
        refs = staged_refs(ctx.keys_dir, key_stem)
        comments = [
            f"Produced by the generator's writer job for the {writer}.",
            *_facts(entry, key_stem, ctx.keys, refs, ctx.scratch),
            "keys/ holds its DEK, recovered offline through kas-keys.json and"
            " confirmed against the known plaintext.",
        ]
        return carry_sidecar(_previous(ctx.src, name), comments, refs, writer)
    if name.startswith("tamper-"):
        recipe = tamper.RECIPES[stem]
        refs = staged_refs(ctx.keys_dir, tamper.key_stem(recipe.base))
        comments = [
            *_base_comments(ctx, recipe.base),
            f"Edit: {TAMPER_CHANGES[stem]}",
        ]
        if recipe.container == "stored":
            comments.append("Repacked as an uncompressed archive with fresh CRC-32s.")
        if stem == FORGED:
            try:
                table = kept_sdk_table(_previous(ctx.src, name))
            except SidecarGenError:
                table = ""
            return with_sdk_table(forged_sidecar(comments, refs), table)
        return carry_sidecar(
            _previous(ctx.src, name), comments, refs, note=NOTES.get(stem)
        )
    if name.startswith("zip-"):
        refs = staged_refs(ctx.keys_dir, tamper.key_stem(zipcases.BASE))
        kind = "Legal" if name.startswith("zip-legal-") else "Contradictory"
        comments = [
            *_base_comments(ctx, zipcases.BASE),
            "Everything before the central directory matches the base byte for"
            " byte; the directory and end records alone were written afresh.",
            f"{kind} trailer: {ZIP_CHANGES[stem]}",
        ]
        return carry_sidecar(
            _previous(ctx.src, name), comments, refs, note=NOTES.get(stem)
        )
    refs = staged_refs(ctx.keys_dir, name.rsplit(".", 1)[0])
    return carry_sidecar(_previous(ctx.src, name), [SYNTHETIC_TEXT[name]], refs)


def copy_synthetic(src: Path, stage: Path) -> None:
    """Copy each synthetic fixture, then its DEK if it had one, so the key is
    never older than the fixture."""
    for name in RENAMES.values():
        shutil.copyfile(_previous(src, name, ""), stage / name)
        old = _load(_previous(src, name))
        if "share_keys" in old or "assertion_keys" in old:
            raise SidecarGenError(f"{name}: only a DEK can be copied")
        if "key" in old:
            dest = stage / "keys" / f"{name.rsplit('.', 1)[0]}.dek"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / old["key"], dest)


def expected_fixtures(manifest: dict[str, Any]) -> list[str]:
    """Every fixture the generator installs."""
    return sorted(
        [
            *(n for n, e in manifest.items() if e["kind"] == "sdk"),
            *(f"{n}.tdf" for n in tamper.RECIPES),
            *(f"{n}.tdf" for n in zipcases.ZIP_CASES),
            *RENAMES.values(),
        ]
    )


def load_manifest(scratch: Path) -> dict[str, Any] | None:
    path = scratch / "manifest.json"
    if not path.is_file():
        print(f"no {path}; run `write` first", file=sys.stderr)
        return None
    return json.loads(path.read_text())


def clear_outputs(stage: Path) -> None:
    """Remove what `sidecars` writes: every sidecar and the synthetic copies."""
    old = {
        *stage.glob(f"*{SUFFIX}"),
        *stage.glob("synthetic-*"),
        *(stage / "keys").glob("synthetic-*"),
    }
    for p in old:
        p.unlink()


def run_sidecars(scratch: Path, src: Path) -> int:
    """Copy the synthetic fixtures into the stage and write every sidecar."""
    manifest = load_manifest(scratch)
    if manifest is None:
        return 2
    stage = scratch / "stage"
    names = expected_fixtures(manifest)
    missing = [
        n for n in names if not n.startswith("synthetic-") and not (stage / n).is_file()
    ]
    if missing:
        print(f"not staged {missing}; run write, deks and derive", file=sys.stderr)
        return 2
    clear_outputs(stage)
    try:
        copy_synthetic(src, stage)
    except (SidecarGenError, OSError, tomllib.TOMLDecodeError) as e:
        print(f"FAIL copying the synthetic fixtures: {e}", file=sys.stderr)
        return 1
    writers = {
        (e["sdk"], e["version"]): provenance(e["sdk"], e["version"])
        for e in manifest.values()
    }
    ctx = _Context(scratch, src, manifest, corpus.kas_keys(), writers)
    failed: list[str] = []
    for name in names:
        out = stage / f"{name}{SUFFIX}"
        try:
            out.write_text(sidecar_text(ctx, name))
            corpus.load_sidecar(out)
        except (SidecarGenError, corpus.SidecarError, KeyError, OSError) as e:
            out.unlink(missing_ok=True)
            failed.append(f"{name}: {e}")
    for f in failed:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"writers: {', '.join(sorted(writers.values()))}")
    print(f"{len(names) - len(failed)}/{len(names)} sidecars in {stage}")
    return 1 if failed else 0


class InstallRefused(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("install refused:\n" + "\n".join(f"  {p}" for p in problems))
        self.problems = problems


def key_refs(raw: dict[str, Any]) -> list[str]:
    """Key paths a sidecar references, relative to the corpus."""
    refs = [raw["key"]] if "key" in raw else []
    refs += [v.partition("=")[2] for v in raw.get("share_keys", [])]
    refs += [
        v.partition("=")[2] if "=" in v else v for v in raw.get("assertion_keys", [])
    ]
    return refs


def base_of(scratch: Path, name: str) -> Path | None:
    """The file a derived fixture was made from; its keys are the base's."""
    stem = name.removesuffix(".tdf")
    if stem in tamper.RECIPES:
        return tamper.base_path(scratch, tamper.RECIPES[stem].base)
    if stem in zipcases.ZIP_CASES:
        return tamper.base_path(scratch, zipcases.BASE)
    return None


def _mtime(path: Path) -> int:
    return path.stat().st_mtime_ns


def _fixture_problems(scratch: Path, name: str) -> list[str]:
    stage = scratch / "stage"
    fixture, sidecar = stage / name, stage / f"{name}{SUFFIX}"
    if not sidecar.is_file():
        return [f"{name}: no sidecar"]
    out = []
    if _mtime(sidecar) < _mtime(fixture):
        out.append(f"{name}: sidecar is older than the fixture")
    try:
        raw = corpus.load_sidecar(sidecar).raw
    except corpus.SidecarError as e:
        return [*out, f"{name}: {e}"]
    source = fixture
    base = base_of(scratch, name)
    if base is not None:
        if not base.is_file():
            return [*out, f"{name}: base {base.name} is missing"]
        if _mtime(fixture) < _mtime(base):
            out.append(f"{name}: older than its base {base.name}")
        source = base
    keys_dir = (stage / "keys").resolve()
    for ref in key_refs(raw):
        path = (stage / ref).resolve()
        if not path.is_relative_to(keys_dir):
            out.append(f"{name}: key reference {ref} is outside keys/")
        elif not path.is_file():
            out.append(f"{name}: missing key file {ref}")
        elif _mtime(path) < _mtime(source):
            out.append(f"{name}: {ref} is older than {source.name}")
    return out


def install_problems(scratch: Path, expected: Iterable[str]) -> list[str]:
    stage = scratch / "stage"
    want = set(expected)
    staged = {
        p.name
        for p in (stage.iterdir() if stage.is_dir() else [])
        if p.is_file() and not p.name.endswith(SUFFIX) and not p.name.startswith(".")
    }
    problems = [f"{n}: not staged" for n in sorted(want - staged)]
    problems += [f"{n}: staged but not expected" for n in sorted(staged - want)]
    for name in sorted(want & staged):
        problems += _fixture_problems(scratch, name)
    return problems


def install(scratch: Path, dest: Path, expected: Iterable[str]) -> list[str]:
    """Replace the generator's outputs in ``dest`` with the stage; refuse,
    changing nothing, unless every expected fixture is complete and current."""
    names = sorted(expected)
    problems = install_problems(scratch, names)
    if problems:
        raise InstallRefused(problems)
    stage = scratch / "stage"
    copies: dict[Path, Path] = {}
    for name in names:
        sidecar = stage / f"{name}{SUFFIX}"
        for rel in (name, sidecar.name, *key_refs(corpus.load_sidecar(sidecar).raw)):
            copies[dest / rel] = stage / rel
    for old in [*dest.iterdir(), *(dest / "keys").glob("*")]:
        if old.is_file() and old.name.startswith(GENERATED):
            old.unlink()
    (dest / "keys").mkdir(exist_ok=True)
    for to, frm in copies.items():
        shutil.copyfile(frm, to)
    return names


def run_install(scratch: Path, dest: Path) -> int:
    manifest = load_manifest(scratch)
    if manifest is None:
        return 2
    try:
        names = install(scratch, dest, expected_fixtures(manifest))
    except InstallRefused as e:
        print(e, file=sys.stderr)
        return 1
    counts = {p: sum(n.startswith(p) for n in names) for p in GENERATED}
    print(f"installed {len(names)} fixtures into {dest}: {counts}")
    return 0
