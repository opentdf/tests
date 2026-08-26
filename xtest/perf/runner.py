"""The paired round loop that produces comparable samples for one cell.

A *cell* is one operation at one payload size, measured for K SDK builds
(2 to 4). The loop runs every arm once per round, in a randomized order, until
it has either enough precision or no more time.

Why rounds rather than "run A 30 times, then B 30 times"
--------------------------------------------------------
A shared runner drifts: a noisy neighbour arrives, the CPU thermally throttles,
the page cache warms. Run all of A and then all of B and every one of those
effects lands entirely on one arm and shows up as a difference between builds.
Interleaving means every arm sees the same conditions within a round, and the
per-round ratio differences it out.

The order *within* a round is randomized because a fixed order is itself a
confounder -- whichever arm runs second inherits the first one's cache state.

Why every arm shares a round, and why that is the whole point at K > 2
----------------------------------------------------------------------
Because all K arms are measured in the same round on the same runner, *every*
pairwise contrast is a within-run ratio -- not just each candidate against the
reference, but candidate-against-candidate too. That is what makes a bake-off
between two competing implementations answerable at all. Running them as two
separate 2-arm jobs puts them on different runners, and this harness's founding
premise is that timings from different runners are not comparable.

Why stopping on precision and not on significance
-------------------------------------------------
The loop stops when the confidence interval is narrow enough, never when the
p-value gets small. Peeking at the p-value and stopping the moment it drops
below alpha is optional stopping: it inflates the false-positive rate well
past the nominal level, because you get a fresh chance to cross the line every
round and only ever stop on the lucky side. Attained CI width, in contrast, is
driven by the dispersion of the differences rather than their location, so it
is approximately ancillary to the effect being tested and stopping on it does
not bias the verdict.

This distinction is easy to "optimize away" -- stopping on significance would
finish sooner -- and doing so silently invalidates every result the job
produces. Do not.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from perf import stats
from perf.measure import METRICS, MeasurementError, Sample, measure

#: Target CI half-width on the log scale, as a fraction of the log threshold.
#: At 1/3, an interval centred on "no change" is comfortably clear of the
#: threshold, so a PASS is a real statement about precision rather than a
#: shrug. Tighter costs rounds superlinearly; looser makes PASS meaningless.
PRECISION_FRACTION = 1 / 3

#: Bootstrap resamples for the between-round precision check. Far fewer than
#: the final analysis uses: this only needs to answer "is the interval roughly
#: narrow enough yet", and it runs after every round.
_INTERIM_RESAMPLES = 1000

#: The A/A control metric that assesses an SDK's noise floor. Wall clock is
#: the most sensitive of the gated metrics to runner noise, which makes it the
#: honest choice of canary.
_CONTROL_METRIC = "wall"


class BudgetExhausted(RuntimeError):
    """The time budget ran out before the cell could collect usable rounds."""


@dataclass(frozen=True, slots=True)
class BenchConfig:
    """Knobs for the round loop and the analysis that follows it."""

    min_rounds: int = 20
    max_rounds: int = 60
    warmup: int = 5
    budget_seconds: float = 1500.0
    seed: int = 0
    threshold: float = stats.DEFAULT_THRESHOLD
    confidence: float = 0.95
    n_resamples: int = stats.DEFAULT_BOOTSTRAP_RESAMPLES
    #: Per-invocation timeout. A wedged CLI must not eat the whole job.
    timeout_s: float = 600.0
    #: Metrics whose verdict can fail the build. CPU time is measured and
    #: reported but excluded: it is the noisiest of the three on a shared
    #: runner, and a real CPU regression shows up in wall clock anyway.
    gated_metrics: tuple[str, ...] = ("wall", "rss")

    def __post_init__(self) -> None:
        if self.min_rounds < stats.MIN_USABLE_ROUNDS:
            raise ValueError(
                f"min_rounds must be at least {stats.MIN_USABLE_ROUNDS}, "
                f"below which no verdict is possible"
            )
        if self.max_rounds < self.min_rounds:
            raise ValueError("max_rounds must not be below min_rounds")
        if self.warmup < 0:
            raise ValueError("warmup must not be negative")
        if self.threshold <= 1.0:
            raise ValueError("threshold is a ratio above 1.0, e.g. 1.15 for 15%")
        unknown = set(self.gated_metrics) - set(METRICS)
        if unknown:
            raise ValueError(f"unknown gated metrics: {sorted(unknown)}")

    @property
    def target_half_width_log(self) -> float:
        """CI half-width, on the log scale, that ends the round loop."""
        return float(np.log(self.threshold)) * PRECISION_FRACTION


@dataclass(frozen=True, slots=True)
class Invocation:
    """One fully-built CLI call, ready to run repeatedly."""

    argv: list[str]
    #: CLI-specific overrides, merged over ``os.environ`` at run time.
    env: dict[str, str] = field(default_factory=dict)
    #: Removed before each measured run, so every round starts from the same
    #: state rather than measuring an overwrite in round 2 onwards.
    output: Path | None = None

    def child_env(self) -> dict[str, str]:
        return dict(os.environ) | self.env


@dataclass(frozen=True, slots=True)
class Arm:
    """One build participating in a cell.

    At K > 2 there is no such thing as "the candidate", so arms are keyed by
    identity rather than by role: ``name`` is the arm id, and which arm is the
    reference is a property of the cell, not of the arm.
    """

    #: Arm id, unique within a cell -- the flattened dist tag, e.g. ``"main"``
    #: or ``"fix--otdfctl-streaming-encrypt-writer"``.
    name: str
    #: The build this arm runs, e.g. ``"go@v0.29.0"``.
    label: str
    invocation: Invocation


@dataclass(slots=True)
class CellResult:
    """Everything one cell measured, before any verdict is assigned.

    Raw per-round vectors are kept in full. Re-analysing a surprising result
    offline is the difference between understanding a red build and re-running
    a 30-minute job to look at it again.
    """

    cell_id: str
    #: Arm ids in the order they were configured. ``arm_ids[0]`` is the
    #: reference by convention, and ``reference`` names it explicitly.
    arm_ids: tuple[str, ...]
    #: Arm id -> the build it ran, e.g. ``"go@v0.29.0"``.
    arm_labels: dict[str, str]
    reference: str
    #: ``samples[arm_id][metric]`` is the per-round vector, warm-up excluded.
    samples: dict[str, dict[str, list[float]]]
    n_warmup: int
    elapsed_s: float
    stopped_because: str
    #: True for the A/A control, where every arm is the same build.
    control: bool = False
    #: Which SDK's control cell assesses this cell's noise floor. A run may
    #: measure several SDKs, and each has its own harness path and its own
    #: floor; go's says nothing about java's.
    sdk: str = ""
    #: Highest measurement floor seen in this cell -- the RSS of the process
    #: that forked each invocation. See :mod:`perf._launcher`.
    rss_floor_bytes: int = 0

    @property
    def baseline_label(self) -> str:
        """The reference build's label.

        Kept alongside :attr:`candidate_label` so that the two-arm shape of the
        JSON artifact -- which predates K arms and which people have scripts
        pointed at -- still reads correctly for a two-arm run.
        """
        return self.arm_labels[self.reference]

    @property
    def candidate_label(self) -> str:
        """The second arm's build label; see :attr:`baseline_label`.

        At K > 2 this is one candidate among several and says nothing about the
        rest, which is why the artifact also carries the full ``arm_labels``.
        """
        others = [a for a in self.arm_ids if a != self.reference]
        return self.arm_labels[others[0]] if others else self.baseline_label

    @property
    def rss_censored_reason(self) -> str | None:
        """Why this cell's peak RSS cannot be compared, or None if it can.

        A command whose peak sits at the floor was not measured, it was
        clipped, and every arm clips to the same value. The resulting ratio is
        1.000 with a tight interval, which is the most convincing-looking
        PASS the harness can emit and means nothing at all.
        """
        if self.rss_floor_bytes <= 0:
            return None
        rss = [v for arm in self.samples.values() for v in arm.get("rss", [])]
        if not rss or min(rss) > self.rss_floor_bytes:
            return None
        return (
            f"peak rss reaches the {self.rss_floor_bytes / 2**20:.0f} MiB "
            "measurement floor, so the arms are not distinguishable"
        )

    @property
    def n_rounds(self) -> int:
        first = next(iter(self.samples.values()), {})
        return len(next(iter(first.values()), []))

    def contrast(
        self, a: str, b: str, metric: str, config: BenchConfig
    ) -> stats.PairedComparison:
        """Compare arm ``b`` against arm ``a`` -- a ratio of b over a.

        The argument order matches the reading of the result:
        ``contrast(reference, candidate, ...)`` answers "how much slower is the
        candidate than the reference", which is the direction every ratio in
        the report is quoted in.
        """
        return stats.compare(
            self.samples[a][metric],
            self.samples[b][metric],
            confidence=config.confidence,
            seed=config.seed,
            n_resamples=config.n_resamples,
        )

    def contrast_pairs(self) -> list[tuple[str, str]]:
        """Every ordered ``(a, b)`` pair to report, reference contrasts first.

        Reference contrasts are quoted as ``(reference, candidate)`` so they
        read as "candidate vs reference". Head-to-head pairs are emitted in
        configured order, once each -- a pair and its inverse are the same
        measurement read two ways, and reporting both would double-count it in
        the multiplicity correction.
        """
        others = [a for a in self.arm_ids if a != self.reference]
        pairs = [(self.reference, b) for b in others]
        pairs += [(a, b) for i, a in enumerate(others) for b in others[i + 1 :]]
        return pairs


def contrast_key(cell_id: str, a: str, b: str, metric: str) -> str:
    """The stable key for one contrast, as used throughout the analysis."""
    return f"{cell_id}/{b}_vs_{a}/{metric}"


def _empty_samples(arm_ids: Sequence[str]) -> dict[str, dict[str, list[float]]]:
    return {arm: {m: [] for m in METRICS} for arm in arm_ids}


def run_cell(
    cell_id: str,
    arms: Sequence[Arm],
    config: BenchConfig,
    *,
    reference: str | None = None,
    deadline: float | None = None,
    control: bool = False,
    sdk: str = "",
    clock: Callable[[], float] = time.monotonic,
    run: Callable[..., Sample] = measure,
) -> CellResult:
    """Run one cell's paired rounds and return its raw samples.

    Args:
        cell_id: stable identifier, also the per-cell RNG seed material so
            that two cells do not share an interleaving order.
        arms: the 2 to 4 builds to measure, all in every round. For an A/A
            control these are the same build running through identical paths.
        config: round-loop knobs.
        reference: id of the arm every gated contrast is taken against;
            defaults to ``arms[0]``.
        deadline: absolute ``clock()`` value past which no new round starts.
        control: records that this is the A/A cell; does not change the loop.
        sdk: which SDK this cell belongs to, so that the analysis can pair it
            with the right control. Only matters in a multi-SDK run.
        clock: injectable monotonic clock.
        run: injectable measurement function, for testing the loop itself.

    Raises:
        ValueError: if fewer than two arms were given, or their ids collide.
        MeasurementError: if any invocation fails. A benchmark over an
            operation that errors out is measuring the error path.
        BudgetExhausted: if the deadline passed before ``min_rounds``, or
            during warm-up.
    """
    arms = tuple(arms)
    if len(arms) < 2:
        raise ValueError(f"{cell_id}: a cell needs at least two arms to compare")
    arm_ids = tuple(a.name for a in arms)
    if len(set(arm_ids)) != len(arm_ids):
        # Ids key the sample vectors, so a collision would silently interleave
        # two builds' measurements into one arm and compare it with itself.
        raise ValueError(f"{cell_id}: arm ids must be unique, got {list(arm_ids)}")
    reference = arm_ids[0] if reference is None else reference
    if reference not in arm_ids:
        raise ValueError(f"{cell_id}: reference {reference!r} is not one of the arms")

    # Seeded per cell so a rerun reproduces the interleaving exactly, but the
    # cells do not all share one order (which would correlate their noise).
    rng = random.Random(f"{config.seed}:{cell_id}")
    samples = _empty_samples(arm_ids)
    round_durations: list[float] = []
    rss_floor = 0
    started = clock()

    def one_round(into: dict[str, dict[str, list[float]]]) -> None:
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            inv = arm.invocation
            if inv.output is not None:
                inv.output.unlink(missing_ok=True)
            try:
                sample = run(inv.argv, inv.child_env(), timeout_s=config.timeout_s)
            except MeasurementError as e:
                raise MeasurementError(f"{cell_id}: {arm.label} failed: {e}") from e
            nonlocal rss_floor
            rss_floor = max(rss_floor, sample.rss_floor_bytes)
            for metric in METRICS:
                into[arm.name][metric].append(sample.metric(metric))

    try:
        for i in range(config.warmup):
            # Warm-up rounds pay the one-time costs -- page cache, `go build`
            # cache, npx package resolution, JIT warm-up -- that would
            # otherwise land unevenly and show up as a difference between
            # builds. Their samples are collected into a throwaway dict and
            # dropped.
            #
            # The deadline is checked here too, and not only in the measured
            # loop below. The budget's end is absolute, so warm-ups that
            # overrun it spend the *following* cells' time and then reach the
            # measured loop with nothing left -- paying the full cost of the
            # cell and producing no data. Better to give up here and say why.
            if deadline is not None and clock() >= deadline:
                raise BudgetExhausted(
                    f"{cell_id}: budget ran out after {i} of {config.warmup} "
                    f"warm-up rounds ({clock() - started:.0f}s), "
                    "before any measurement began"
                )
            one_round(_empty_samples(arm_ids))

        stopped_because = "max_rounds"
        for _ in range(config.max_rounds):
            round_start = clock()
            if deadline is not None and round_start >= deadline:
                stopped_because = "budget"
                break
            if deadline is not None and round_durations:
                # Do not start a round we cannot finish: a half-measured round
                # is unpaired data, and unpaired data is exactly what this
                # design exists to avoid.
                expected = float(np.median(round_durations))
                if round_start + expected > deadline:
                    stopped_because = "budget"
                    break
            one_round(samples)
            round_durations.append(clock() - round_start)

            n = len(samples[reference]["wall"])
            if n >= config.min_rounds and _precise_enough(
                samples, config, reference=reference
            ):
                stopped_because = "precision"
                break

        elapsed = clock() - started
        n = len(samples[reference]["wall"])
        if n < stats.MIN_USABLE_ROUNDS:
            raise BudgetExhausted(
                f"{cell_id}: only {n} rounds completed in {elapsed:.0f}s, "
                f"below the {stats.MIN_USABLE_ROUNDS} needed for any verdict"
            )
        return CellResult(
            cell_id=cell_id,
            arm_ids=arm_ids,
            arm_labels={a.name: a.label for a in arms},
            reference=reference,
            samples=samples,
            n_warmup=config.warmup,
            elapsed_s=elapsed,
            stopped_because=stopped_because,
            control=control,
            sdk=sdk,
            rss_floor_bytes=rss_floor,
        )
    finally:
        # Each arm leaves behind an output the size of the payload, and
        # nothing reads it once the cell is done. Keeping them costs K GiB per
        # 1 GiB cell, which every later cell then has to fit around -- so the
        # cell that fails on disk is not the one that filled it.
        for arm in arms:
            if arm.invocation.output is not None:
                arm.invocation.output.unlink(missing_ok=True)


def _precise_enough(
    samples: dict[str, dict[str, list[float]]],
    config: BenchConfig,
    *,
    reference: str,
) -> bool:
    """True once every gated contrast's CI is narrow enough to decide on.

    Every non-reference arm must be resolved on every gated metric, not just
    the first one: stopping as soon as *some* contrast is precise would leave
    the rest INCONCLUSIVE while the budget was still there to spend on them,
    and at K arms the slowest contrast to converge is the one that matters.

    Deliberately looks only at interval *width*, never at where the interval
    sits or at any p-value -- see the module docstring.
    """
    for metric in config.gated_metrics:
        for arm, vectors in samples.items():
            if arm == reference:
                continue
            c = stats.compare(
                samples[reference][metric],
                vectors[metric],
                confidence=config.confidence,
                seed=config.seed,
                n_resamples=_INTERIM_RESAMPLES,
            )
            # `not (a <= b)` rather than `a > b`, which is not the same thing
            # when a is NaN: an unusable interval must read as "keep going",
            # and `NaN > b` is False, which would end the loop and call it
            # precise.
            if not c.ci_half_width_log <= config.target_half_width_log:  # NOSONAR
                return False
    return True


class Budget:
    """Shares one wall-clock allowance across a run's cells.

    Cells are measured one at a time, so a cell that stops early on precision
    should hand its unused time to the cells after it rather than letting the
    last cell get squeezed by whatever the first ones happened to use.
    """

    def __init__(
        self,
        total_seconds: float,
        n_cells: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if n_cells <= 0:
            raise ValueError("a budget needs at least one cell to divide across")
        self._clock = clock
        self._end = clock() + total_seconds
        self._cells_left = n_cells

    def next_deadline(self) -> float:
        """Absolute deadline for the next cell: an even share of what is left."""
        now = self._clock()
        share = max(0.0, self._end - now) / max(1, self._cells_left)
        self._cells_left = max(0, self._cells_left - 1)
        return now + share

    @property
    def remaining_s(self) -> float:
        return max(0.0, self._end - self._clock())


def analyze(results: Sequence[CellResult], config: BenchConfig) -> stats.GateResult:
    """Turn every cell's raw samples into one gate decision.

    ``GateResult.comparisons`` is keyed by ``"<cell_id>/<b>_vs_<a>/<metric>"``
    and holds the *finalized* comparisons -- the ones carrying adjusted
    p-values and verdicts. Every pairwise contrast in every cell is here, but
    they fall into three groups that are judged and corrected separately:

    - **Gated**: a non-reference arm against the reference, on a gated metric.
      One-sided; only these can fail the build. At K arms there are K-1 of
      them per cell and metric rather than one.
    - **Symmetric**: a head-to-head between two non-reference arms -- the
      bake-off question. Judged two-sided against an equivalence band, ranked
      and reported, never gated. See invariant #9 in ``README.md``.
    - **Ungated**: everything else, reported for context only.

    They get separate BH families for the reason documented in
    :func:`stats.apply_multiplicity_control`: adjusting the gate against tests
    nobody gates on only makes a real regression harder to confirm. A bake-off
    is a question of interest, not a build gate, so it must not dilute the
    gate either.

    Each SDK's cells are paired with *that SDK's* control. A run measuring go
    and java has two harness paths and two noise floors, and judging java's
    cells against go's control would be judging them against a floor that was
    never measured for them.
    """
    comparisons: dict[str, stats.PairedComparison] = {}
    gated: set[str] = set()
    symmetric: set[str] = set()
    censored: dict[str, str] = {}
    control_keys: set[str] = set()
    controls: dict[str, str] = {}

    for result in results:
        floored = result.rss_censored_reason
        for a, b in result.contrast_pairs():
            head_to_head = result.reference not in (a, b)
            for metric in METRICS:
                key = contrast_key(result.cell_id, a, b, metric)
                comparisons[key] = result.contrast(a, b, metric, config)
                if metric == "rss" and floored is not None:
                    censored[key] = floored
                    continue
                if result.control:
                    control_keys.add(key)
                elif head_to_head:
                    # Every head-to-head is judged symmetrically, on gated and
                    # ungated metrics alike: "which arm is faster" has no
                    # privileged direction, and the one-sided PASS/REGRESSION
                    # vocabulary would misdescribe it. None of them gate, so
                    # sharing one BH family costs the gate nothing -- the
                    # separation that matters is keeping them *out* of it.
                    symmetric.add(key)
                elif metric in config.gated_metrics:
                    gated.add(key)

    # Pick each SDK's noise floor only once every control contrast exists: a
    # K-arm control produces C(K,2) of them and the worst one is the floor.
    assessor_for_sdk = {
        r.sdk: stats.worst_control_key(
            comparisons,
            [
                contrast_key(r.cell_id, a, b, _CONTROL_METRIC)
                for a, b in r.contrast_pairs()
            ],
            threshold=config.threshold,
        )
        for r in results
        if r.control
    }
    for result in results:
        assessor = assessor_for_sdk.get(result.sdk)
        if assessor is None:
            continue
        for a, b in result.contrast_pairs():
            for metric in METRICS:
                controls[contrast_key(result.cell_id, a, b, metric)] = assessor

    return stats.apply_multiplicity_control(
        comparisons,
        gated=gated,
        symmetric=symmetric,
        controls=controls,
        control_keys=control_keys,
        censored=censored,
        threshold=config.threshold,
        alpha=stats.DEFAULT_ALPHA,
    )
