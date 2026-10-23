"""Results, baseline and report for the cross-SDK validity suite (DSPX-5349).

Three things live here, all offline and all exercised by
``test_tdf_validity_units.py``:

1. **The CLI contract.** Every SDK's ``cli.sh validate <file>`` passes its
   CLI's stdout and exit status through unchanged:

   - exit 0, stdout ``{"valid":true}``: the file is a valid TDF;
   - exit 3, stdout ``{"valid":false,"reason":"..."}``: the check ran and the
     file is not a valid TDF;
   - anything else -- another exit status, a signal, a timeout, or stdout that
     is not exactly one such JSON line -- means the check could not run.

   Not exit 1 for "invalid": cobra, Node and picocli all exit 1 on an
   unhandled error (and picocli 2 on a usage error), so a crash would read as
   a verdict. :func:`parse_output` turns a finished process into a
   :class:`ValidateResult`.

2. **The baseline.** ``tdfvalidity_baseline.json`` records, per case and SDK,
   every answer that is *not* the case's agreed answer -- each carrying the
   ticket that explains it -- plus every SDK's answer to the cases that have
   no agreed answer yet. :func:`judge` holds an observed result to it. Any
   difference fails the cell: a validator growing more lenient and a
   divergence quietly disappearing are both news.

3. **The report.** Each judged cell is recorded on its test report; the
   conftest hook collects them into ``test-results/tdf-validity.json`` (a
   case x SDK table) and a terminal / step summary.

To refresh the baseline from a run, see :func:`refresh` and
``spec/tdf-validity.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, cast, get_args

#: Exit status of a CLI whose check completed and found the file valid.
EXIT_VALID = 0
#: Exit status of a CLI whose check completed and found the file invalid.
EXIT_INVALID = 3

Outcome = Literal["valid", "invalid", "error"]
#: What the baseline expects of one SDK on one case. ``pending`` means no
#: expectation has been recorded yet: the cell is reported, not judged.
Expected = Literal["valid", "invalid", "error", "pending"]
#: A case's agreed answer. ``undecided`` cases have an open decision ticket
#: and each SDK's current answer is pinned in the baseline. ``unspecified``
#: cases are outside what any validity API promises (payload integrity, say);
#: they are pinned the same way but need no ticket, because there is no agreed
#: answer for an SDK to deviate from.
Expect = Literal["valid", "invalid", "undecided", "unspecified"]
#: Where a rejection belongs. A reader can reject at the wrong layer -- an
#: archive that fails "entry count is not 2" never exercises its directory
#: walk (DSPX-4924) -- so where an SDK reports a reason, the baseline can hold
#: it to the case's layer.
Layer = Literal["archive", "manifest-missing", "manifest-json", "manifest-schema"]
Status = Literal["match", "drift", "reason", "pending"]

LAYERS: frozenset[str] = frozenset(get_args(Layer))
BASELINE_PATH = Path(__file__).parent / "tdfvalidity_baseline.json"
DEFAULT_REPORT = Path("test-results/tdf-validity.json")
#: Name every judged cell is recorded under in ``user_properties``.
PROPERTY = "tdf_validity"

_TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
#: How much of a reason or diagnostic to keep. Go's schema failures list
#: every violation, and a report nobody can read is not a report.
_KEEP = 400


# --- the CLI contract --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidateResult:
    """What one ``cli.sh validate`` run said, classified."""

    outcome: Outcome
    #: For ``invalid``, the CLI's reason. For ``error``, what went wrong.
    reason: str = ""
    #: None when the process was killed for running past its timeout.
    returncode: int | None = None
    #: The tail of stderr, kept for diagnosing an ``error``.
    stderr: str = ""


def _head(text: str, n: int = _KEEP) -> str:
    """The start of a reason: where every SDK says which layer rejected it."""
    text = text.strip()
    return text if len(text) <= n else text[:n] + "..."


def _tail(raw: bytes | str, n: int = _KEEP) -> str:
    """The end of stderr: where a stack trace says what actually failed."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = text.strip()
    return text if len(text) <= n else "..." + text[-n:]


def parse_output(
    returncode: int | None,
    stdout: bytes,
    stderr: bytes = b"",
    *,
    timed_out: bool = False,
    timeout: float | None = None,
) -> ValidateResult:
    """Classify one finished ``validate`` process against the contract.

    Strict on purpose. Exit 0 or 3 is a verdict only if stdout agrees with it,
    as exactly one JSON object; anything else is reported as an ``error``
    naming the violation, because a shim or CLI that has drifted from the
    contract is not answering the question this suite asks.
    """
    err = _tail(stderr)
    if timed_out:
        return ValidateResult("error", f"timed out after {timeout}s", None, err)
    if returncode is None:
        return ValidateResult("error", "no exit status", None, err)
    if returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = f"signal {-returncode}"
        return ValidateResult("error", f"killed by {name}", returncode, err)
    if returncode not in (EXIT_VALID, EXIT_INVALID):
        return ValidateResult(
            "error", f"exit {returncode}: the check could not run", returncode, err
        )

    text = stdout.decode("utf-8", errors="replace").strip()
    lines = text.splitlines()
    if len(lines) != 1:
        return ValidateResult(
            "error",
            f"exit {returncode} but stdout has {len(lines)} lines, not one JSON "
            f"line: {_tail(text, 200)!r}",
            returncode,
            err,
        )
    try:
        record = json.loads(lines[0])
    except json.JSONDecodeError:
        return ValidateResult(
            "error",
            f"exit {returncode} but stdout is not JSON: {_tail(text, 200)!r}",
            returncode,
            err,
        )
    if not isinstance(record, dict) or not isinstance(record.get("valid"), bool):
        return ValidateResult(
            "error",
            f'exit {returncode} but stdout has no boolean "valid": {_tail(text, 200)!r}',
            returncode,
            err,
        )
    record = cast(dict[str, Any], record)
    valid: bool = record["valid"]
    if valid != (returncode == EXIT_VALID):
        return ValidateResult(
            "error",
            f'exit {returncode} contradicts stdout "valid":{json.dumps(valid)}',
            returncode,
            err,
        )
    if valid:
        return ValidateResult("valid", "", returncode, err)
    reason = record.get("reason", "")
    if not isinstance(reason, str):
        return ValidateResult(
            "error", f'"reason" is not a string: {reason!r}', returncode, err
        )
    return ValidateResult("invalid", _head(reason), returncode, err)


# --- the baseline ------------------------------------------------------------


class Spec(Protocol):
    """What :func:`judge` needs to know about a case."""

    @property
    def id(self) -> str: ...

    @property
    def expect(self) -> Expect: ...

    @property
    def layer(self) -> Layer | None: ...

    @property
    def ticket(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class Cell:
    """One SDK's recorded answer to one case."""

    outcome: Expected
    #: Why this differs from the agreed answer. Required whenever it does.
    ticket: str | None = None
    #: Where this SDK's rejection lands, when it is not the case's layer --
    #: Go reads a deflated manifest as JSON, say, rather than refusing the
    #: compression method.
    layer: Layer | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class SdkBaseline:
    #: ``seeded``: every case is judged. ``pending``: cells without a recorded
    #: answer are reported but not judged, until the SDK's first real run is
    #: folded in with :func:`refresh`.
    status: Literal["seeded", "pending"]
    source: str = ""
    ticket: str | None = None
    #: Regex per layer, searched (case-insensitively) in this SDK's reason for
    #: an invalid verdict. Absent for an SDK whose reasons are not yet known.
    reason_patterns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Baseline:
    sdks: dict[str, SdkBaseline]
    #: case id -> cell key -> cell. A cell key is an SDK name (``go``), or for
    #: a round trip optionally ``<validator>:<writer>`` (``go:java``) when one
    #: writer's output is judged differently from the rest.
    cells: dict[str, dict[str, Cell]]

    def cell(self, case_id: str, sdk: str, writer: str | None = None) -> Cell | None:
        row = self.cells.get(case_id, {})
        if writer is not None and f"{sdk}:{writer}" in row:
            return row[f"{sdk}:{writer}"]
        return row.get(sdk)

    def expected(self, spec: Spec, sdk: str, writer: str | None = None) -> Cell:
        """What ``sdk`` should say about ``spec``.

        A recorded cell wins. Otherwise a seeded SDK is held to the agreed
        answer, and a pending SDK -- or any SDK on a case with no agreed answer
        that nobody has recorded yet -- is ``pending``.
        """
        recorded = self.cell(spec.id, sdk, writer)
        if recorded is not None:
            return recorded
        sb = self.sdks.get(sdk)
        if sb is None or sb.status == "pending":
            return Cell("pending")
        if spec.expect in ("valid", "invalid"):
            return Cell(cast(Expected, spec.expect))
        return Cell("pending")


def _cell_from_json(raw: object, where: str) -> Cell:
    if isinstance(raw, str):
        raw = {"outcome": raw}
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: a cell is a string or an object, not {raw!r}")
    raw = cast(dict[str, Any], raw)
    unknown = set(raw) - {"outcome", "ticket", "layer", "note"}
    if unknown:
        raise ValueError(f"{where}: unknown cell keys {sorted(unknown)}")
    outcome = raw.get("outcome")
    if outcome not in get_args(Expected):
        raise ValueError(
            f"{where}: outcome {outcome!r} is not one of {get_args(Expected)}"
        )
    ticket = raw.get("ticket")
    if ticket is not None and not _TICKET_RE.match(str(ticket)):
        raise ValueError(f"{where}: ticket {ticket!r} is not a tracker key")
    layer = raw.get("layer")
    if layer is not None and layer not in LAYERS:
        raise ValueError(f"{where}: layer {layer!r} is not one of {sorted(LAYERS)}")
    return Cell(
        cast(Expected, outcome),
        ticket,
        cast(Layer | None, layer),
        str(raw.get("note", "")),
    )


def _cell_to_json(cell: Cell) -> str | dict[str, str]:
    if cell.ticket is None and cell.layer is None and not cell.note:
        return cell.outcome
    out: dict[str, str] = {"outcome": cell.outcome}
    if cell.ticket:
        out["ticket"] = cell.ticket
    if cell.layer:
        out["layer"] = cell.layer
    if cell.note:
        out["note"] = cell.note
    return out


def parse_baseline(doc: Mapping[str, Any]) -> Baseline:
    if doc.get("format") != 1:
        raise ValueError(f"unsupported baseline format {doc.get('format')!r}")
    sdks: dict[str, SdkBaseline] = {}
    for name, raw in doc.get("sdks", {}).items():
        patterns = dict(raw.get("reason_patterns", {}))
        for layer, pattern in patterns.items():
            if layer not in LAYERS:
                raise ValueError(
                    f"sdks.{name}: reason pattern for unknown layer {layer!r}"
                )
            re.compile(pattern)
        status = raw.get("status")
        if status not in ("seeded", "pending"):
            raise ValueError(f"sdks.{name}: status {status!r} is not seeded or pending")
        sdks[name] = SdkBaseline(
            status=status,
            source=raw.get("source", ""),
            ticket=raw.get("ticket"),
            reason_patterns=patterns,
        )
    cells: dict[str, dict[str, Cell]] = {}
    for case_id, row in doc.get("cells", {}).items():
        cells[case_id] = {
            key: _cell_from_json(raw, f"cells.{case_id}.{key}")
            for key, raw in row.items()
        }
    return Baseline(sdks, cells)


def load_baseline(path: Path = BASELINE_PATH) -> Baseline:
    return parse_baseline(json.loads(path.read_text(encoding="utf-8")))


def dump_baseline(baseline: Baseline, header: Mapping[str, Any] | None = None) -> str:
    """Serialise ``baseline`` with sorted keys, so a refresh diffs cleanly."""
    doc: dict[str, Any] = dict(header or {})
    doc["format"] = 1
    doc["sdks"] = {
        name: {k: v for k, v in asdict(sb).items() if v not in (None, "", {})}
        for name, sb in sorted(baseline.sdks.items())
    }
    doc["cells"] = {
        case_id: {key: _cell_to_json(c) for key, c in sorted(row.items())}
        for case_id, row in sorted(baseline.cells.items())
        if row
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def problems(baseline: Baseline, specs: Iterable[Spec]) -> list[str]:
    """Everything wrong with ``baseline`` as a description of ``specs``.

    - a row for a case that does not exist;
    - a cell key naming an SDK the baseline does not describe;
    - a cell that differs from its case's agreed answer without a ticket;
    - a seeded SDK with no recorded answer to a case that has no agreed one;
    - a cell that just repeats the agreed answer, with nothing to say.
    """
    by_id = {s.id: s for s in specs}
    out = [
        f"{case_id}: baseline row for a case that is not in the corpus"
        for case_id in sorted(set(baseline.cells) - set(by_id))
    ]
    for case_id, row in sorted(baseline.cells.items()):
        spec = by_id.get(case_id)
        if spec is None:
            continue
        for key, cell in sorted(row.items()):
            sdk = key.split(":", 1)[0]
            if sdk not in baseline.sdks:
                out.append(f"{case_id}.{key}: no such SDK in the baseline")
            if cell.outcome == "pending":
                continue
            differs = spec.expect not in ("valid", "invalid", "unspecified") or (
                spec.expect in ("valid", "invalid")
                and (cell.outcome != spec.expect or cell.layer is not None)
            )
            if differs and not (cell.ticket or spec.ticket):
                out.append(
                    f"{case_id}.{key}: {cell.outcome} differs from the agreed "
                    f"{spec.expect} without a ticket"
                )
            if (
                spec.expect in ("valid", "invalid")
                and cell.outcome == spec.expect
                and cell.layer is None
                and not cell.note
            ):
                out.append(
                    f"{case_id}.{key}: repeats the agreed answer; delete the cell"
                )
    for spec in by_id.values():
        if spec.expect in ("valid", "invalid"):
            continue
        for sdk, sb in sorted(baseline.sdks.items()):
            if sb.status == "seeded" and baseline.cell(spec.id, sdk) is None:
                out.append(
                    f"{spec.id}.{sdk}: {spec.expect} case with no recorded answer "
                    f"for seeded SDK {sdk}"
                )
    return out


# --- judging -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Verdict:
    """One SDK's answer to one case, held to the baseline."""

    case_id: str
    #: SDK name, the baseline key: ``go``.
    sdk: str
    #: The build that answered: ``go@main``.
    build: str
    expect: Expect
    expected: Expected
    observed: Outcome
    status: Status
    reason: str = ""
    ticket: str | None = None
    #: For a round trip, the SDK that wrote the file.
    writer: str | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("match", "pending")


def _describe(cell: Cell, case_ticket: str | None) -> str:
    ticket = cell.ticket or case_ticket
    return f"{cell.outcome}" + (f" ({ticket})" if ticket else "")


def judge(
    spec: Spec,
    sdk: str,
    build: str,
    result: ValidateResult,
    baseline: Baseline,
    *,
    writer: str | None = None,
) -> Verdict:
    """Hold ``result`` to the baseline, and say what to do if it differs."""
    cell = baseline.expected(spec, sdk, writer)
    ticket = cell.ticket or spec.ticket
    base = {
        "case_id": spec.id,
        "sdk": sdk,
        "build": build,
        "expect": spec.expect,
        "expected": cell.outcome,
        "observed": result.outcome,
        "reason": result.reason,
        "ticket": ticket,
        "writer": writer,
    }

    if result.outcome == "error" and cell.outcome != "error":
        return Verdict(
            **base,
            status="drift",
            message=(
                f"{build} could not check {spec.id}: {result.reason}"
                + (f"\nstderr: {result.stderr}" if result.stderr else "")
            ),
        )
    if cell.outcome == "pending":
        return Verdict(**base, status="pending", message=f"{build}: no baseline yet")
    if result.outcome != cell.outcome:
        if cell.ticket and result.outcome == spec.expect:
            hint = (
                f"{cell.ticket} no longer reproduces here. If it is fixed, delete "
                "this cell from tdfvalidity_baseline.json."
            )
        elif spec.expect in ("undecided", "unspecified"):
            hint = (
                "This case has no agreed answer, so the change itself is the "
                "finding: record the new answer in tdfvalidity_baseline.json"
                + (f" and on {spec.ticket}." if spec.ticket else ".")
            )
        else:
            hint = (
                "A new divergence: file a ticket, and record the cell with it in "
                "tdfvalidity_baseline.json."
            )
        reason = f" ({result.reason})" if result.reason else ""
        return Verdict(
            **base,
            status="drift",
            message=(
                f"{build} says {spec.id} is {result.outcome}{reason}; the baseline "
                f"says {_describe(cell, spec.ticket)} and the agreed answer is "
                f"{spec.expect}. {hint}"
            ),
        )
    if result.outcome == "invalid":
        layer = cell.layer or spec.layer
        pattern = (
            baseline.sdks[sdk].reason_patterns.get(layer)
            if layer and sdk in baseline.sdks
            else None
        )
        if pattern and not re.search(pattern, result.reason, re.IGNORECASE):
            return Verdict(
                **base,
                status="reason",
                message=(
                    f"{build} rejected {spec.id}, but its reason does not look like "
                    f"a {layer}-layer rejection (/{pattern}/): {result.reason!r}. "
                    "A reader can reject at the wrong layer; if this one does, "
                    "record the cell's layer with a ticket. If the CLI's wording "
                    "changed instead, update reason_patterns."
                ),
            )
    return Verdict(**base, status="match")


# --- the report --------------------------------------------------------------


def encode(verdict: Verdict) -> str:
    """One verdict as a ``user_properties`` value."""
    return json.dumps(asdict(verdict), separators=(",", ":"))


def collect(user_properties: Iterable[tuple[str, object]]) -> list[Verdict]:
    """Every verdict in one test report's properties; others are ignored."""
    return [
        Verdict(**json.loads(str(value)))
        for name, value in user_properties
        if name == PROPERTY
    ]


def _order(verdicts: Iterable[Verdict]) -> list[Verdict]:
    # Under xdist verdicts arrive in whatever order workers finish; a report
    # that reorders itself between identical runs is one nobody can diff.
    return sorted(verdicts, key=lambda v: (v.case_id, v.writer or "", v.build))


def _column(v: Verdict) -> str:
    return f"{v.build}<-{v.writer}" if v.writer else v.build


def report(verdicts: Iterable[Verdict], corpus_digest: str = "") -> dict[str, Any]:
    """The case x SDK table, plus per-build tallies."""
    ordered = _order(verdicts)
    table: dict[str, dict[str, Any]] = {}
    tallies: dict[str, Counter[str]] = {}
    for v in ordered:
        row = table.setdefault(v.case_id, {"expect": v.expect})
        cell: dict[str, Any] = {
            "observed": v.observed,
            "expected": v.expected,
            "status": v.status,
        }
        if v.ticket:
            cell["ticket"] = v.ticket
        if v.reason:
            cell["reason"] = v.reason
        row[_column(v)] = cell
        tallies.setdefault(v.build, Counter())[v.status] += 1
    return {
        "format": 1,
        "corpus_digest": corpus_digest,
        "builds": {b: dict(sorted(c.items())) for b, c in sorted(tallies.items())},
        "table": table,
        "verdicts": [asdict(v) for v in ordered],
    }


def write_report(
    path: Path, verdicts: Iterable[Verdict], corpus_digest: str = ""
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report(verdicts, corpus_digest), indent=2) + "\n", encoding="utf-8"
    )
    return path


def terminal_lines(verdicts: Iterable[Verdict]) -> list[str]:
    ordered = _order(verdicts)
    tallies: dict[str, Counter[str]] = {}
    for v in ordered:
        tallies.setdefault(v.build, Counter())[v.status] += 1
    lines = [
        f"{build:24} "
        + "  ".join(
            f"{s}={c[s]}" for s in ("match", "drift", "reason", "pending") if c[s]
        )
        for build, c in sorted(tallies.items())
    ]
    lines += [f"  {v.status:7} {_column(v)} {v.case_id}" for v in ordered if not v.ok]
    pending = Counter(v.build for v in ordered if v.status == "pending")
    lines += [
        f"  {build}: {n} cell(s) have no baseline yet; see spec/tdf-validity.md to seed it"
        for build, n in sorted(pending.items())
    ]
    return lines


def markdown(verdicts: Iterable[Verdict]) -> str:
    ordered = _order(verdicts)
    builds = sorted({_column(v) for v in ordered})
    lines = [
        "## TDF validity",
        "",
        "Each SDK's `validate` against the shared corpus. *drift* and *reason* "
        "cells failed; *pending* cells have no baseline yet.",
        "",
        "| build | match | drift | reason | pending |",
        "| --- | --- | --- | --- | --- |",
    ]
    for b in builds:
        c = Counter(v.status for v in ordered if _column(v) == b)
        lines.append(
            f"| {b} | {c['match']} | {c['drift']} | {c['reason']} | {c['pending']} |"
        )
    failed = [v for v in ordered if not v.ok]
    if failed:
        lines += [
            "",
            "| case | build | observed | expected |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            f"| `{v.case_id}` | {_column(v)} | {v.observed} | {v.expected} |"
            for v in failed
        ]
    return "\n".join(lines) + "\n"


# --- refreshing the baseline -------------------------------------------------


def refresh(
    baseline: Baseline,
    specs: Iterable[Spec],
    verdicts: Iterable[Verdict],
    *,
    seed: Iterable[str] = (),
) -> Baseline:
    """Fold a run's observations into ``baseline``.

    For every verdict that did not match -- and, for each SDK named in
    ``seed``, every verdict at all -- the observed answer becomes the cell.
    Cells are kept minimal: one that now matches the agreed answer is
    removed, so a fixed divergence disappears from the file rather than
    lingering. Tickets on surviving cells are kept. A new disagreement gets no
    ticket, so :func:`problems` fails until a person supplies one.

    SDKs in ``seed`` are flipped from ``pending`` to ``seeded``.
    """
    seeded = set(seed)
    by_id = {s.id: s for s in specs}
    cells = {k: dict(v) for k, v in baseline.cells.items()}
    for v in verdicts:
        if v.observed == "error" and v.expected != "error":
            continue  # a broken run is not a baseline
        if v.status == "match" and v.sdk not in seeded:
            continue
        spec = by_id.get(v.case_id)
        if spec is None:
            continue
        # A writer-qualified cell is only ever written by hand; refresh keeps
        # updating it if one exists, and otherwise records per validator.
        key = v.sdk
        if v.writer and f"{v.sdk}:{v.writer}" in baseline.cells.get(v.case_id, {}):
            key = f"{v.sdk}:{v.writer}"
        row = cells.setdefault(v.case_id, {})
        old = row.get(key)
        if spec.expect in ("valid", "invalid") and v.observed == spec.expect:
            if old is not None and old.layer is None:
                row.pop(key)
            continue
        row[key] = Cell(
            cast(Expected, v.observed),
            old.ticket if old else None,
            old.layer if old else None,
            old.note if old else "",
        )
    sdks = {
        name: SdkBaseline(
            "seeded" if name in seeded else sb.status,
            sb.source,
            sb.ticket,
            sb.reason_patterns,
        )
        for name, sb in baseline.sdks.items()
    }
    return Baseline(sdks, {k: v for k, v in cells.items() if v})


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fold a tdf-validity.json run report into the baseline."
    )
    parser.add_argument("report", type=Path, nargs="+")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument(
        "--seed",
        action="append",
        default=[],
        help="SDK to flip from pending to seeded, recording every answer it gave",
    )
    args = parser.parse_args(argv)

    # Imported here: the corpus pulls in every golden file, and nothing else
    # in this module needs it.
    import tdfvalidity_corpus

    specs: list[Spec] = [*tdfvalidity_corpus.corpus(), *tdfvalidity_corpus.ROUND_TRIPS]
    verdicts = [
        Verdict(**raw)
        for path in args.report
        for raw in json.loads(path.read_text(encoding="utf-8"))["verdicts"]
    ]
    doc = json.loads(args.baseline.read_text(encoding="utf-8"))
    header = {k: v for k, v in doc.items() if k.startswith("$") or k == "about"}
    updated = refresh(parse_baseline(doc), specs, verdicts, seed=args.seed)
    args.baseline.write_text(dump_baseline(updated, header), encoding="utf-8")
    for line in problems(updated, specs):
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
