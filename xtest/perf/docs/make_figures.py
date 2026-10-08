"""Render the three figures that explain the benchmark's decision rule.

Run ``python -m perf.docs.make_figures`` from ``xtest/`` to rewrite the
committed SVGs, ``--check`` to fail on drift, and ``--verify`` to re-run the
Monte Carlo behind the frozen constants below.

Every number here came out of :mod:`perf.docs.verify`. They are frozen rather
than computed at render time so that the committed SVGs are a pure function of
literals and geometry: a scipy upgrade that shifted a tie correction would
otherwise rewrite three binary-looking files in a diff nobody can read.
``--verify`` is how the freezing stays honest.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from perf.docs import svgkit as k
from perf.docs.svgkit import Band, Canvas, Panel, Scale, series

# --- Figure 1 ---------------------------------------------------------------

#: Default gating margins, from ``perf.stats.DEFAULT_THRESHOLD``.
THRESHOLD = 1.15
IMPROVE_MARGIN = 1 / THRESHOLD  # 0.8696

#: ``(ratio, ci_low, ci_high, right-hand label, mark color)`` for four cells
#: planted one per region. From ``verify.simulate_example_cells()``.
FIG1_CELLS: tuple[tuple[float, float, float, str, str], ...] = (
    (1.304, 1.276, 1.346, "1.30 [1.28, 1.35]", series(1)),
    (1.087, 1.054, 1.110, "1.09 [1.05, 1.11]", "var(--muted)"),
    (0.983, 0.956, 1.005, "0.98 [0.96, 1.01]", "var(--muted)"),
    (0.808, 0.793, 0.825, "0.81 [0.79, 0.83]", series(2)),
)

#: Cells where the CI clause passed but the unadjusted p-clause did not, out of
#: 1200. From ``verify.simulate_binding_clause()``.
FIG1_BINDING_DISAGREEMENTS = 0
FIG1_BINDING_TRIALS = 1200

#: ``(ci_low, ci_high, p_slower)`` for a constructed cell that passes the CI
#: clause on a raw p of 0.343. From ``verify.ci_without_significance()``: the
#: zero above is a fact about the harness's noise model, not an implication.
FIG1_COUNTEREXAMPLE = (1.211, 1.223, 0.343)

# --- Figure 2 ---------------------------------------------------------------

#: From ``verify.simulate_improvement_p_clause((4, 12, 24))``, rounded to 2dp.
#: These count acceptances of the improvement *p-clause*, not whole IMPROVED
#: verdicts -- see ``FIG2_NULL_CI_PASSES``.
FIG2_CELLS = (4, 12, 24)
FIG2_OLD_RULE = (0.43, 2.71, 6.28)
FIG2_NEW_RULE = (0.05, 0.07, 0.06)

#: Null cells out of 2000 whose CI clause for IMPROVED passed, from
#: ``verify.simulate_null_improvement_ci()``. Zero, so neither rule above ever
#: completed a false IMPROVED verdict on this null: the conjunction masked the
#: broken clause rather than the clause being harmless.
FIG2_NULL_CI_PASSES = 0
FIG2_NULL_CI_TRIALS = 2000

# --- Figure 3 ---------------------------------------------------------------

#: From ``verify.simulate_scale(...)``, ``verify.simulate_stall_tails(...)`` and
#: ``verify.simulate_stall_size(...)``, rounded to 3dp.
FIG3_RATIOS = (1.0, 1.3, 2.0, 4.0)
FIG3_SD_RAW = (0.142, 0.164, 0.224, 0.412)
FIG3_SD_LOG = (0.142, 0.141, 0.141, 0.141)

FIG3_STALL_P = (0.0, 0.05, 0.15, 0.30)
#: Stalls on the candidate arm only. The true median ratio moves with them, so
#: these are rejection rates under a (small) real effect, not test size.
FIG3_SLOWER_TAIL = (0.047, 0.107, 0.362, 0.815)
FIG3_FASTER_TAIL = (0.049, 0.017, 0.001, 0.000)
FIG3_MEDIAN_RATIO = (1.000, 1.008, 1.026, 1.068)
#: The same stall rate on both arms: contamination just as heavy, true ratio
#: still 1. This row is the one that measures size, and it stays at nominal.
FIG3_SLOWER_BOTH_ARMS = (0.048, 0.051, 0.057, 0.039)

ALPHA = 0.05


def fig1_three_regions() -> str:
    """The decision space: three verdicts, but both tests sit at the point null."""
    w, h = 900.0, 378.0
    panel = Panel(x=64, y=92, w=626, h=160)
    scale = Scale(0.70, 1.45, panel.x, panel.right, log=True)
    c = Canvas()

    c.text(
        64,
        30,
        "Three verdicts, two tests of the same point null",
        size=15,
        weight="bold",
    )
    c.text(
        64,
        52,
        "Where the gate's clauses actually sit on the ratio axis.",
        cls="muted",
    )

    x_improve = scale.at(IMPROVE_MARGIN)
    x_regress = scale.at(THRESHOLD)
    x_null = scale.at(1.0)

    # Region washes. "No verdict" is grey on purpose: the absence of a verdict
    # is not a fourth category competing with the other two.
    c.rect(panel.x, panel.y, x_improve - panel.x, panel.h, fill=series(2), opacity=0.12)
    c.rect(
        x_improve,
        panel.y,
        x_regress - x_improve,
        panel.h,
        fill="var(--grid)",
        opacity=0.38,
    )
    c.rect(
        x_regress,
        panel.y,
        panel.right - x_regress,
        panel.h,
        fill=series(1),
        opacity=0.12,
    )

    c.text(
        (panel.x + x_improve) / 2,
        panel.y + 16,
        "IMPROVED",
        cls="muted",
        size=11,
        anchor="middle",
        weight="bold",
    )
    # Offset into the left half of the middle band, clear of the point-null
    # rule and of its callout directly above.
    c.text(
        (x_improve + x_null) / 2,
        panel.y + 16,
        "no verdict",
        cls="muted",
        size=11,
        anchor="middle",
    )
    c.text(
        (x_regress + panel.right) / 2,
        panel.y + 16,
        "REGRESSION",
        cls="muted",
        size=11,
        anchor="middle",
        weight="bold",
    )

    # The margins, and then the point null drawn over them.
    c.rule(x_improve, panel.y, x_improve, panel.bottom, cls="rule")
    c.rule(x_regress, panel.y, x_regress, panel.bottom, cls="rule")
    c.stroke(x_null, panel.y, x_null, panel.bottom, stroke=series(0), width=2)
    c.text(x_null, 76, "both p-values test H0: ratio = 1", size=11, anchor="middle")
    c.stroke(x_null, 80, x_null, panel.y, stroke=series(0), width=1)

    for i, (ratio, lo, hi, label, color) in enumerate(FIG1_CELLS):
        y = panel.y + 44 + i * 30
        c.stroke(scale.at(lo), y, scale.at(hi), y, stroke=color, width=2)
        for bound in (lo, hi):
            c.stroke(
                scale.at(bound), y - 5, scale.at(bound), y + 5, stroke=color, width=2
            )
        c.dot(scale.at(ratio), y, fill=color)
        c.text(panel.right + 14, y + 4, label, size=11)

    c.rule(panel.x, panel.bottom, panel.right, panel.bottom, cls="axis")
    # No 0.80 tick: its label collides with the wider "0.87 = 1/1.15" one, and
    # the margin is the number worth reading here.
    for tick, text in (
        (0.70, "0.70"),
        (IMPROVE_MARGIN, "0.87 = 1/1.15"),
        (1.00, "1.00"),
        (1.15, "1.15"),
        (1.30, "1.30"),
        (1.45, "1.45"),
    ):
        c.text(
            scale.at(tick),
            panel.bottom + 20,
            text,
            cls="muted",
            size=11,
            anchor="middle",
        )
    c.text(
        (panel.x + panel.right) / 2,
        panel.bottom + 42,
        "ratio of medians, candidate / baseline (log scale)",
        cls="muted",
        size=11,
        anchor="middle",
    )

    c.text(
        64,
        322,
        "The margins at 0.87 and 1.15 are carried by the confidence interval alone.",
        cls="muted",
        size=11,
    )
    c.text(
        64,
        340,
        f"On {FIG1_BINDING_TRIALS} cells simulated from the harness's noise model "
        f"the CI clause passed while the raw p-clause failed "
        f"{FIG1_BINDING_DISAGREEMENTS} times.",
        cls="muted",
        size=11,
    )
    # The zero above invites "so clause 1 implies clause 2", which is false.
    ci_low, ci_high, p_slower = FIG1_COUNTEREXAMPLE
    c.text(
        64,
        358,
        f"It is not implied, though: a constructed cell reaches "
        f"[{ci_low:.2f}, {ci_high:.2f}] at p = {p_slower:.2f}.",
        cls="muted",
        size=11,
    )

    return k.document(
        w,
        h,
        c.render(),
        title="Three verdicts, two tests of the same point null",
        desc=(
            "A log-scaled ratio axis banded into IMPROVED below 0.87, no verdict, "
            "and REGRESSION above 1.15. A vertical rule at 1.00 marks where both "
            "Wilcoxon tests actually test. Four example cells are drawn as "
            "confidence intervals, one per region."
        ),
    )


def fig2_correction_runs_backwards() -> str:
    """False improvement p-clause acceptances per run, old rule against new."""
    w, h = 660.0, 428.0
    panel = Panel(x=74, y=96, w=536, h=204)
    y = Scale(0, 7, panel.bottom, panel.y)
    band = Band(len(FIG2_CELLS), panel.x, panel.right, pad=0.40)
    c = Canvas()

    c.text(
        64, 30, "A multiplicity correction running backwards", size=15, weight="bold"
    )
    c.text(
        64,
        52,
        "Cells per run accepting the improvement p-clause, everything drawn "
        "from a pure null.",
        cls="muted",
    )
    # Slots are assigned in declaration order, not by sentiment. Do not "fix"
    # this to paint the broken rule in a warning color: status hues are
    # reserved, and recoloring by verdict would make the two panels of figure 3
    # disagree with this one.
    k.legend(
        c, 64, 76, [(0, "old: p_adj_slower > 0.95"), (1, "new: p_adj_faster < 0.05")]
    )

    k.y_axis(c, panel, y, [0, 2, 4, 6], ["0", "2", "4", "6"])
    c.rule(panel.x, panel.bottom, panel.right, panel.bottom, cls="axis")

    for i, (old, new) in enumerate(zip(FIG2_OLD_RULE, FIG2_NEW_RULE, strict=True)):
        for slot, value in ((0, old), (1, new)):
            x, width = band.slot(i, slot, 2)
            if width > 30.0:
                # Cap the width but keep the pair together: growing the gap
                # instead would read as two separate groups.
                x += (width - 30.0) / 2
                width = 30.0
            c.column(x, panel.bottom, y.at(value), width, fill=series(slot))
            c.text(
                x + width / 2, y.at(value) - 8, f"{value:.2f}", size=11, anchor="middle"
            )

    k.x_ticks(
        c,
        panel,
        [band.center(i) for i in range(len(FIG2_CELLS))],
        [f"{m} cells" for m in FIG2_CELLS],
    )
    c.text(
        (panel.x + panel.right) / 2,
        panel.bottom + 44,
        "cells in the run",
        cls="muted",
        size=11,
        anchor="middle",
    )

    c.text(
        64,
        372,
        "BH never lowers a p-value, so a test that asks for a large adjusted "
        "p gets easier as a run grows.",
        cls="muted",
        size=11,
    )
    # The clause, not the verdict. Without these lines the columns read as
    # false IMPROVED verdicts, a count neither rule reaches on this null.
    c.text(
        64,
        390,
        f"These count clause 2 alone. The CI clause passed {FIG2_NULL_CI_PASSES} "
        f"of {FIG2_NULL_CI_TRIALS} null cells, so neither",
        cls="muted",
        size=11,
    )
    c.text(
        64,
        408,
        "rule completed a verdict here -- the conjunction is what hid the "
        "broken clause.",
        cls="muted",
        size=11,
    )

    return k.document(
        w,
        h,
        c.render(),
        title="A multiplicity correction running backwards",
        desc=(
            "Grouped columns over runs of 4, 12 and 24 cells, counting cells "
            "that accept the improvement p-clause under a pure null. The old "
            "rule's count rises from 0.43 to 6.28 per run; the new rule's "
            "stays flat near 0.06. The CI clause of the same verdict passed "
            "zero of 2000 null cells, so these are clause acceptances rather "
            "than completed IMPROVED verdicts."
        ),
    )


def _line_series(
    c: Canvas, band: Band, y: Scale, values: Sequence[float], slot: int
) -> None:
    points = [(band.center(i), y.at(v)) for i, v in enumerate(values)]
    c.polyline(points, stroke=series(slot))
    for px, py in points:
        c.dot(px, py, fill=series(slot))


def fig3_positivity() -> str:
    """Two panels: the log transform fixes the scale problem, not the skew one."""
    w, h = 1000.0, 488.0
    left = Panel(x=74, y=96, w=366, h=190)
    right = Panel(x=596, y=96, w=354, h=190)
    c = Canvas()

    c.text(64, 30, "A positive, right-tailed measurement", size=15, weight="bold")
    c.text(
        64,
        52,
        "Taking logs makes the spread independent of the effect. It does not "
        "make the two tails behave alike.",
        cls="muted",
    )

    # Left panel: spread against the size of a real effect.
    c.text(left.x, 80, "Scale: the log absorbs it", size=12, weight="bold")
    y_left = Scale(0, 0.45, left.bottom, left.y)
    band_left = Band(len(FIG3_RATIOS), left.x, left.right, pad=0.30)
    k.y_axis(c, left, y_left, [0, 0.15, 0.30, 0.45], ["0", "0.15", "0.30", "0.45"])
    c.rule(left.x, left.bottom, left.right, left.bottom, cls="axis")
    _line_series(c, band_left, y_left, FIG3_SD_RAW, 0)
    _line_series(c, band_left, y_left, FIG3_SD_LOG, 1)
    last_left = band_left.center(len(FIG3_RATIOS) - 1)
    c.text(
        last_left, y_left.at(FIG3_SD_RAW[-1]) - 14, "0.412", size=11, anchor="middle"
    )
    c.text(
        last_left,
        y_left.at(FIG3_SD_LOG[-1]) + 22,
        "0.141 - flat",
        size=11,
        anchor="middle",
    )
    k.x_ticks(
        c,
        left,
        [band_left.center(i) for i in range(len(FIG3_RATIOS))],
        [f"{r:.1f}" for r in FIG3_RATIOS],
    )
    # Both axis titles sit at bottom + 82 so the two panels align, even though
    # only the right one needs the extra rows its strips occupy.
    c.text(
        (left.x + left.right) / 2,
        left.bottom + 82,
        "true ratio (candidate / baseline)",
        cls="muted",
        size=11,
        anchor="middle",
    )
    k.legend(c, left.x, 398, [(0, "sd of raw difference"), (1, "sd of log-ratio")])

    # Right panel: its own y-axis, because two measures never share one.
    c.text(right.x, 80, "Skew: it does not", size=12, weight="bold")
    y_right = Scale(0, 0.85, right.bottom, right.y)
    band_right = Band(len(FIG3_STALL_P), right.x, right.right, pad=0.30)
    k.y_axis(
        c, right, y_right, [0, 0.2, 0.4, 0.6, 0.8], ["0", "0.2", "0.4", "0.6", "0.8"]
    )
    c.rule(right.x, right.bottom, right.right, right.bottom, cls="axis")
    y_alpha = y_right.at(ALPHA)
    c.rule(right.x, y_alpha, right.right, y_alpha, cls="ref")
    # Left end, not right: the faster tail lands on zero at the right edge and
    # its direct label would sit on top of this one.
    c.text(right.x + 4, y_alpha - 8, "alpha = 0.05", cls="muted", size=11)
    _line_series(c, band_right, y_right, FIG3_SLOWER_TAIL, 0)
    _line_series(c, band_right, y_right, FIG3_FASTER_TAIL, 1)
    last_right = band_right.center(len(FIG3_STALL_P) - 1)
    c.text(
        last_right,
        y_right.at(FIG3_SLOWER_TAIL[-1]) - 14,
        "0.815",
        size=11,
        anchor="middle",
    )
    c.text(
        last_right,
        y_right.at(FIG3_FASTER_TAIL[-1]) - 14,
        "0.000",
        size=11,
        anchor="middle",
    )
    k.x_ticks(
        c,
        right,
        [band_right.center(i) for i in range(len(FIG3_STALL_P))],
        [f"{p:.0%}" for p in FIG3_STALL_P],
    )

    # The median ratio and the both-arms control are further quantities on
    # other measures. They go in labelled text rows, not on more y-axes.
    # The control row is what stops the plotted curves reading as test size:
    # stalling one arm moves the median off 1, so the null it would be the
    # size of is not the null being simulated.
    for row, label, values in (
        (42, "median ratio", FIG3_MEDIAN_RATIO),
        (60, "both arms stalled", FIG3_SLOWER_BOTH_ARMS),
    ):
        c.text(
            right.x - 12,
            right.bottom + row,
            label,
            cls="muted",
            size=11,
            anchor="end",
        )
        for i, value in enumerate(values):
            c.text(
                band_right.center(i),
                right.bottom + row,
                f"{value:.3f}",
                cls="muted",
                size=11,
                anchor="middle",
            )
    c.text(
        (right.x + right.right) / 2,
        right.bottom + 82,
        "share of rounds stalled, on the candidate arm only",
        cls="muted",
        size=11,
        anchor="middle",
    )
    k.legend(c, right.x, 398, [(0, "slower tail"), (1, "faster tail")])

    c.text(
        64,
        432,
        "Signed-rank needs the paired difference symmetric under H0. Stalling "
        "one arm breaks that directionally -- and moves the true median, so the",
        cls="muted",
        size=11,
    )
    c.text(
        64,
        450,
        "plotted rates are power against a 2.6% effect, not size. Stall both "
        "arms and the true ratio stays 1: the slower tail holds at nominal.",
        cls="muted",
        size=11,
    )
    c.text(
        64,
        468,
        "Either way it is the interval, not the p-value, that refuses to call "
        "1.026 a regression.",
        cls="muted",
        size=11,
    )

    return k.document(
        w,
        h,
        c.render(),
        title="A positive, right-tailed measurement",
        desc=(
            "Two panels. On the left, the spread of the raw paired difference "
            "grows with the effect while the log-ratio's stays flat at 0.141. "
            "On the right, stalling the candidate arm only drives the slower "
            "tail's rejection rate from 0.047 to 0.815 and the faster tail's "
            "to zero, while the median ratio moves only from 1.000 to 1.068. "
            "A text row shows the same stall rates applied to both arms, "
            "where the true ratio stays 1 and the slower tail holds between "
            "0.039 and 0.057 -- so the curves measure sensitivity to "
            "asymmetric contamination, not test size."
        ),
    )


FIGURES: tuple[tuple[str, Callable[[], str]], ...] = (
    ("fig1-three-regions.svg", fig1_three_regions),
    ("fig2-fdr-backwards.svg", fig2_correction_runs_backwards),
    ("fig3-positivity.svg", fig3_positivity),
)


def _verify() -> int:
    """Re-run the Monte Carlo and compare it to the constants above."""
    from perf.docs import verify

    failures: list[str] = []

    def check(name: str, got: object, want: object) -> None:
        if got != want:
            failures.append(f"{name}: simulated {got}, figure says {want}")

    old, new = verify.simulate_improvement_p_clause(FIG2_CELLS)
    check("fig2 old rule", tuple(round(v, 2) for v in old), FIG2_OLD_RULE)
    check("fig2 new rule", tuple(round(v, 2) for v in new), FIG2_NEW_RULE)
    check(
        "fig2 null CI clause",
        verify.simulate_null_improvement_ci(trials=FIG2_NULL_CI_TRIALS),
        FIG2_NULL_CI_PASSES,
    )

    raw, log = verify.simulate_scale(FIG3_RATIOS)
    check("fig3 sd raw", tuple(round(v, 3) for v in raw), FIG3_SD_RAW)
    check("fig3 sd log", tuple(round(v, 3) for v in log), FIG3_SD_LOG)

    slower, faster, medians = verify.simulate_stall_tails(FIG3_STALL_P)
    check("fig3 slower tail", tuple(round(v, 3) for v in slower), FIG3_SLOWER_TAIL)
    check("fig3 faster tail", tuple(round(v, 3) for v in faster), FIG3_FASTER_TAIL)
    check("fig3 median ratio", tuple(round(v, 3) for v in medians), FIG3_MEDIAN_RATIO)
    check(
        "fig3 both arms stalled",
        tuple(round(v, 3) for v in verify.simulate_stall_size(FIG3_STALL_P)),
        FIG3_SLOWER_BOTH_ARMS,
    )

    check(
        "fig1 binding clause",
        verify.simulate_binding_clause(),
        FIG1_BINDING_DISAGREEMENTS,
    )
    check(
        "fig1 counterexample",
        verify.ci_without_significance(),
        FIG1_COUNTEREXAMPLE,
    )
    check(
        "fig1 example cells",
        verify.simulate_example_cells(),
        tuple(cell[:3] for cell in FIG1_CELLS),
    )

    for line in failures:
        print(f"MISMATCH {line}")
    if failures:
        print(f"\n{len(failures)} constant(s) no longer match the simulation.")
        return 1
    print("All figure constants match the simulation.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent,
        help="directory to write the SVGs into",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare against the committed files instead of writing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="re-run the Monte Carlo behind the frozen constants",
    )
    args = parser.parse_args(argv)

    if args.verify:
        return _verify()

    stale: list[str] = []
    for name, build in FIGURES:
        svg = build()
        path = args.out / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != svg:
                stale.append(name)
        else:
            path.write_text(svg, encoding="utf-8")
            print(f"wrote {path}")

    if args.check:
        for name in stale:
            print(f"STALE {name}")
        if stale:
            print("\nRun: python -m perf.docs.make_figures")
            return 1
        print("All figures are up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
