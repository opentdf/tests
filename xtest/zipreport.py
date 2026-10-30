"""Collect and render ``test_zip_conformance.py``'s per-cell outcomes.

A conformance cell passes whether the SDK read the mutated container or
rejected it cleanly. That is deliberate -- a reader declining a 0xFFFF comment
has lost nobody any data -- but it means the pass/fail line says nothing about
which of the two happened, and the two results worth knowing about (a reader
refusing a structure APPNOTE permits, a reader accepting a malformed one) are
invisible in a green matrix. Each judged container records what happened as a
``user_properties`` entry; this module turns a run's worth of them into the
table someone reads.

The collecting end is a pytest hook, so it lives in ``conftest.py``. Parsing
and rendering live here so they can be exercised offline in
``test_zip_conformance_units.py`` rather than only by a full cross-SDK run.

Summarising in-process is also what keeps ``junit_family`` at its default.
Per-testcase properties are only schema-valid under ``xunit1``, so reading
these back out of the junit XML costs a non-default ini setting, and buys a
channel that exists only in CI -- the same run locally would print nothing.
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeIs, get_args

#: Property name every judged container is recorded under. One property
#: carrying all the fields as JSON, rather than one property per field: a cell
#: that judges two containers writes two records, and a reader keying by
#: property name would keep only the last without noticing it dropped one.
PROPERTY = "zip_conformance"

#: Where a run's records go, relative to the rootdir. Alongside the html
#: reports, because CI's upload step globs ``test-results/**/*.json``.
DEFAULT_OUT = Path("test-results/zip-conformance.json")

#: Whether a mutation produces a structure APPNOTE permits ("spec-legal") or
#: one it does not ("adversarial"). This never changes whether a cell passes
#: -- only which of the two passing outcomes is worth reporting.
Legality = Literal["spec-legal", "adversarial"]

#: What the decrypting SDK did with the container.
Outcome = Literal["accepted", "rejected"]

#: The two ``(legality, outcome)`` quadrants that pass without being
#: conformant. The other two are the expected result and need no reporting.
NOT_CONFORMANT: frozenset[tuple[Legality, Outcome]] = frozenset(
    {("spec-legal", "rejected"), ("adversarial", "accepted")}
)


def is_legality(val: object) -> TypeIs[Legality]:
    return val in get_args(Legality)


def is_outcome(val: object) -> TypeIs[Outcome]:
    return val in get_args(Outcome)


class MalformedRecordError(ValueError):
    """A :data:`PROPERTY` value that did not come from :func:`encode`."""


@dataclass(frozen=True, slots=True)
class Cell:
    """One mutated container, as judged by one decrypting SDK."""

    node_id: str
    #: ``sdk@version``, so two builds of one SDK stay separate rows.
    sdk: str
    legality: Legality
    outcome: Outcome
    diagnostic: str = ""

    @property
    def conformant(self) -> bool:
        """Whether this is the answer a conformant reader gives.

        Not whether the cell passed -- both outcomes pass. Readers should be
        liberal in what they accept, so accepting a spec-legal structure and
        rejecting an adversarial one are the conformant answers.
        """
        return (self.legality, self.outcome) not in NOT_CONFORMANT


def encode(
    sdk: str, *, legality: Legality, outcome: Outcome, diagnostic: str = ""
) -> str:
    """Render one record for a cell's ``user_properties``.

    Keyword-only because ``legality`` and ``outcome`` are both short strings:
    passed positionally in the wrong order, every cell would read as
    conformant and the report would quietly say nothing.

    ``diagnostic`` must already be the allowlist-matched slice: this value
    reaches CI logs and uploaded artifacts.
    """
    record = {"sdk": sdk, "legality": legality, "outcome": outcome}
    if diagnostic:
        record["diagnostic"] = diagnostic
    return json.dumps(record, separators=(",", ":"))


def collect(node_id: str, user_properties: Iterable[tuple[str, object]]) -> list[Cell]:
    """Every conformance record in one test report's properties.

    Properties other than :data:`PROPERTY` belong to some other suite and are
    left alone. A :data:`PROPERTY` value :func:`encode` could not have written
    raises :class:`MalformedRecordError` rather than being dropped or read as
    something it is not.
    """
    cells: list[Cell] = []
    for name, value in user_properties:
        if name != PROPERTY:
            continue
        cells.append(_decode(node_id, value))
    return cells


def _decode(node_id: str, value: object) -> Cell:
    try:
        record = json.loads(str(value))
    except json.JSONDecodeError as e:
        raise MalformedRecordError(f"{node_id}: {PROPERTY} is not JSON: {e}") from e
    if not isinstance(record, dict):
        raise MalformedRecordError(f"{node_id}: {PROPERTY} is not an object: {value!r}")
    sdk = record.get("sdk")
    legality = record.get("legality")
    outcome = record.get("outcome")
    diagnostic = record.get("diagnostic", "")
    if not (
        isinstance(sdk, str)
        and sdk
        and is_legality(legality)
        and is_outcome(outcome)
        and isinstance(diagnostic, str)
    ):
        raise MalformedRecordError(f"{node_id}: unrecognised {PROPERTY}: {value!r}")
    return Cell(
        node_id=node_id,
        sdk=sdk,
        legality=legality,
        outcome=outcome,
        diagnostic=diagnostic,
    )


@dataclass(frozen=True, slots=True)
class Summary:
    """A run's records, counted, with the notable ones pulled out."""

    counts: Counter[tuple[str, str, str]]
    notable: dict[str, list[Cell]]


def summarize(cells: Iterable[Cell]) -> Summary:
    """Count every ``(sdk, legality, outcome)`` and keep the notable cells.

    Cells are sorted first: under xdist they arrive in whatever order the
    workers finish, and a printed table or step summary that reorders itself
    between two identical runs is one nobody can compare.
    """
    counts: Counter[tuple[str, str, str]] = Counter()
    notable: dict[str, list[Cell]] = {}
    for cell in sorted(cells, key=lambda c: (c.sdk, c.node_id)):
        counts[(cell.sdk, cell.legality, cell.outcome)] += 1
        if not cell.conformant:
            notable.setdefault(cell.sdk, []).append(cell)
    return Summary(counts=counts, notable=notable)


def terminal_lines(summary: Summary) -> list[str]:
    """The summary as the terminal reporter prints it at end of run."""
    width = max((len(sdk) for sdk, _, _ in summary.counts), default=0)
    width = max(width, 5)
    lines = [
        f"{sdk:{width}} {legality:12} {outcome:9} x{count}"
        for (sdk, legality, outcome), count in sorted(summary.counts.items())
    ]
    for sdk, cells in sorted(summary.notable.items()):
        lines.append(f"{sdk}: {len(cells)} cell(s) passed without being conformant")
        lines += [
            f"  {cell.node_id}: {cell.outcome} [{cell.diagnostic or '-'}]"
            for cell in cells
        ]
    return lines


def markdown(summary: Summary) -> str:
    """Render the summary as a GitHub step summary."""
    lines = [
        "## ZIP conformance outcomes",
        "",
        "Every cell here passed. A reader is *conformant* when it accepts the "
        "spec-legal structures and rejects the adversarial ones; one that does "
        "the opposite is merely safe, which a green matrix cannot show.",
        "",
        "| SDK | container | outcome | cells |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| {sdk} | {legality} | {outcome} | {count} |"
        for (sdk, legality, outcome), count in sorted(summary.counts.items())
    ]
    for sdk, cells in sorted(summary.notable.items()):
        lines += [
            "",
            f"**{sdk}: {len(cells)} cell(s) passed without being conformant**",
            "",
        ]
        lines += [
            f"- `{cell.node_id}`: {cell.outcome} [{cell.diagnostic or '-'}]"
            for cell in cells
        ]
    return "\n".join(lines) + "\n"


def write_json(path: Path, cells: Iterable[Cell]) -> Path:
    """Write every record for anything that wants to post-process the run.

    ``conformant`` is derived, but it is written out anyway: it is the whole
    point of the artifact, and re-deriving it means duplicating
    :data:`NOT_CONFORMANT` in whatever reads this.
    """
    ordered = sorted(cells, key=lambda c: (c.node_id, c.sdk))
    payload = {
        "cells": [
            dataclasses.asdict(cell) | {"conformant": cell.conformant}
            for cell in ordered
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
