"""Per-SDK [sdk] tables from record-mode corpus runs. Offline.

`verdicts REC.jsonl...` reads the rows `test_corpus.py --corpus-record` wrote,
one file per platform, and appends an [sdk] table to every non-golden sidecar
in xtest/corpus, and to its staged copy if there is one, replacing any earlier
table. Where cells disagree in a way it cannot express, it keeps the earlier
entry if that gives every cell. It writes nothing if any cell is wrong, no
entry gives a disagreement, or a fixture has no cells at all.
"""

import json
import sys
import tempfile
import tomllib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import corpus
from corpus_gen import sidecars

Entry = dict[str, str]
SdkVerdict = str | list[Entry]

# Validator codes for a file with no manifest entry, or no TDF container at all.
_NO_MANIFEST = ("TDF.STRUCTURE.MISSING_MANIFEST", "CORE.DETECT.")
# Validator code for a manifest with no keyAccess.
_NO_KEY_ACCESS = "TDF.SEMANTIC.KEY_ACCESS_MISSING"
# Why a fixture might have no cells from any SDK.
_NO_CELLS = (
    "no SDK recorded a cell; check the dry run's platform and env"
    " (PLATFORM_VERSION, PLATFORM_TAG; see corpus/README.md)"
)


class VerdictError(Exception):
    pass


def _semver(v: list[int] | None) -> corpus.Semver | None:
    return (v[0], v[1], v[2]) if v else None


@dataclass(frozen=True)
class Cell:
    """One recorded decrypt: an SDK build on a platform."""

    sdk: str
    version: str
    sdk_semver: corpus.Semver | None
    platform: str
    platform_semver: corpus.Semver | None
    outcome: str
    output_sha256: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Cell:
        return cls(
            sdk=row["sdk"],
            version=row["version"],
            sdk_semver=_semver(row["sdk_semver"]),
            platform=str(row["platform_tag"]),
            platform_semver=_semver(row["platform_semver"]),
            outcome=row["outcome"],
            output_sha256=row["output_sha256"],
        )

    def __str__(self) -> str:
        return f"{self.sdk}@{self.version} on platform {self.platform}: {self.outcome}"


def _order(semver: corpus.Semver | None) -> tuple[bool, corpus.Semver]:
    """Branch builds first, then releases oldest to newest."""
    return (semver is not None, semver or (0, 0, 0))


def collapse(cells: Sequence[Cell]) -> SdkVerdict:
    """One SDK's verdict: bare when every cell agrees; a list bounded at the
    next minor release when only the branch builds differ from the releases."""
    if len({c.outcome for c in cells}) == 1:
        return cells[0].outcome
    branch = {c.outcome for c in cells if c.sdk_semver is None}
    releases = [c.sdk_semver for c in cells if c.sdk_semver is not None]
    released = {c.outcome for c in cells if c.sdk_semver is not None}
    if len(branch) == 1 and len(released) == 1:
        major, minor, _ = max(releases)
        return [
            {"verdict": released.pop(), "before": f"{major}.{minor + 1}.0"},
            {"verdict": branch.pop()},
        ]
    raise VerdictError(f"cells disagree:\n{_listing(cells)}")


def _listing(cells: Iterable[Cell]) -> str:
    ordered = sorted(
        cells, key=lambda c: (c.sdk, _order(c.sdk_semver), c.version, c.platform)
    )
    return "\n".join(f"    {c}" for c in ordered)


def plaintext_digest(
    manifest: dict[str, Any], name: str, earlier: str | None = None
) -> str | None:
    """The generator's plaintext digest for ``name``, by its base for derived
    fixtures, else ``earlier`` (the sidecar's own); None for synthetic ones,
    whose plaintext is unknown."""
    if name.startswith("synthetic-"):
        return None
    base = sidecars.base_of(Path(), name)
    entry = manifest.get(base.name if base else name)
    return entry["plaintext_sha256"] if entry else earlier


def load_generator_manifest(scratch: Path) -> dict[str, Any]:
    """The generator's manifest.json, or {} when the scratch is gone."""
    path = scratch / "manifest.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def _synthetic_note(raw: dict[str, Any]) -> str:
    codes = raw.get("must_contain", [])
    if any(c.startswith(_NO_MANIFEST) for c in codes):
        return "Synthetic: no usable manifest."
    if _NO_KEY_ACCESS in codes:
        return "Synthetic: no key access object."
    return "Synthetic: no KAS holds this key."


def _skip_note(sdk: str, needs: Sequence[str]) -> str:
    what = needs[0] if len(needs) == 1 else f"one of {', '.join(needs)}"
    return (
        f"The {sdk} cell is skipped because {sdk} lacks {what};"
        f" {sdk} takes the other SDKs' verdict."
    )


def _forged_comment(by_sdk: dict[str, list[Cell]]) -> list[str]:
    """What the recorded runs saw for the forged x5c fixture, when every
    build decrypted it."""
    cells = [c for cs in by_sdk.values() for c in cs]
    if not cells or any(c.outcome != "decrypt" for c in cells):
        return []

    def names(pairs: dict[str, corpus.Semver | None]) -> str:
        return " and ".join(sorted(pairs, key=lambda n: _order(pairs[n])))

    builds = ", ".join(
        f"{sdk} {names({c.version: c.sdk_semver for c in by_sdk[sdk]})}"
        for sdk in corpus.SDK_NAMES
        if by_sdk.get(sdk)
    )
    platforms = names({c.platform: c.platform_semver for c in cells})
    return [
        f"Observed when these verdicts were recorded, on platforms {platforms}:"
        f" every SDK build tested ({builds}) decrypts this file with the genuine"
        " signer's public key configured."
    ]


def _toml(v: SdkVerdict) -> str:
    if isinstance(v, str):
        return json.dumps(v)
    tables = (
        "{ " + ", ".join(f"{k} = {json.dumps(x)}" for k, x in e.items()) + " }"
        for e in v
    )
    return f"[{', '.join(tables)}]"


def render_table(
    digest: str | None,
    verdicts: dict[str, SdkVerdict],
    note: str | None,
    comments: Sequence[str] = (),
) -> str:
    lines = ["[sdk]\n", sidecars.comment_lines(comments)]
    if digest:
        lines.append(f"plaintext_sha256 = {json.dumps(digest)}\n")
    lines += [f"{sdk} = {_toml(verdicts[sdk])}\n" for sdk in corpus.SDK_NAMES]
    if note:
        lines.append(f"note = {json.dumps(note)}\n")
    return "".join(lines)


def _unresolved(table: corpus.SdkTable, sdk: str, cells: Iterable[Cell]) -> list[Cell]:
    """The cells ``table`` does not resolve to their recorded outcome."""
    return [
        c
        for c in cells
        if corpus.resolve_verdict(table, sdk, c.sdk_semver, c.platform_semver)
        != c.outcome
    ]


@dataclass(frozen=True)
class Earlier:
    """A sidecar's existing [sdk] table, parsed and as written."""

    table: corpus.SdkTable
    written: dict[str, Any]

    def entry(self, sdk: str, cells: Sequence[Cell]) -> SdkVerdict | None:
        """The SDK's entry as written, if it gives every cell."""
        return None if _unresolved(self.table, sdk, cells) else self.written[sdk]


def table_text(
    name: str,
    raw: dict[str, Any],
    by_sdk: dict[str, list[Cell]],
    digest: str | None,
    needs: Sequence[str],
    earlier: Earlier | None = None,
) -> tuple[str, list[str]]:
    """The [sdk] table for one fixture, and the SDKs whose earlier entry it
    kept. ``needs`` names the capabilities its decrypt needs; only they explain
    an SDK with no cells, which then gets the outcome all other cells share."""
    ran = [c for cells in by_sdk.values() for c in cells]
    if not ran:
        raise VerdictError(f"{name}: {_NO_CELLS}")
    synthetic = name.startswith("synthetic-")
    problems: list[str] = []
    kept: list[str] = []
    notes = [_synthetic_note(raw)] if synthetic else []
    out: dict[str, SdkVerdict] = {}
    for sdk in corpus.SDK_NAMES:
        cells = by_sdk.get(sdk, [])
        if not cells:
            outcomes = {c.outcome for c in ran}
            if not needs:
                problems.append(f"no {sdk} cells, and no capability explains it")
            elif len(outcomes) > 1:
                problems.append(
                    f"no {sdk} cells, and the SDKs that ran disagree:\n{_listing(ran)}"
                )
            else:
                out[sdk] = outcomes.pop()
                notes.append(_skip_note(sdk, needs))
            continue
        for c in cells:
            if c.outcome not in corpus.VERDICTS:
                problems.append(f"{c}, which is not a verdict")
            elif c.outcome == "decrypt" and synthetic:
                problems.append(f"{c}, but synthetic files must be rejected")
            elif c.outcome == "decrypt" and digest is None:
                problems.append(f"{c}, but no plaintext digest is known")
            elif c.outcome == "decrypt" and c.output_sha256 != digest:
                problems.append(f"{c}, but its output is not the plaintext")
        try:
            out[sdk] = collapse(cells)
        except VerdictError as e:
            entry = earlier.entry(sdk, cells) if earlier else None
            if entry is None:
                problems.append(
                    f"{sdk} {e}\n"
                    f"    and the sidecar has no {sdk} entry that gives them all"
                )
            else:
                out[sdk] = entry
                kept.append(sdk)
    if problems:
        raise VerdictError("\n".join(f"{name}: {p}" for p in problems))
    comments = _forged_comment(by_sdk) if name == f"{sidecars.FORGED}.tdf" else []
    return render_table(digest, out, " ".join(notes) or None, comments), kept


Records = dict[str, dict[str, list[Cell]]]


def load_records(paths: Sequence[Path]) -> Records:
    out: defaultdict[str, defaultdict[str, list[Cell]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            cell = Cell.from_row(row := json.loads(line))
            if cell.sdk not in corpus.SDK_NAMES:
                raise VerdictError(f"{path}: unknown sdk {cell.sdk!r}")
            out[row["fixture"]][cell.sdk].append(cell)
    return {f: dict(by) for f, by in out.items()}


def _check(texts: dict[Path, str], records: Records) -> list[str]:
    """Each new sidecar parses and resolves every recorded cell to its outcome."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for path, text in texts.items():
            name = path.name.removesuffix(corpus.SIDECAR_SUFFIX)
            probe = Path(tmp) / path.name
            probe.write_text(text)
            try:
                table = corpus.load_sidecar(probe).sdk
            except corpus.SidecarError as e:
                problems.append(f"{name}: {e}")
                continue
            assert table is not None
            problems += [
                f"{name}: the table does not give {c}"
                for sdk, cells in records[name].items()
                for c in _unresolved(table, sdk, cells)
            ]
    return problems


def _earlier(path: Path, table: corpus.SdkTable | None) -> Earlier | None:
    if table is None:
        return None
    return Earlier(table, tomllib.loads(path.read_text())["sdk"])


def build_sidecars(
    records: Records, manifest: dict[str, Any], root: Path, stage: Path | None = None
) -> tuple[dict[Path, str], list[str]]:
    """New text for every non-golden sidecar in ``root``, and for its copy in
    ``stage`` if there is one: its lines up to any earlier [sdk] table,
    unchanged, then the new table. Also the earlier entries kept, as
    "<fixture> <sdk>". ``manifest`` is the generator's; a fixture it lacks keeps
    its sidecar's plaintext_sha256."""
    keys = corpus.kas_keys(root)
    names = [f.name for f in corpus.fixtures(root) if not f.name.startswith("golden-")]
    problems = [
        f"{n}: recorded, but not a non-golden fixture in {root}"
        for n in sorted(set(records) - set(names))
    ]
    texts: dict[Path, str] = {}
    kept: list[str] = []
    for name in names:
        sidecar = f"{name}{corpus.SIDECAR_SUFFIX}"
        path = root / sidecar
        if name not in records:
            problems.append(f"{name}: {_NO_CELLS}")
            continue
        try:
            sc = corpus.load_sidecar(path)
            digest = plaintext_digest(
                manifest, name, sc.sdk.plaintext_sha256 if sc.sdk else None
            )
            needs = corpus.required_features(corpus.read_manifest(root / name), keys)
            table, kept_sdks = table_text(
                name, sc.raw, records[name], digest, needs, _earlier(path, sc.sdk)
            )
            kept += [f"{name} {sdk}" for sdk in kept_sdks]
            copies = [path, *([stage / sidecar] if stage else [])]
            for p in (p for p in copies if p.is_file()):
                head, _ = sidecars.split_sdk_table(p.read_text())
                texts[p] = sidecars.with_sdk_table(head, table)
        except (VerdictError, corpus.SidecarError, sidecars.SidecarGenError) as e:
            problems.append(str(e))
    problems += _check(texts, records)
    if problems:
        raise VerdictError("\n".join(problems))
    return texts, kept


def _summary(paths: Iterable[Path], records: Records) -> list[str]:
    counts = {sdk: [0, 0] for sdk in corpus.SDK_NAMES}
    bounded: list[str] = []
    for path in paths:
        name = path.name.removesuffix(corpus.SIDECAR_SUFFIX)
        table = corpus.load_sidecar(path).sdk
        assert table is not None
        for sdk, entries in table.verdicts.items():
            counts[sdk][len(entries) > 1] += 1
            if len(entries) > 1:
                bounded.append(f"  {name} {sdk}: {entries}")
    skipped = [
        f"  {name} {sdk}"
        for name in sorted(records)
        for sdk in corpus.SDK_NAMES
        if sdk not in records[name]
    ]
    out = [f"{sdk}: {n} bare, {b} bounded" for sdk, (n, b) in counts.items()]
    out += ["bounded:", *bounded] if bounded else ["bounded: none"]
    return [*out, "skipped (others' verdict):", *skipped] if skipped else out


def run_verdicts(
    paths: Sequence[Path], scratch: Path, root: Path = corpus.CORPUS_DIR
) -> int:
    stage = scratch / "stage"
    try:
        manifest = load_generator_manifest(scratch)
        records = load_records(paths)
        texts, kept = build_sidecars(records, manifest, root, stage)
    except (VerdictError, OSError, ValueError, KeyError) as e:
        print(f"refused; nothing written:\n{e}", file=sys.stderr)
        return 1
    for path, text in texts.items():
        path.write_text(text)
    written = [p for p in texts if p.parent == root]
    print(f"{len(written)} [sdk] tables in {root}")
    print(f"{len(texts) - len(written)} staged copies updated in {stage}")
    for line in _summary(written, records):
        print(line)
    print("kept earlier entries:", ", ".join(kept) or "none")
    return 0
