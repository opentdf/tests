"""SDK performance regression cells.

One test per cell: an operation at a payload size, measuring the newest
installed release against the branch build on the same runner, in the same
round, in a randomized order.

**These tests do not assert.** Each one records its raw samples and passes.
The verdict cannot be reached cell by cell: the multiplicity correction is
computed across every gated cell in the run, and the A/A control can
invalidate all of them at once. The gate therefore runs once in
``pytest_sessionfinish`` (see ``conftest.py``), which fails the session on a
confirmed regression.

Nothing is collected here without ``--bench``; see ``conftest.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import pytest

import abac
from fixtures import bench
from perf import report, runner
from perf.cells import BenchCell

pytestmark = pytest.mark.benchmark


def test_sdk_performance(
    bench_cell: BenchCell,
    bench_config: runner.BenchConfig,
    bench_arms: bench.ArmResolver,
    bench_payloads: dict[str, Path],
    bench_ciphertexts: bench.CiphertextFactory,
    bench_budget: runner.Budget,
    bench_recorder: report.BenchmarkRecorder,
    attribute_default_rsa: abac.Attribute,
    tmp_dir: Path,
) -> None:
    """Measure one cell and record it; the session-wide gate decides.

    A cell that cannot be measured -- a missing build, two builds that would
    not be doing the same work, a budget that ran out -- is skipped *and*
    recorded as skipped, so that a quiet report is visibly quiet rather than
    indistinguishable from a clean one.
    """

    def bail(reason: str) -> NoReturn:
        bench_recorder.skip(bench_cell.id, reason)
        pytest.skip(reason)

    try:
        arms = bench_arms(bench_cell.sdk)
    except bench.ArmSelectionError as e:
        bail(str(e))

    problem = bench.comparability_problem(arms)
    if problem:
        bail(problem)

    ct_file = (
        bench_ciphertexts(arms, bench_cell.payload.label)
        if bench_cell.operation == "decrypt"
        else None
    )
    baseline, candidate = bench.build_arms(
        bench_cell,
        arms,
        pt_file=bench_payloads[bench_cell.payload.label],
        ct_file=ct_file,
        tmp_dir=tmp_dir,
        attr_values=attribute_default_rsa.value_fqns,
    )

    try:
        result = runner.run_cell(
            bench_cell.id,
            baseline,
            candidate,
            bench_config,
            deadline=bench_budget.next_deadline(),
            control=bench_cell.control,
            sdk=bench_cell.sdk,
        )
    except runner.BudgetExhausted as e:
        bail(str(e))

    bench_recorder.record(result)
