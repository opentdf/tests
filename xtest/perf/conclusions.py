"""What a multi-candidate run concluded about its candidates.

The gate answers "did any candidate get slower than the reference". This
module answers the other question a run with several candidates is asked:
"how do the candidates compare with each other, and is one of them the best".
It never changes the gate. A build must not go red because one candidate lost
to another.

Pairwise conclusions come first. Point-estimate order is not evidence: two
candidates whose ratios against the reference are 1.02 and 1.05 have not been
shown to differ unless their own contrast says so. A unique winner is named
only when it is supported against *every* other candidate, and never when the
run's control tripped.

Winner eligibility is decided here, once, from the analysed result. The JSON
artifact, the terminal line, and the markdown summary all read these objects,
so they cannot disagree about the conclusion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from perf import stats
from perf.runner import BenchConfig, CellResult, contrast_key


@dataclass(frozen=True, slots=True)
class Pairwise:
    """One candidate-to-candidate contrast, read as "``b`` vs ``a``"."""

    a: str
    b: str
    verdict: stats.Verdict
    ratio: float
    ci_low: float
    ci_high: float
    note: str

    def faster(self) -> str | None:
        """The arm shown to be faster, or None if neither was."""
        if self.verdict is stats.Verdict.FASTER:
            return self.b
        if self.verdict is stats.Verdict.SLOWER:
            return self.a
        return None


@dataclass(frozen=True, slots=True)
class Conclusion:
    """The candidates of one cell compared on one metric."""

    cell_id: str
    metric: str
    #: Arm id -> build label, for rendering.
    labels: dict[str, str]
    pairwise: tuple[Pairwise, ...]
    #: The candidate supported against every other, or None.
    winner: str | None
    #: Why there is or is not a winner, in one sentence.
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "cell": self.cell_id,
            "metric": self.metric,
            "pairwise": [
                {
                    "a": p.a,
                    "b": p.b,
                    "verdict": str(p.verdict),
                    "note": p.note,
                }
                for p in self.pairwise
            ],
            "winner": self.winner,
            "reason": self.reason,
        }


def conclude(
    results: Sequence[CellResult], config: BenchConfig, gate: stats.GateResult
) -> list[Conclusion]:
    """Compare the candidates of every cell that measured more than one.

    Empty for a two-arm run: one candidate has nothing to be compared with,
    and the gate has already said everything there is to say about it.
    """
    out: list[Conclusion] = []
    for r in results:
        if r.control or len(r.candidates) < 2:
            continue
        for metric in config.gated_metrics:
            pairwise = tuple(
                _pairwise(a, b, gate.comparisons[key])
                for a, b in r.contrast_pairs()
                if not r.is_reference_pair(a, b)
                and (key := contrast_key(r.cell_id, a, b, metric)) in gate.comparisons
            )
            winner, reason = _winner(r.candidates, pairwise, gate)
            out.append(
                Conclusion(
                    cell_id=r.cell_id,
                    metric=metric,
                    labels=dict(r.arm_labels),
                    pairwise=pairwise,
                    winner=winner,
                    reason=reason,
                )
            )
    return out


def _pairwise(a: str, b: str, c: stats.PairedComparison) -> Pairwise:
    return Pairwise(
        a=a,
        b=b,
        verdict=c.verdict,
        ratio=c.ratio,
        ci_low=c.ci_low,
        ci_high=c.ci_high,
        note=c.note,
    )


def _winner(
    candidates: Sequence[str], pairwise: Sequence[Pairwise], gate: stats.GateResult
) -> tuple[str | None, str]:
    """Name the candidate faster than every other, or say why there is none.

    Every requirement is checked, in an order that gives the most useful
    reason first:

    1. The control must not have tripped. A biased harness can produce a
       narrow, decisive-looking interval, so a tripped control suppresses the
       claim however clean the contrast looks.
    2. Some candidate must be shown FASTER than each of the others in its own
       contrast. Beating the runner-up is not enough when a third candidate's
       contrast is unresolved: that competitor may be the faster one.
    """
    if not gate.trustworthy:
        return None, (
            "no winner: the A/A control failed its own comparison, so no "
            "ranking from this run can be trusted"
        )
    beats: dict[str, set[str]] = {c: set() for c in candidates}
    for p in pairwise:
        faster = p.faster()
        if faster is not None:
            beats[faster].add(p.b if faster == p.a else p.a)
    for c in candidates:
        if beats[c] == set(candidates) - {c}:
            return c, f"faster than every other candidate ({len(candidates) - 1})"

    ties = [p for p in pairwise if p.verdict is stats.Verdict.TIED]
    unresolved = [p for p in pairwise if p.verdict is stats.Verdict.INCONCLUSIVE]
    if unresolved:
        p = unresolved[0]
        return None, (
            f"no winner: `{p.b}` vs `{p.a}` is unresolved"
            + (f" ({p.note})" if p.note else "")
        )
    if ties:
        p = ties[0]
        return None, f"no winner: `{p.a}` and `{p.b}` are tied"
    return None, "no winner: no candidate is faster than every other"
