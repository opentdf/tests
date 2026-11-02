"""The paired round loop that produces comparable samples for one cell.

A *cell* is one operation at one payload size, measured over two or more
arms: distinct SDK builds, or, in the A/A control, copies of one build. The
loop runs every arm once per round, in a randomized order, until it has
either enough precision or no more time. The first arm is the *reference*,
and every other arm is compared against it.

Why rounds rather than "run A 30 times, then B 30 times"
--------------------------------------------------------
A shared runner drifts: a noisy neighbour arrives, the CPU thermally throttles,
the page cache warms. Run all of A and then all of B and every one of those
effects lands entirely on one arm and shows up as a difference between builds.
Interleaving means every arm sees the same conditions within a round, and the
per-round ratio differences it out. A round is recorded only once every arm
in it has completed, so the vectors stay paired however many arms there are.

The order *within* a round is randomized because a fixed order is itself a
confounder -- whichever arm runs second inherits the first one's cache state.

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

# BenchConfig lives in `perf.config`, which the CI adapter and the local
# entry point can import without dragging in the measurement stack. It is
# imported (not redefined) here because this is where callers look for the
# round loop's settings.
from perf.config import BenchConfig
from perf.measure import METRICS, MeasurementError, Sample, measure

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
    """One build in a cell. Which arm is the reference belongs to the cell."""

    #: Arm id, unique within a cell: it keys the samples. ``build_arms`` uses
    #: the dist directory name, e.g. ``"v0.29.0"``, or ``"v0.29.0#1"`` for a
    #: control copy.
    name: str
    #: The build this arm runs, e.g. ``"go@v0.29.0"``.
    label: str
    invocation: Invocation


def _check_arm_ids(cell_id: str, arm_ids: Sequence[str]) -> None:
    """Reject fewer than two arms, or colliding ids (which would merge samples)."""
    if len(arm_ids) < 2:
        raise ValueError(f"{cell_id}: a cell needs at least two arms to compare")
    if len(set(arm_ids)) != len(arm_ids):
        raise ValueError(f"{cell_id}: arm ids must be unique, got {list(arm_ids)}")


@dataclass(frozen=True, slots=True)
class CellResult:
    """Everything one cell measured, before any verdict is assigned.

    Raw per-round vectors are kept in full. Re-analysing a surprising result
    offline is the difference between understanding a red build and re-running
    a 30-minute job to look at it again.
    """

    cell_id: str
    #: Arm ids in the order they were configured; the first is the reference.
    arm_ids: tuple[str, ...]
    #: Arm id -> the build it ran, e.g. ``"go@v0.29.0"``.
    arm_labels: dict[str, str]
    #: ``samples[arm_id][metric]`` is the per-round vector, warm-up excluded.
    #: Every arm has every metric, and all vectors share one non-zero length.
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

    def __post_init__(self) -> None:
        _check_arm_ids(self.cell_id, self.arm_ids)
        if not set(self.arm_labels) == set(self.samples) == set(self.arm_ids):
            raise ValueError(
                f"{self.cell_id}: labels and samples must name exactly the arms"
            )
        # Every contrast reads every metric of both of its arms.
        for arm_id in self.arm_ids:
            if set(self.samples[arm_id]) != set(METRICS):
                raise ValueError(
                    f"{self.cell_id}: arm {arm_id} needs samples for exactly "
                    f"{list(METRICS)}, got {sorted(self.samples[arm_id])}"
                )
        # Entry i of every vector is round i; unequal lengths are unpaired.
        lengths = {len(v) for arm in self.samples.values() for v in arm.values()}
        if len(lengths) > 1:
            raise ValueError(f"{self.cell_id}: sample vectors differ in length")
        if lengths == {0}:
            raise ValueError(f"{self.cell_id}: no rounds were recorded")

    @property
    def reference(self) -> str:
        """The arm every other arm is compared against: always the first."""
        return self.arm_ids[0]

    def rss_censored_reason(self, a: str, b: str) -> str | None:
        """Why the RSS contrast of ``b`` against ``a`` can't be judged, or None.

        A peak at the floor was clipped, not measured, and clipping pulls the
        ratio toward 1.000: two clipped arms give a tight, meaningless PASS,
        and one shrinks a real difference. Arms outside the pair don't count.
        """
        if self.rss_floor_bytes <= 0:
            return None
        if min(self.samples[a]["rss"] + self.samples[b]["rss"]) > self.rss_floor_bytes:
            return None
        return (
            f"peak rss reaches the {self.rss_floor_bytes / 2**20:.0f} MiB "
            "measurement floor, so the arms are not distinguishable"
        )

    @property
    def n_rounds(self) -> int:
        return len(self.samples[self.reference]["wall"])

    @property
    def candidates(self) -> tuple[str, ...]:
        """Every arm id except the reference, in configured order."""
        return tuple(a for a in self.arm_ids if a != self.reference)

    def contrast(
        self, a: str, b: str, metric: str, config: BenchConfig
    ) -> stats.PairedComparison:
        """Compare arm ``b`` against arm ``a``: the ratio is b/a, as reported."""
        return stats.compare(
            self.samples[a][metric],
            self.samples[b][metric],
            confidence=config.confidence,
            seed=config.seed,
            n_resamples=config.n_resamples,
        )

    def contrast_pairs(self) -> list[tuple[str, str]]:
        """The ``(a, b)`` contrasts this cell is judged on."""
        return _contrast_pairs(self.arm_ids)


def _contrast_pairs(arm_ids: Sequence[str]) -> list[tuple[str, str]]:
    """``(reference, candidate)`` for each candidate.

    The analysis and the precision stop rule both read this, so the loop waits
    for exactly the contrasts that will be judged.
    """
    reference, *candidates = arm_ids
    return [(reference, b) for b in candidates]


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
        arms: two or more, all run every round; the first is the reference.
        config: round-loop knobs.
        deadline: absolute ``clock()`` value past which no new round starts.
        control: records that this is the A/A cell; does not change the loop.
        sdk: which SDK this cell belongs to, so that the analysis can pair it
            with the right control. Only matters in a multi-SDK run.
        clock: injectable monotonic clock.
        run: injectable measurement function, for testing the loop itself.

    Raises:
        ValueError: if fewer than two arms were given or their ids collide.
        MeasurementError: if any invocation fails. A benchmark over an
            operation that errors out is measuring the error path.
        BudgetExhausted: if the deadline passed before ``min_rounds``, or
            during warm-up.
    """
    arms = tuple(arms)
    arm_ids = tuple(a.name for a in arms)
    # Before anything is measured: a cell that cannot be analysed must not
    # spend its budget first.
    _check_arm_ids(cell_id, arm_ids)
    reference = arm_ids[0]
    pairs = _contrast_pairs(arm_ids)

    # Seeded per cell so a rerun reproduces the interleaving exactly, but the
    # cells do not all share one order (which would correlate their noise).
    rng = random.Random(f"{config.seed}:{cell_id}")
    samples = _empty_samples(arm_ids)
    round_durations: list[float] = []
    rss_floor = 0
    started = clock()

    def one_round(into: dict[str, dict[str, list[float]]]) -> None:
        # Build the round off to the side. If the deadline expires partway
        # through, none of that partial round may enter the paired sample
        # vectors.
        completed = _empty_samples(arm_ids)
        round_rss_floor = 0
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            # The label alone is ambiguous: a control's copies share one.
            who = f"{arm.name} ({arm.label})"
            inv = arm.invocation
            if inv.output is not None:
                inv.output.unlink(missing_ok=True)
            timeout_s = config.timeout_s
            if deadline is not None:
                remaining_s = deadline - clock()
                if remaining_s <= 0:
                    raise BudgetExhausted(
                        f"{cell_id}: budget expired before {who} could run"
                    )
                timeout_s = min(timeout_s, remaining_s)
            try:
                sample = run(inv.argv, inv.child_env(), timeout_s=timeout_s)
            except MeasurementError as e:
                if deadline is not None and clock() >= deadline:
                    raise BudgetExhausted(
                        f"{cell_id}: budget expired while running {who}"
                    ) from e
                raise MeasurementError(f"{cell_id}: {who} failed: {e}") from e
            if deadline is not None and clock() > deadline:
                raise BudgetExhausted(f"{cell_id}: budget expired while running {who}")
            round_rss_floor = max(round_rss_floor, sample.rss_floor_bytes)
            for metric in METRICS:
                completed[arm.name][metric].append(sample.metric(metric))

        nonlocal rss_floor
        rss_floor = max(rss_floor, round_rss_floor)
        for arm_name in completed:
            for metric in METRICS:
                into[arm_name][metric].extend(completed[arm_name][metric])

    for i in range(config.warmup):
        # Warm-up rounds pay the one-time costs -- page cache, `go build`
        # cache, npx package resolution, JIT warm-up -- that would otherwise
        # land unevenly and show up as a difference between builds. Their
        # samples are collected into a throwaway dict and dropped.
        #
        # The deadline is checked here too, and not only in the measured loop
        # below. The budget's end is absolute, so warm-ups that overrun it
        # spend the *following* cells' time and then reach the measured loop
        # with nothing left -- paying the full cost of the cell and producing
        # no data. Better to give up here and say why.
        if deadline is not None and clock() >= deadline:
            raise BudgetExhausted(
                f"{cell_id}: budget ran out after {i} of {config.warmup} "
                f"warm-up rounds ({clock() - started:.0f}s), "
                "before any measurement began"
            )
        try:
            one_round(_empty_samples(arm_ids))
        except BudgetExhausted as e:
            raise BudgetExhausted(
                f"{cell_id}: budget ran out during warm-up after {i} of "
                f"{config.warmup} rounds ({clock() - started:.0f}s)"
            ) from e

    stopped_because = "max_rounds"
    for _ in range(config.max_rounds):
        round_start = clock()
        if deadline is not None and round_start >= deadline:
            stopped_because = "budget"
            break
        if deadline is not None and round_durations:
            # Do not start a round we cannot finish: a half-measured round is
            # unpaired data, and unpaired data is exactly what this design
            # exists to avoid.
            expected = float(np.median(round_durations))
            if round_start + expected > deadline:
                stopped_because = "budget"
                break
        try:
            one_round(samples)
        except BudgetExhausted:
            stopped_because = "budget"
            break
        round_durations.append(clock() - round_start)

        n = len(samples[reference]["wall"])
        if n >= config.min_rounds and _precise_enough(samples, config, pairs):
            stopped_because = "precision"
            break

    elapsed = clock() - started
    n = len(samples[reference]["wall"])
    if n < config.min_rounds:
        raise BudgetExhausted(
            f"{cell_id}: only {n} rounds completed in {elapsed:.0f}s, "
            f"below the configured minimum of {config.min_rounds}"
        )
    return CellResult(
        cell_id=cell_id,
        arm_ids=arm_ids,
        arm_labels={a.name: a.label for a in arms},
        samples=samples,
        n_warmup=config.warmup,
        elapsed_s=elapsed,
        stopped_because=stopped_because,
        control=control,
        sdk=sdk,
        rss_floor_bytes=rss_floor,
    )


def _precise_enough(
    samples: dict[str, dict[str, list[float]]],
    config: BenchConfig,
    pairs: Sequence[tuple[str, str]],
) -> bool:
    """True once every judged contrast's gated CIs are narrow enough.

    Stopping on the first precise contrast would leave the rest INCONCLUSIVE
    with budget unspent. Looks only at interval *width*, never at where it
    sits or at any p-value -- see the module docstring.
    """
    for metric in config.gated_metrics:
        for a, b in pairs:
            c = stats.compare(
                samples[a][metric],
                samples[b][metric],
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
    (see :func:`contrast_key`) and holds the *finalized* comparisons -- the
    ones carrying adjusted p-values and verdicts. There is one contrast per
    candidate, cell and metric: each candidate against the reference.
    Ungated metrics are included so they appear in the report, but they
    cannot fail the build, and they are corrected separately from the gated
    ones: adjusting across tests nobody gates on only makes a real regression
    harder to confirm.

    Each SDK's cells are paired with *that SDK's* control. A run measuring go
    and java has two harness paths and two noise floors, and judging java's
    cells against go's control would be judging them against a floor that was
    never measured for them. A control with K copies of the reference yields
    K-1 A/A contrasts, and the worst of them is the floor.
    """
    comparisons: dict[str, stats.PairedComparison] = {}
    gated: set[str] = set()
    censored: dict[str, str] = {}
    control_keys: set[str] = set()

    for result in results:
        for a, b in result.contrast_pairs():
            floored = result.rss_censored_reason(a, b)
            for metric in METRICS:
                key = contrast_key(result.cell_id, a, b, metric)
                # Stored for every pair and metric, before any `continue`: the
                # report and the noise floor look keys up directly.
                comparisons[key] = result.contrast(a, b, metric, config)
                # Identify every metric of a control before applying
                # metric-specific censoring. Otherwise a floored control RSS
                # key looks like a candidate comparison to the run-level
                # "nothing measured" safeguard.
                if result.control:
                    control_keys.add(key)
                if metric == "rss" and floored is not None:
                    censored[key] = floored
                    continue
                if not result.control and metric in config.gated_metrics:
                    gated.add(key)

    # Pick each SDK's noise floor only once every control contrast exists.
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
    controls: dict[str, str] = {}
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
        controls=controls,
        control_keys=control_keys,
        censored=censored,
        threshold=config.threshold,
        alpha=stats.DEFAULT_ALPHA,
    )
