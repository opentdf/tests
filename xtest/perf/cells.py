"""The benchmark's experiment matrix.

Kept free of pytest and of ``tdfs`` so that both the conftest parametrizer and
the reporting layer can name a cell without importing each other.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

operation_type = Literal["encrypt", "decrypt"]


@dataclass(frozen=True, slots=True)
class Payload:
    """One payload size regime.

    The sizes separate two failure modes that hide each other. At 1 KiB
    essentially all the cost is process startup -- JVM boot, npx resolution,
    TLS handshake, token fetch -- so a throughput regression is invisible. At
    32 MiB the crypto and IO dominate and a startup regression is invisible.
    A benchmark at one size only will miss half the regressions it claims to
    cover.

    "Dominate" is relative, and at 32 MiB it is not yet true. On a 4-core
    Linux runner a go encrypt costs ~450 ms of fixed startup against ~72 ms
    that scales with the payload, so payload work is ~14% of the cell and the
    default 1.15x gate is wider than the whole of it -- a candidate that
    doubled every per-segment cost would still report PASS. Gating throughput
    needs a size where the ratio inverts, which is what ``--bench-payloads``
    is for: at 1 GiB the payload term is ~2.3 s against the same ~450 ms.
    """

    label: str
    n_bytes: int


#: Binary units only. A label is a filename and a cell id, and "1MB" sitting
#: next to "1MiB" in a report is a misreading waiting to happen.
_UNITS: tuple[tuple[str, int], ...] = (
    ("B", 1),
    ("KiB", 2**10),
    ("MiB", 2**20),
    ("GiB", 2**30),
)

_SIZE_RE = re.compile(r"^\s*(\d+)\s*([a-z]+)\s*$", re.IGNORECASE)


def parse_payload(spec: str) -> Payload:
    """Parse one size spec, e.g. ``"32MiB"``, into a :class:`Payload`.

    The unit is matched case-insensitively but the label is rebuilt from the
    canonical spelling, so ``"1gib"`` and ``"1GiB"`` name the same cell rather
    than two cells that measure the same thing under different ids.
    """
    match = _SIZE_RE.match(spec)
    units = {name.lower(): (name, mult) for name, mult in _UNITS}
    if match is None or match.group(2).lower() not in units:
        raise ValueError(
            f"{spec!r} is not a payload size; expected a count and one of "
            f"{', '.join(name for name, _ in _UNITS)}, e.g. '32MiB'"
        )
    count = int(match.group(1))
    name, multiplier = units[match.group(2).lower()]
    if count <= 0:
        raise ValueError(f"{spec!r} is not a payload size; it must be above zero")
    return Payload(f"{count}{name}", count * multiplier)


def parse_payloads(spec: str) -> tuple[Payload, ...]:
    """Parse a comma-separated size list into the run's payload set.

    Sorted ascending and deduplicated *by byte count*, not by label: ``1024B``
    and ``1KiB`` are one size written two ways, and admitting both would run
    two identically-sized cells whose only difference is the id in the report.
    """
    by_size: dict[int, Payload] = {}
    for part in spec.split(","):
        if not part.strip():
            continue
        payload = parse_payload(part)
        by_size.setdefault(payload.n_bytes, payload)
    if not by_size:
        raise ValueError("no payload sizes given")
    return tuple(by_size[n] for n in sorted(by_size))


#: What a run measures unless ``--bench-payloads`` says otherwise. Anything
#: larger is opt-in: a 1 GiB cell costs minutes of budget and gigabytes of
#: scratch disk, which a nightly should not spend without being asked.
DEFAULT_PAYLOAD_SPEC = "1KiB,1MiB,32MiB"

PAYLOADS: tuple[Payload, ...] = parse_payloads(DEFAULT_PAYLOAD_SPEC)

#: Payload used for the A/A control. Mid-size: large enough that startup noise
#: does not dominate it, small enough that the control is not a big slice of
#: the budget.
#:
#: Fixed rather than picked out of the selected set, because the control's
#: reported width *is* the run's noise floor and every other cell is judged
#: against it. Letting it follow ``--bench-payloads`` would move the floor
#: whenever the matrix changed, so two runs of the same comparison could
#: disagree about which cells were trustworthy for a reason that has nothing
#: to do with either build.
CONTROL_PAYLOAD = Payload("1MiB", 2**20)


def payloads_to_generate(payloads: Sequence[Payload]) -> tuple[Payload, ...]:
    """Every payload file a run needs, including the control's.

    The control's size need not be in the selected set -- ``--bench-payloads
    1GiB`` is a legitimate ask -- but its file is still required, and a
    missing one surfaces as a KeyError deep in arm construction.
    """
    by_label = {p.label: p for p in (*payloads, CONTROL_PAYLOAD)}
    return tuple(sorted(by_label.values(), key=lambda p: p.n_bytes))


@dataclass(frozen=True, slots=True)
class BenchCell:
    """One comparison: an operation at a payload size, for one SDK."""

    sdk: str
    operation: operation_type
    payload: Payload
    #: A/A control -- the same build in both arms, through the same pipeline.
    #: Its true ratio is 1.0 by construction, so whatever it reports is the
    #: harness's own error.
    control: bool = False

    @property
    def id(self) -> str:
        suffix = "-control" if self.control else ""
        return f"{self.sdk}-{self.operation}-{self.payload.label}{suffix}"

    def __str__(self) -> str:
        return self.id


def cells_for(
    sdks: list[str], payloads: Sequence[Payload] = PAYLOADS
) -> list[BenchCell]:
    """Build the full cell list for a run, each SDK's control cell first.

    One control per SDK rather than one per run: a control measures a
    particular SDK's harness path, and go's noise floor says nothing about
    java's.

    Controls run first because a run that overruns its time budget loses
    whatever is at the end. Losing one comparison leaves the rest
    trustworthy; losing the control leaves nothing trustworthy at all, since
    without a noise floor no cell may report PASS.

    Within an SDK the payloads run smallest first, so that when the budget
    does run out it is the most expensive cell that is lost rather than an
    arbitrary one.
    """
    cells: list[BenchCell] = []
    for sdk in sdks:
        cells.append(BenchCell(sdk, "encrypt", CONTROL_PAYLOAD, control=True))
        cells += [
            BenchCell(sdk, op, payload)
            for payload in payloads
            for op in ("encrypt", "decrypt")
        ]
    return cells
