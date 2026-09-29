"""The Monte Carlo behind the figures, kept off the rendering path.

:mod:`perf.docs.make_figures` draws from frozen constants, not from these
functions. That split is deliberate. If the figures re-simulated at render
time, a scipy release that changed a tie correction would silently rewrite
three committed SVGs and produce a diff nobody can review. Instead
``make_figures --verify`` runs these and *reports* a mismatch, and a human
decides whether the figure or the world changed.

Every model here matches the one described beside its constant.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from scipy import stats as _scipy_stats

from perf import stats
from perf.stats import DEFAULT_THRESHOLD

#: Fixed so the reported numbers are reproducible, not so they are flattering.
SEED_P_CLAUSE = 31
SEED_NULL_CI = 23
SEED_SCALE = 11
SEED_STALLS = 11
SEED_BINDING = 5
SEED_CELLS = 17

ALPHA = 0.05
TRIALS = 300


def _wilcoxon_tails(d: np.ndarray) -> tuple[float, float]:
    """Both one-sided p-values, as :func:`perf.stats._one_sided_ps` computes them."""
    slower = cast(float, _scipy_stats.wilcoxon(d, alternative="greater")[1])
    faster = cast(float, _scipy_stats.wilcoxon(d, alternative="less")[1])
    return slower, faster


def _bh(p: list[float]) -> np.ndarray:
    return np.asarray(
        _scipy_stats.false_discovery_control(np.asarray(p, dtype=float), method="bh")
    )


def _pair(
    rng: np.random.Generator,
    ratio: float = 1.0,
    *,
    n: int = 30,
    sigma: float = 0.06,
) -> tuple[np.ndarray, np.ndarray]:
    """Two log-normal arms of one synthetic cell, the candidate scaled by ``ratio``.

    ``ratio = 1`` is the A/A case: both arms from the same distribution.
    """
    b = np.exp(rng.normal(0, sigma, n))
    c = ratio * np.exp(rng.normal(0, sigma, n))
    return b, c


def _null_cell(rng: np.random.Generator, n: int = 30) -> tuple[float, float]:
    """Both tails of one A/A cell."""
    b, c = _pair(rng, n=n)
    return _wilcoxon_tails(np.log(c) - np.log(b))


def simulate_improvement_p_clause(
    cells: tuple[int, ...], *, trials: int = TRIALS
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Mean false acceptances of the improvement *p-clause* per run.

    Counts clause 2 of the IMPROVED rule only -- ``p_adjusted_slower >
    1 - alpha`` under the old formulation, ``p_adjusted_faster < alpha`` under
    the new one -- not the full verdict, which also requires ``ci_high <
    1 / threshold``. Isolating the clause is the point: it is the clause whose
    behaviour under multiplicity is being compared, and pairing it with a CI
    condition that never fires on this null would report zero for both rules
    and measure nothing.

    :func:`simulate_null_improvement_ci` measures the CI clause on the same
    null, which is what says how much of the gate the difference here reaches.

    Everything is a pure null, so every acceptance is false by construction.
    """
    rng = np.random.default_rng(SEED_P_CLAUSE)
    old: list[float] = []
    new: list[float] = []
    for m in cells:
        o = 0
        w = 0
        for _ in range(trials):
            tails = [_null_cell(rng) for _ in range(m)]
            p_slower = _bh([t[0] for t in tails])
            p_faster = _bh([t[1] for t in tails])
            o += int(np.sum(p_slower > 1 - ALPHA))
            w += int(np.sum(p_faster < ALPHA))
        old.append(o / trials)
        new.append(w / trials)
    return tuple(old), tuple(new)


def simulate_null_improvement_ci(
    *, trials: int = 2000, threshold: float = DEFAULT_THRESHOLD
) -> int:
    """Null cells whose CI clause for IMPROVED passes: ``ci_high < 1/threshold``.

    The answer is zero. The whole interval would have to sit below 0.87 --
    asserting a speedup of at least 13% -- on data with no effect at all, and
    at this dispersion it never comes close. So the figure counts p-clause
    acceptances rather than whole verdicts, and the broken rule it illustrates
    never published a false IMPROVED on its own.
    """
    rng = np.random.default_rng(SEED_NULL_CI)
    passes = 0
    for _ in range(trials):
        b, c = _pair(rng)
        if stats.compare(b, c, seed=2, n_resamples=999).ci_high < 1 / threshold:
            passes += 1
    return passes


def simulate_scale(
    ratios: tuple[float, ...], *, n: int = 30, trials: int = 3000
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Spread of the paired difference on the raw scale and the log scale.

    The raw difference inherits the effect's size because the measurements are
    positive; the log-ratio does not. That is what the log transform buys.
    """
    rng = np.random.default_rng(SEED_SCALE)
    raw: list[float] = []
    log: list[float] = []
    for r in ratios:
        rs: list[np.ndarray] = []
        ls: list[np.ndarray] = []
        for _ in range(trials):
            b = np.exp(rng.normal(0, 0.10, n) - 0.10**2 / 2)
            c = r * np.exp(rng.normal(0, 0.10, n) - 0.10**2 / 2)
            rs.append(c - b)
            ls.append(np.log(c) - np.log(b))
        raw.append(float(np.concatenate(rs).std()))
        log.append(float(np.concatenate(ls).std()))
    return tuple(raw), tuple(log)


def _stalled(
    rng: np.random.Generator, n: int, mean: float, sigma: float, stall_p: float
) -> np.ndarray:
    """A positive, right-tailed timing vector with one-sided stall contamination."""
    x = mean * np.exp(rng.normal(0, sigma, n) - sigma**2 / 2)
    return x * np.where(rng.random(n) < stall_p, 2.5, 1.0)


def _stall_rejection(
    rng: np.random.Generator,
    baseline_p: float,
    candidate_p: float,
    *,
    n: int,
    trials: int,
) -> tuple[float, float, float]:
    """Rejection rate of each tail, and the median ratio, at one pair of stall rates.

    Returns ``(slower_rate, faster_rate, median_ratio)``.
    """
    pg: list[float] = []
    pl: list[float] = []
    meds: list[float] = []
    for _ in range(trials):
        b = _stalled(rng, n, 1.0, 0.08, baseline_p)
        c = _stalled(rng, n, 1.0, 0.08, candidate_p)
        d = np.log(c) - np.log(b)
        g, f = _wilcoxon_tails(d)
        pg.append(g)
        pl.append(f)
        meds.append(float(np.exp(np.median(d))))
    return (
        float(np.mean(np.asarray(pg) < ALPHA)),
        float(np.mean(np.asarray(pl) < ALPHA)),
        float(np.median(meds)),
    )


def simulate_stall_tails(
    stall_ps: tuple[float, ...], *, n: int = 30, trials: int = 1500
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Tail rejection rates and median ratio with only the candidate arm stalling.

    This is *not* a null experiment, and the numbers are not test size: stalls
    on one arm shift that arm's distribution, so the true median ratio leaves 1
    and the rejections are power against a small real effect. It is the
    asymmetry that the figure is about -- the two tails stop matching each
    other while the median barely moves.

    :func:`simulate_stall_size` is the companion null, and reading the two
    together is what separates the two explanations. Returns
    ``(slower_rate, faster_rate, median_ratio)``.
    """
    rng = np.random.default_rng(SEED_STALLS)
    runs = [_stall_rejection(rng, 0.0, sp, n=n, trials=trials) for sp in stall_ps]
    slower, faster, medians = zip(*runs, strict=True)
    return slower, faster, medians


def simulate_stall_size(
    stall_ps: tuple[float, ...], *, n: int = 30, trials: int = 1500
) -> tuple[float, ...]:
    """Slower-tail size with *both* arms stalling at the same rate.

    Contamination just as heavy as in :func:`simulate_stall_tails`, but
    symmetric, so the true ratio stays 1 and this genuinely is the null. The
    rate holds near alpha throughout, which is what says the inflation next
    door is asymmetry rather than signed-rank failing.

    Its own generator, seeded off :data:`SEED_STALLS`, so adding or dropping
    this control cannot shift the numbers in the other run.
    """
    rng = np.random.default_rng(SEED_STALLS + 1)
    return tuple(
        _stall_rejection(rng, sp, sp, n=n, trials=trials)[0] for sp in stall_ps
    )


def simulate_binding_clause(
    ratios: tuple[float, ...] = (1.0, 1.10, 1.18, 1.30),
    *,
    threshold: float = DEFAULT_THRESHOLD,
    trials: int = TRIALS,
) -> int:
    """Count cells where the CI clause passes but the raw p-clause does not.

    The answer is zero over these log-normal draws, so on the harness's own
    noise model the p-clause contributes only its multiplicity adjustment.

    That is an empirical statement about this generative model, not an
    implication -- :func:`ci_without_significance` constructs a cell where the
    CI clause passes and the raw p-clause does not.
    """
    rng = np.random.default_rng(SEED_BINDING)
    disagreements = 0
    for r in ratios:
        for _ in range(trials):
            cmp_ = stats.compare(*_pair(rng, r), seed=2, n_resamples=999)
            if cmp_.ci_low > threshold and cmp_.p_value >= ALPHA:
                disagreements += 1
    return disagreements


def ci_without_significance() -> tuple[float, float, float]:
    """A cell passing the CI clause while the raw slower-tail p-clause fails.

    Signed-rank scores each difference by the *rank of its magnitude*, so a
    minority of large negative rounds can outweigh a majority of small
    positive ones. Here 22 rounds sit tightly just above the margin and 8 swing
    far below it: the median -- and so the bootstrap interval around it -- stays
    above ``threshold``, while the signed-rank statistic is nearly balanced.

    Nothing in the harness generates this shape; it exists to bound what
    :func:`simulate_binding_clause` is allowed to claim. Returns
    ``(ci_low, ci_high, p_slower)``.
    """
    d = np.concatenate([np.linspace(0.19, 0.21, 22), np.linspace(-2.0, -1.0, 8)])
    lo, hi = _scipy_stats.bootstrap(
        (d,),
        np.median,
        confidence_level=0.95,
        method="percentile",
        n_resamples=9999,
        rng=np.random.default_rng(0),
    ).confidence_interval
    return (
        round(float(np.exp(lo)), 3),
        round(float(np.exp(hi)), 3),
        round(float(_wilcoxon_tails(d)[0]), 3),
    )


def simulate_example_cells() -> tuple[tuple[float, float, float], ...]:
    """Four representative cells, as ``(ratio, ci_low, ci_high)``.

    Planted at a clear slowdown, a real-but-under-margin slowdown, pure noise,
    and a clear speedup -- one per region of figure 1.
    """
    rng = np.random.default_rng(SEED_CELLS)
    out: list[tuple[float, float, float]] = []
    for true_ratio in (1.31, 1.08, 1.00, 0.81):
        b, c = _pair(rng, true_ratio, n=40, sigma=0.05)
        cmp_ = stats.compare(b, c, seed=4, n_resamples=4999)
        out.append(
            (round(cmp_.ratio, 3), round(cmp_.ci_low, 3), round(cmp_.ci_high, 3))
        )
    return tuple(out)
