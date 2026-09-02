"""The paired round loop that produces comparable samples for one cell.

A *cell* is one operation at one payload size, measured for two SDK builds.
The loop runs both arms once per round, in a randomized order, until it has
either enough precision or no more time.

Why rounds rather than "run A 30 times, then B 30 times"
--------------------------------------------------------
A shared runner drifts: a noisy neighbour arrives, the CPU thermally throttles,
the page cache warms. Run all of A and then all of B and every one of those
effects lands entirely on one arm and shows up as a difference between builds.
Interleaving means both arms see the same conditions within a round, and the
per-round ratio differences it out.

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
    """One side of a comparison."""

    #: ``"baseline"`` or ``"candidate"``; identifies the role, not the build.
    name: str
    #: The build under this role, e.g. ``"go@v0.29.0"``.
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
    baseline_label: str
    candidate_label: str
    #: ``samples[arm_name][metric]`` is the per-round vector, warm-up excluded.
    samples: dict[str, dict[str, list[float]]]
    n_warmup: int
    elapsed_s: float
    stopped_because: str
    #: True for the A/A control, where both arms are the same build.
    control: bool = False
    #: Which SDK's control cell assesses this cell's noise floor. A run may
    #: measure several SDKs, and each has its own harness path and its own
    #: floor; go's says nothing about java's.
    sdk: str = ""
    #: Highest measurement floor seen in this cell -- the RSS of the process
    #: that forked each invocation. See :mod:`perf._launcher`.
    rss_floor_bytes: int = 0

    @property
    def rss_censored_reason(self) -> str | None:
        """Why this cell's peak RSS cannot be compared, or None if it can.

        A command whose peak sits at the floor was not measured, it was
        clipped, and both arms clip to the same value. The resulting ratio is
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
            "measurement floor, so the two arms are not distinguishable"
        )

    @property
    def n_rounds(self) -> int:
        first = next(iter(self.samples.values()), {})
        return len(next(iter(first.values()), []))

    def metric_pair(self, metric: str) -> tuple[list[float], list[float]]:
        """Return ``(baseline, candidate)`` vectors for one metric."""
        return self.samples["baseline"][metric], self.samples["candidate"][metric]

    def compare(self, metric: str, config: BenchConfig) -> stats.PairedComparison:
        baseline, candidate = self.metric_pair(metric)
        return stats.compare(
            baseline,
            candidate,
            confidence=config.confidence,
            seed=config.seed,
            n_resamples=config.n_resamples,
        )


def _empty_samples() -> dict[str, dict[str, list[float]]]:
    return {arm: {m: [] for m in METRICS} for arm in ("baseline", "candidate")}


def run_cell(
    cell_id: str,
    baseline: Arm,
    candidate: Arm,
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
        baseline: the arm the candidate is compared against.
        candidate: the arm under test. For an A/A control this is the same
            build as ``baseline``, running through the identical path.
        deadline: absolute ``clock()`` value past which no new round starts.
        control: records that this is the A/A cell; does not change the loop.
        sdk: which SDK this cell belongs to, so that the analysis can pair it
            with the right control. Only matters in a multi-SDK run.
        clock: injectable monotonic clock.
        run: injectable measurement function, for testing the loop itself.

    Raises:
        MeasurementError: if any invocation fails. A benchmark over an
            operation that errors out is measuring the error path.
        BudgetExhausted: if the deadline passed before ``min_rounds``, or
            during warm-up.
    """
    arms = (baseline, candidate)
    # Seeded per cell so a rerun reproduces the interleaving exactly, but the
    # cells do not all share one order (which would correlate their noise).
    rng = random.Random(f"{config.seed}:{cell_id}")
    samples = _empty_samples()
    round_durations: list[float] = []
    rss_floor = 0
    started = clock()

    def one_round(into: dict[str, dict[str, list[float]]]) -> None:
        # Build the round off to the side. If the deadline expires after one
        # arm, none of that partial round may enter the paired sample vectors.
        completed = _empty_samples()
        round_rss_floor = 0
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            inv = arm.invocation
            if inv.output is not None:
                inv.output.unlink(missing_ok=True)
            timeout_s = config.timeout_s
            if deadline is not None:
                remaining_s = deadline - clock()
                if remaining_s <= 0:
                    raise BudgetExhausted(
                        f"{cell_id}: budget expired before {arm.label} could run"
                    )
                timeout_s = min(timeout_s, remaining_s)
            try:
                sample = run(inv.argv, inv.child_env(), timeout_s=timeout_s)
            except MeasurementError as e:
                if deadline is not None and clock() >= deadline:
                    raise BudgetExhausted(
                        f"{cell_id}: budget expired while running {arm.label}"
                    ) from e
                raise MeasurementError(f"{cell_id}: {arm.label} failed: {e}") from e
            if deadline is not None and clock() > deadline:
                raise BudgetExhausted(
                    f"{cell_id}: budget expired while running {arm.label}"
                )
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
            one_round(_empty_samples())
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

        n = len(samples["baseline"]["wall"])
        if n >= config.min_rounds and _precise_enough(samples, config):
            stopped_because = "precision"
            break

    elapsed = clock() - started
    n = len(samples["baseline"]["wall"])
    if n < config.min_rounds:
        raise BudgetExhausted(
            f"{cell_id}: only {n} rounds completed in {elapsed:.0f}s, "
            f"below the configured minimum of {config.min_rounds}"
        )
    return CellResult(
        cell_id=cell_id,
        baseline_label=baseline.label,
        candidate_label=candidate.label,
        samples=samples,
        n_warmup=config.warmup,
        elapsed_s=elapsed,
        stopped_because=stopped_because,
        control=control,
        sdk=sdk,
        rss_floor_bytes=rss_floor,
    )


def _precise_enough(
    samples: dict[str, dict[str, list[float]]], config: BenchConfig
) -> bool:
    """True once every gated metric's CI is narrow enough to decide on.

    Deliberately looks only at interval *width*, never at where the interval
    sits or at any p-value -- see the module docstring.
    """
    for metric in config.gated_metrics:
        c = stats.compare(
            samples["baseline"][metric],
            samples["candidate"][metric],
            confidence=config.confidence,
            seed=config.seed,
            n_resamples=_INTERIM_RESAMPLES,
        )
        # `not (a <= b)` rather than `a > b`, which is not the same thing when
        # a is NaN: an unusable interval must read as "keep going", and
        # `NaN > b` is False, which would end the loop and call it precise.
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

    ``GateResult.comparisons`` is keyed by ``"<cell_id>/<metric>"`` and holds
    the *finalized* comparisons -- the ones carrying adjusted p-values and
    verdicts. Ungated metrics are included so they appear in the report, but
    they cannot fail the build, and they are corrected separately from the
    gated ones: adjusting across tests nobody gates on only makes a real
    regression harder to confirm.

    Each SDK's cells are paired with *that SDK's* control. A run measuring go
    and java has two harness paths and two noise floors, and judging java's
    cells against go's control would be judging them against a floor that was
    never measured for them.
    """
    comparisons: dict[str, stats.PairedComparison] = {}
    gated: set[str] = set()
    censored: dict[str, str] = {}
    control_keys: set[str] = set()
    controls: dict[str, str] = {}
    control_for_sdk = {
        r.sdk: f"{r.cell_id}/{_CONTROL_METRIC}" for r in results if r.control
    }

    for result in results:
        floored = result.rss_censored_reason
        for metric in METRICS:
            key = f"{result.cell_id}/{metric}"
            comparisons[key] = result.compare(metric, config)
            control_key = control_for_sdk.get(result.sdk)
            if control_key is not None:
                controls[key] = control_key
            # Identify every metric of a control before applying metric-specific
            # censoring. Otherwise a floored control RSS key looks like an A/B
            # comparison to the run-level "nothing measured" safeguard.
            if result.control:
                control_keys.add(key)
            if metric == "rss" and floored is not None:
                censored[key] = floored
                continue
            if not result.control and metric in config.gated_metrics:
                gated.add(key)

    return stats.apply_multiplicity_control(
        comparisons,
        gated=gated,
        controls=controls,
        control_keys=control_keys,
        censored=censored,
        threshold=config.threshold,
        alpha=stats.DEFAULT_ALPHA,
    )
