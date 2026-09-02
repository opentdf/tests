"""The benchmark's experiment matrix.

Kept free of pytest and of ``tdfs`` so that both the conftest parametrizer and
the reporting layer can name a cell without importing each other.
"""

from __future__ import annotations

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
    """

    label: str
    n_bytes: int


PAYLOADS: tuple[Payload, ...] = (
    Payload("1KiB", 1024),
    Payload("1MiB", 2**20),
    Payload("32MiB", 32 * 2**20),
)

#: Payload used for the A/A control. Mid-size: large enough that startup noise
#: does not dominate it, small enough that the control is not a big slice of
#: the budget.
CONTROL_PAYLOAD = PAYLOADS[1]


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


def cells_for(sdks: list[str]) -> list[BenchCell]:
    """Build the full cell list for a run, each SDK's control cell first.

    One control per SDK rather than one per run: a control measures a
    particular SDK's harness path, and go's noise floor says nothing about
    java's.

    Controls run first because a run that overruns its time budget loses
    whatever is at the end. Losing one comparison leaves the rest
    trustworthy; losing the control leaves nothing trustworthy at all, since
    without a noise floor no cell may report PASS.
    """
    cells: list[BenchCell] = []
    for sdk in sdks:
        cells.append(BenchCell(sdk, "encrypt", CONTROL_PAYLOAD, control=True))
        cells += [
            BenchCell(sdk, op, payload)
            for op in ("encrypt", "decrypt")
            for payload in PAYLOADS
        ]
    return cells
