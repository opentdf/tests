"""The baseline, and holding each SDK's answer to it.

``baseline.json`` records, per case and SDK, every answer that is *not* the
case's agreed answer -- each carrying the ticket that explains it -- plus every
SDK's answer to the cases that have no agreed answer. :func:`judge` holds an
observed result to it. Any difference fails the cell: a validator growing more
lenient and a divergence quietly disappearing are both news. :func:`problems`
checks the file itself, offline.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

from validity.contract import Outcome, ValidateResult

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

PATH = Path(__file__).parent / "baseline.json"

Ticket = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]+-\d+$")]


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


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Cell(_Strict):
    """One SDK's recorded answer to one case.

    In the file, a bare outcome string is a cell with nothing else to say.
    """

    outcome: Outcome
    #: Why this differs from the agreed answer. Required whenever it does.
    ticket: Ticket | None = None
    #: Where this SDK's rejection lands, when it is not the case's layer --
    #: Go reads a deflated manifest as JSON, say, rather than refusing the
    #: compression method.
    layer: Layer | None = None
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _bare_outcome(cls, raw: Any) -> Any:
        return {"outcome": raw} if isinstance(raw, str) else raw


class SdkBaseline(_Strict):
    #: Which build the answers were recorded from.
    source: str = ""
    #: Regex per layer, searched (case-insensitively) in this SDK's reason for
    #: an invalid verdict. Absent for an SDK whose reasons are not yet known.
    reason_patterns: dict[Layer, str] = {}

    @field_validator("reason_patterns")
    @classmethod
    def _compiles(cls, patterns: dict[Layer, str]) -> dict[Layer, str]:
        for layer, pattern in patterns.items():
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"{layer}: {e}") from e
        return patterns


class Baseline(_Strict):
    about: list[str] = []
    format: Literal[1]
    sdks: dict[str, SdkBaseline]
    #: case id -> SDK name -> cell.
    cells: dict[str, dict[str, Cell]] = {}

    def expected(self, spec: Spec, sdk: str) -> Cell | None:
        """What ``sdk`` should say about ``spec``.

        A recorded cell wins; otherwise the agreed answer. None for a case
        with no agreed answer that nobody has recorded for ``sdk``.
        """
        recorded = self.cells.get(spec.id, {}).get(sdk)
        if recorded is not None:
            return recorded
        if spec.expect in ("valid", "invalid"):
            return Cell(outcome=spec.expect)
        return None


def load(path: Path = PATH) -> Baseline:
    return Baseline.model_validate_json(path.read_bytes())


def problems(baseline: Baseline, specs: Iterable[Spec]) -> list[str]:
    """Everything wrong with ``baseline`` as a description of ``specs``.

    - a row for a case that does not exist;
    - a cell naming an SDK the baseline does not describe;
    - a cell that differs from its case's agreed answer without a ticket;
    - a cell that just repeats the agreed answer, with nothing to say;
    - an SDK with no recorded answer to a case that has no agreed one.
    """
    by_id = {s.id: s for s in specs}
    out = [
        f"{case_id}: baseline row for a case that is not in the corpus"
        for case_id in sorted(baseline.cells.keys() - by_id.keys())
    ]
    for case_id, row in sorted(baseline.cells.items()):
        spec = by_id.get(case_id)
        if spec is None:
            continue
        for sdk, cell in sorted(row.items()):
            if sdk not in baseline.sdks:
                out.append(f"{case_id}.{sdk}: no such SDK in the baseline")
            agreed = spec.expect in ("valid", "invalid")
            if agreed and cell.outcome == spec.expect and cell.layer is None:
                if not cell.note:
                    out.append(
                        f"{case_id}.{sdk}: repeats the agreed answer; delete the cell"
                    )
            elif spec.expect != "unspecified" and not (cell.ticket or spec.ticket):
                out.append(
                    f"{case_id}.{sdk}: {cell.outcome} differs from the agreed "
                    f"{spec.expect} without a ticket"
                )
    for spec in by_id.values():
        if spec.expect in ("valid", "invalid"):
            continue
        out += [
            f"{spec.id}.{sdk}: {spec.expect} case with no recorded answer for {sdk}"
            for sdk in sorted(baseline.sdks)
            if sdk not in baseline.cells.get(spec.id, {})
        ]
    return out


def judge(
    spec: Spec, sdk: str, build: str, result: ValidateResult, baseline: Baseline
) -> str | None:
    """Hold ``result`` to the baseline: None if it matches, else what differs
    and what to do about it."""
    cell = baseline.expected(spec, sdk)
    if result.outcome == "error" and (cell is None or cell.outcome != "error"):
        return f"{build} could not check {spec.id}: {result.reason}" + (
            f"\nstderr: {result.stderr}" if result.stderr else ""
        )
    said = f"{build} says {spec.id} is {result.outcome}" + (
        f" ({result.reason})" if result.reason else ""
    )
    if cell is None:
        return (
            f"{said}. The case has no agreed answer and validity/baseline.json "
            f"records none for {sdk}: add one."
        )
    if result.outcome != cell.outcome:
        ticket = cell.ticket or spec.ticket
        if cell.ticket and result.outcome == spec.expect:
            hint = (
                f"{cell.ticket} no longer reproduces here. If it is fixed, delete "
                "this cell from validity/baseline.json."
            )
        elif spec.expect in ("undecided", "unspecified"):
            hint = (
                "This case has no agreed answer, so the change itself is the "
                "finding: record the new answer in validity/baseline.json"
                + (f" and on {spec.ticket}." if spec.ticket else ".")
            )
        else:
            hint = (
                "A new divergence: file a ticket, and record the cell with it in "
                "validity/baseline.json."
            )
        return (
            f"{said}; the baseline says {cell.outcome}"
            + (f" ({ticket})" if ticket else "")
            + f" and the agreed answer is {spec.expect}. {hint}"
        )
    layer = cell.layer or spec.layer
    sb = baseline.sdks.get(sdk)
    pattern = sb.reason_patterns.get(layer) if sb and layer else None
    if (
        result.outcome == "invalid"
        and pattern
        and not re.search(pattern, result.reason, re.IGNORECASE)
    ):
        return (
            f"{build} rejected {spec.id}, but its reason does not look like a "
            f"{layer}-layer rejection (/{pattern}/): {result.reason!r}. A reader "
            "can reject at the wrong layer; if this one does, record the cell's "
            "layer with a ticket. If the CLI's wording changed instead, update "
            "reason_patterns."
        )
    return None
