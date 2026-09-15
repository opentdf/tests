"""Feature gates as data, and the one evaluator that reads them.

A capability question -- "can this build do ``ecwrap``?" -- has exactly three
honest answers today, and each is currently written out longhand, in bash,
once per SDK per feature:

* a version comparison, hand-rolled in awk
  (``--version --json | jq -re .sdk_version | awk -F. '{ if ($1 > 0 ||
  ($1 == 0 && $2 >= 12)) exit 0; else exit 1; }'``, with the boundary
  expression rewritten from scratch each time);
* a help-text probe (``help decrypt | grep kas-allowlist``);
* a constant, with a comment explaining why.

Two more answers exist but had no vocabulary, so they were spelled as
constants: an SDK that answers natively (java ships ``cmdline.jar supports
dpop``), and a capability with no CLI surface at all, which every shim reports
as a bare ``exit 1`` indistinguishable from "this build is too old".

This module names those five shapes and evaluates them once. A gate is inert
data: it has no opinion about how to run a subprocess, which is what makes it
testable without an SDK installed and what lets the tables live next to the
adapter that answers them.

The tables themselves are deliberately **not** here yet. Populating them means
transcribing ~50 case arms, and transcribing them is where the mistakes are;
that is its own reviewable change. What lands here is the vocabulary and the
evaluator, so the transcription has something to be reviewed against.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from packaging.version import InvalidVersion, Version

from otdf_adapter.protocol import SdkVersion

logger = logging.getLogger("otdf_adapter.gates")

#: Which reported version a :class:`MinVersion` compares against. An SDK's own
#: version and the container-schema version it writes move independently --
#: ``hexless`` is a question about the schema, ``ecwrap`` about the SDK.
VersionField = Literal["sdk", "schema"]


@dataclass(frozen=True)
class MinVersion:
    """Supported from ``minimum`` onwards, per the SDK's self-reported version.

    Replaces the awk one-liners. Those encode the same comparison ~15 times
    with divergent expressions, which is how ``$2 >= 2`` ended up sitting
    under a comment that says 4.3.0: when the boundary is an expression rather
    than a value, nothing can check it against its own documentation.

    A build whose version does not parse -- every branch build -- answers
    ``False``, which is what the awk pipelines already do by way of ``jq``
    failing and ``set -o pipefail``. That is also why ``XT_FORCE_SUPPORTS``
    exists.
    """

    minimum: str
    field: VersionField = "sdk"
    reason: str = ""


@dataclass(frozen=True)
class HelpContains:
    """Supported if the SDK's help output for ``subcommand`` contains ``needle``.

    A capability probe rather than a version guess, and so correct for branch
    builds -- but only for capabilities that add a flag. It says nothing about
    whether the flag works.
    """

    subcommand: Sequence[str] = ()
    needle: str = ""
    ignore_case: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "subcommand", tuple(self.subcommand))


@dataclass(frozen=True)
class Always:
    """A constant answer, with the reason attached rather than in a comment.

    ``Always(False)`` and :class:`Unprobeable` both currently compile to
    ``exit 1``, which is the problem: "too old" and "unanswerable" are
    different facts and a reader cannot tell them apart.
    """

    answer: bool
    reason: str = ""


@dataclass(frozen=True)
class Delegate:
    """The SDK answers for itself: ``<cli> supports <feature>``.

    The right answer whenever an SDK is willing to give one, because it moves
    the fact into the repo that owns it. java already does this for ``dpop``;
    the rest of the table is this repo asserting things about other people's
    code.
    """

    #: Feature name to pass through, when the SDK spells it differently.
    feature: str | None = None


@dataclass(frozen=True)
class Unprobeable:
    """No CLI surface exists to ask. Answers ``False``, and says why.

    For behaviour that lives below the command line -- a validation step that
    runs after a key unwrap adds no flag, no subcommand and no version field.
    The test that covers it has to provoke the behaviour and watch, and this
    gate's job is to make the resulting skip legible instead of looking like a
    stale version bound.
    """

    reason: str


Gate = MinVersion | HelpContains | Always | Delegate | Unprobeable

#: ``{sdk: {feature: Gate}}``. Empty until the tables are transcribed from
#: ``sdk/{go,java,js}/cli.sh``; ``evaluate`` treats a missing entry as
#: unknown and the caller falls back to the shim, so an empty table is
#: exactly today's behaviour.
GATES: dict[str, dict[str, Gate]] = {}


class GateContext(Protocol):
    """What an evaluator needs from an adapter, and nothing more.

    Narrow on purpose: a gate table can be exercised against a stub in a unit
    test with no SDK installed, which is the only way ~50 transcribed
    comparisons ever get checked.
    """

    def version(self) -> SdkVersion:
        """What the build reports about itself."""
        ...

    def help_text(self, *subcommand: str) -> str:
        """Help output for ``subcommand``; empty string if it cannot be read."""
        ...

    def ask_native(self, feature: str) -> bool:
        """Ask the SDK's own ``supports`` verb."""
        ...


@dataclass(frozen=True)
class GateResult:
    """The verdict plus why, so a skip message can explain itself."""

    supported: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.supported


def _reported(version: SdkVersion, which: VersionField) -> str | None:
    return version.sdk if which == "sdk" else version.schema


def evaluate(gate: Gate, ctx: GateContext, feature: str = "") -> GateResult:
    """Answer one gate against one build."""
    if isinstance(gate, Always):
        return GateResult(gate.answer, gate.reason)

    if isinstance(gate, Unprobeable):
        return GateResult(False, gate.reason)

    if isinstance(gate, Delegate):
        name = gate.feature or feature
        return GateResult(ctx.ask_native(name), f"{name} delegated to the SDK")

    if isinstance(gate, HelpContains):
        haystack = ctx.help_text(*gate.subcommand)
        needle = gate.needle
        if gate.ignore_case:
            haystack, needle = haystack.lower(), needle.lower()
        found = needle in haystack
        where = " ".join(("help", *gate.subcommand)).strip()
        return GateResult(found, f"{gate.needle!r} {'in' if found else 'absent from'} {where}")

    reported = _reported(ctx.version(), gate.field)
    if reported is None:
        return GateResult(False, f"build reports no parseable {gate.field} version")
    try:
        actual, minimum = Version(reported), Version(gate.minimum)
    except InvalidVersion:
        return GateResult(False, f"{gate.field} version {reported!r} does not parse")
    ok = actual >= minimum
    detail = f"{gate.field} {reported} {'>=' if ok else '<'} {gate.minimum}"
    return GateResult(ok, f"{detail}{'; ' + gate.reason if gate.reason else ''}")


def lookup(sdk: str, feature: str, tables: dict[str, dict[str, Gate]] | None = None) -> Gate | None:
    """The gate for ``(sdk, feature)``, or ``None`` if the table has no opinion."""
    return (tables if tables is not None else GATES).get(sdk, {}).get(feature)


@dataclass(frozen=True)
class GateTable:
    """One SDK's gates, so a consumer can register a table without mutating GATES."""

    sdk: str
    gates: dict[str, Gate] = field(default_factory=dict)

    def evaluate(self, feature: str, ctx: GateContext) -> GateResult | None:
        gate = self.gates.get(feature)
        if gate is None:
            return None
        return evaluate(gate, ctx, feature)
