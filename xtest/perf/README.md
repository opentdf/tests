# SDK performance regression benchmarks

A paired A/B benchmark for the OpenTDF SDK CLIs. It answers one question:
**did this change make the SDK measurably and meaningfully slower?**

Two builds — normally the newest installed release and the branch build —
are measured on the *same* runner, interleaved round by round, and only their
*ratio* is reported. Nothing is ever compared against a stored historical
number.

It runs nightly (one runner per SDK) and on `workflow_dispatch` with
`run-benchmarks` checked. It never runs on pull requests: 30 minutes of serial
measurement is too slow for a PR gate, and a PR runner is the noisiest place to
measure.

> **Dispatching it by hand:** set the `*-ref` inputs to `main latest`, not the
> default `main`. The nightly cron resolves `main latest` on its own, but an
> explicit `main` installs only the branch build — no release to use as a
> baseline — and every cell skips. The run fails rather than passing empty
> (see [NOTHING MEASURED](#the-verdicts)), but it will have wasted 45 minutes
> to tell you that.

- **Section 1 — [Reading a result](#1-reading-a-result)** is for developers on
  the SDKs and the platform: your build got flagged, what does that mean.
- **Section 2 — [Maintaining the harness](#2-maintaining-the-harness)** is for
  whoever changes this code: how it works and why it is shaped this way.

---

## 1. Reading a result

### Where the output is

| Artifact | Where | Contents |
| --- | --- | --- |
| Job summary | The Actions run page | The table below, plus the verdict |
| `bench-<sdk>` artifact | Run artifacts | `<sdk>.json` with **every raw per-round sample**, and an HTML report |
| Terminal | Job log tail | One-line summary and the JSON path |

The JSON is the useful one. It holds each cell's full per-round vectors for both
arms, so a surprising verdict can be re-analysed offline instead of by re-running
a 30-minute job to look at the same numbers again.

Each `metrics` entry carries both directions of the test: `p_value` /
`p_adjusted` are the one-sided "candidate is slower" pair that the regression
gate reads, and `p_value_faster` / `p_adjusted_faster` are the matching
"candidate is faster" pair behind IMPROVED. The `_adjusted` forms are the
Benjamini–Hochberg values within that key's correction family and are `null`
for controls and censored keys, which enter no family. These are additive
fields; the artifact is still `"schema": 1`.

### The table

```markdown
| cell                | metric     | baseline | candidate | ratio (95% CI)        | p (BH) | n  | verdict |
| go-encrypt-1MiB     | wall clock | 412.3 ms | 498.1 ms  | 1.208x [1.171, 1.245] | <0.001 | 22 | **REGRESSION** |
```

- **cell** — `<sdk>-<operation>-<payload>`, plus `-control` for the A/A cell.
  Payload sizes are 1 KiB, 1 MiB, and 32 MiB.
- **ratio** — candidate ÷ baseline. `1.208x` means the candidate took 20.8%
  longer. Below 1.0 means faster.
- **95% CI** — the bootstrap interval on that ratio. Its *width* is how precisely
  this run could measure; a wide interval means a noisy runner, not a big change.
- **p (BH)** — the one-sided "candidate is slower" p-value, Benjamini–Hochberg
  adjusted across the run. The opposite direction has its own adjusted p-value;
  it is in the JSON rather than the table.
- **n** — paired rounds actually measured (20–60; the loop stops early once the
  interval is narrow enough).

### The verdicts

![Three verdicts, two tests of the same point null: a log-scaled ratio axis
banded into IMPROVED below 0.87, no verdict, and REGRESSION above 1.15, with a
rule at 1.00 marking where both Wilcoxon tests actually
test.](docs/fig1-three-regions.svg)

**REGRESSION** — the CI lower bound exceeds the threshold (default **1.15x**,
i.e. 15% slower) *and* the adjusted p < 0.05. Both clauses are required, and
neither is redundant: the threshold alone would fire on a reproducible 0.5%
slowdown nobody cares about, and significance alone would fire on noise often
enough to be ignored within a week. This fails the job.

**PASS** — not a regression, *and* the run had enough precision to have found
one. "We looked and found nothing" only counts when we could have found
something.

**IMPROVED** — the same test mirrored: the CI *upper* bound below `1/threshold`
(0.87x by default) *and* the adjusted "candidate is faster" p < 0.05. That
second clause is its own lower-tail test with its own BH adjustment, not a
reversal of the slowdown one — see [the two tails](#the-two-tails). Never fails
anything.

**inconclusive** — the run could not decide. Common reasons, all shown in the
note beside the verdict:
- the runner was too noisy for this cell's interval to be usable;
- the A/A noise floor was wider than the 15% effect being gated on, so a real
  regression of that size could not have been distinguished from noise;
- peak RSS hit the measurement floor (see below);
- too few rounds completed inside the time budget.

**Inconclusive is not a pass.** It means the question was not answered. If a
change you expect to be performance-sensitive comes back inconclusive on every
cell, the run told you nothing and re-running it is reasonable.

**NOTHING MEASURED** — no cell produced a comparison at all, usually because
only one build was installed so there was no baseline to compare against. This
**fails the job**. An empty run and a clean run have the same empty list of
regressions, so without this a benchmark that had quietly stopped measuring
would keep reporting a green tick. The "Not measured" section of the report
lists the reason for each cell.

> One cause looks like a bug and is not. If an SDK's newest release tags the same
> commit as `main` — java sat at `v0.18.0 == main == dev == 57d070b0` through
> August 2026 — then `main latest` resolves both arms to one SHA, `otdf-sdk-mgr`
> installs a single build, and every cell skips with *"no final release to compare
> against; installed: main"*. The message is true from where the harness stands, but
> the release it is looking for does exist; the two arms are just the same code.
> Check with `otdf-sdk-mgr versions resolve <sdk> main latest` — one entry back
> instead of two means there is nothing to measure until `main` moves.

### The A/A control

Each SDK gets a control cell that compares the baseline build **against itself**
through the identical pipeline. Its true ratio is exactly 1.0 by construction, so
whatever it reports is the harness's own error on this runner. It does two jobs:

- If the control *trips* — its own A/A comparison looks like a real effect — then
  something is systematically biased and **the whole run stops being able to fail
  the build**. Results are still reported, marked untrustworthy.
- Its interval width is the run's **noise floor**: the smallest effect this
  runner could have resolved. If the floor is wider than the threshold, cells
  report inconclusive rather than PASS.

In a multi-SDK run each SDK is judged against *its own* control — go's harness
path says nothing about java's. `noise_floor_by_control` in the JSON has each
one; the top-level `noise_floor` is the worst of them.

### Gated vs ungated metrics

| Metric | Gated? | Why |
| --- | --- | --- |
| wall clock | yes | What users experience |
| peak RSS | yes | Regressions here are real and invisible in timing |
| CPU time | **no** | Noisiest of the three on a shared runner, and a real CPU regression shows up in wall clock anyway |

Ungated rows are labelled `(ungated)` and reported for context only. They cannot
fail the build.

Peak RSS additionally gets **censored** when a cell's readings sit at the
measurement floor (the RSS of the process that forked the command). Both arms
clip to the same value there, producing a `1.000x` ratio with a tight interval —
the most convincing-looking PASS the harness can emit, and completely meaningless.
Censored cells report inconclusive with the floor named in the note.

### My build was flagged. Now what?

1. **Read the CI column, not just the ratio.** A `1.20x [1.02, 1.41]` is a very
   different claim from `1.20x [1.19, 1.21]`.
2. **Check the control row.** If the A/A cell for your SDK also looks strange,
   suspect the runner before your code.
3. **Look at which cells fired.** Only the 1 KiB cells means startup cost —
   process boot, package resolution, TLS handshake, token fetch. Only 32 MiB
   means throughput — the crypto and IO path. Both means something structural.
4. **Reproduce locally.** The comparison is self-contained; it does not need CI.

```bash
cd xtest && set -a && source test.env && set +a

# whatever two builds you want, side by side under sdk/<name>/dist/
uv run pytest --bench --sdks go \
  --bench-baseline go@v0.29.0 \
  --bench-candidate go@main \
  -v test_benchmarks.py
```

Useful knobs while investigating:

| Option | Default | Use |
| --- | --- | --- |
| `--bench-threshold` | `1.15` | Smallest slowdown worth failing on |
| `--bench-min-rounds` / `--bench-max-rounds` | `20` / `60` | Rounds per cell |
| `--bench-warmup` | `5` | Discarded rounds paying one-time costs |
| `--bench-budget-seconds` | `1500` | Wall-clock allowance shared by all cells |
| `--bench-seed` | `0` | Payloads, round order, bootstrap. Fix it to reproduce |
| `--bench-out` | `test-results/benchmarks` | JSON destination |
| `--bench-no-gate` | off | Measure and report, never fail |

A local run is noisier than CI unless the machine is otherwise idle. Close
things; the noise floor will tell you whether you succeeded.

### What this benchmark cannot tell you

- **Anything about absolute speed.** A number from a GitHub-hosted runner is not
  comparable to a number from your laptop or from last week's runner. Only
  within-run ratios mean anything.
- **Anything about trends.** There is no history and no stored baseline. Each run
  is a self-contained experiment.
- **Anything about a slowdown under 15%** by default. That is the price of not
  crying wolf on a shared runner.
- **Anything about your change specifically** if the baseline moved too — the
  comparison is release-vs-`main`, so it catches whatever landed on `main`.

---

## 2. Maintaining the harness

### Module map

| File | Responsibility |
| --- | --- |
| `cells.py` | The experiment matrix: payload sizes, `BenchCell`, `cells_for()`. No pytest, no `tdfs` |
| `measure.py` | Wall/CPU/RSS for one invocation, via `os.wait4` |
| `_launcher.py` | The separate process that actually forks the measured command |
| `runner.py` | The paired round loop, the stopping rule, the budget, `analyze()` |
| `stats.py` | Pure functions: log-ratios, bootstrap CI, Wilcoxon, BH, the decision rule |
| `report.py` | Session recorder, JSON artifact, step-summary markdown |
| `docs/` | The figures in this README, and the Monte Carlo behind them. Documentation only; imported by nothing in the harness |
| `../fixtures/bench.py` | The pytest glue: arm selection, payloads, ciphertexts, budget |
| `../test_benchmarks.py` | One test per cell. **Records; never asserts** |
| `../conftest.py` | `--bench*` options, cell parametrization, the session-finish gate |

Offline tests, no platform and no subprocesses needed:

```bash
cd xtest
uv run pytest -q test_bench_stats.py test_bench_measure.py \
                 test_bench_runner.py test_bench_arms.py
```

These run on every PR via `check.yml`, so the harness is exercised continuously
even though the benchmark itself runs nightly.

### The design, and why

#### Ratios within a run, never comparison against history

CPU models vary, tenancy is shared, and steal time is unbounded on a hosted
runner. Storing a baseline and diffing against it produces false alarms until
people mute the job. Both builds are measured on the same runner and the
statistic is the within-round ratio, so runner speed is a shared factor that
divides out.

#### Interleaved rounds, randomized within the round

Running all of A then all of B lands every drift effect — a noisy neighbour
arriving, thermal throttling, the page cache warming — entirely on one arm, where
it reads as a difference between builds. Both arms run once per round instead.
The order *within* a round is shuffled because a fixed order is itself a
confounder: whichever arm goes second inherits the first one's cache state.

The shuffle is seeded per cell (`f"{seed}:{cell_id}"`), so a rerun reproduces the
interleaving exactly while different cells do not share one order — which would
correlate their noise.

#### Log-ratios

`d_i = ln(candidate_i) - ln(baseline_i)`. Logs make ratios symmetric (a 2x
slowdown and a 2x speedup are equal and opposite) and additive, which is what
the median and the bootstrap want. Everything is exponentiated back for reporting.

![Two panels. On the left, the spread of the raw paired difference grows with
the effect while the log-ratio's stays flat. On the right, stalling the
candidate arm only drives the slower tail's rejection rate to 0.815 and the
faster tail's to zero while the median ratio barely moves; stalling both arms
leaves the slower tail at nominal.](docs/fig3-positivity.svg)

The log fixes a *scale* problem. Timings are strictly positive, so the raw
paired difference inherits the size of whatever effect is present — its spread
grows from 0.142 to 0.412 as the true ratio goes 1x to 4x, while the log-ratio's
stays flat at 0.141. Thresholds and interval widths are therefore comparable
across payload sizes and SDKs only because of the log.

It does not fix a *skew* problem. Signed-rank needs `d` symmetric under the
null, and a positive right-tailed variable produces one-sided contamination —
a stalled round makes an arm slower, never faster. Stalls landing on one arm
break the symmetry directionally: at a 15% stall rate the slower tail rejects
36.2% of the time and the faster tail collapses to 0.001, while the median
ratio moves only 2.6%.

Read what that is and is not. Stalling one arm changes that arm's
distribution, so the true median ratio leaves 1 and the point null the
p-values test is genuinely false — 36.2% is *power against a 2.6% effect*,
not a size failure. Running the control confirms it: stall both arms at the
same rate and the true ratio stays 1 under contamination just as heavy, and
the slower tail holds between 0.039 and 0.057 across every rate simulated.
Signed-rank is not being invalidated here; it is answering the question it was
asked, and that question is the wrong one for a gate.

Which is the second reason [both clauses](#both-clauses-of-the-decision-rule)
are required. A 2.6% shift is real and nowhere near the 15% margin, and only
the CI clause knows the difference — it is what keeps a stall-contaminated
cell from being read as a regression.

#### Stopping on precision, never on significance

> This is the single easiest thing here to "optimize" into invalidity.

The loop stops when the CI is narrow enough. It must never stop when the p-value
gets small. Peeking at p and stopping the moment it crosses alpha is optional
stopping: you get a fresh chance to cross the line every round and only ever stop
on the lucky side, which inflates the false-positive rate far past nominal.
Attained CI *width* is driven by the dispersion of the differences rather than
their location, so it is approximately ancillary to the effect being tested and
stopping on it does not bias the verdict.

`_precise_enough()` therefore looks only at interval width, never at where the
interval sits. It also uses `not (width <= target)` rather than `width > target`,
because a NaN width must read as "keep going" and `NaN > target` is `False`.

#### Both clauses of the decision rule

A cell is a regression iff the CI lower bound exceeds `threshold` **and** the
BH-adjusted p is below alpha. Clause 1 alone fires on real-but-trivial effects
measured precisely; clause 2 alone fires on noise roughly alpha of the time per
cell, and a run has enough cells that "roughly alpha" becomes "most nights".

Note which clause carries which claim. The p-values test the *point* null
(`ratio = 1`); the margin is carried by the interval alone. Across 1200 cells
simulated from the harness's log-normal noise model the CI clause passed while
the raw p-clause failed zero times, so *on measurements shaped like these*
clause 2 contributes exactly one thing clause 1 does not: the multiplicity
adjustment.

That is an observation about those distributions, not an implication —
`verify.ci_without_significance()` constructs a cell where the CI clause
passes and the raw p-clause does not. Signed-rank ranks differences by
magnitude, so 22 rounds clustered just above the margin against 8 swinging far
below it give a bootstrap CI of [1.211, 1.223] at a slower-tail p of 0.343.
Nothing in the harness produces that shape, but the gate should not be
documented as if it could not.

The conjunction is load-bearing in a second way regardless — it is also what
shields the gate from the signed-rank point null being the wrong null on
[skewed positive data](#log-ratios).

#### The two tails

Every comparison carries two one-sided p-values: `p_value` for "candidate is
slower", which REGRESSION reads, and `p_value_faster` for "candidate is
faster", which IMPROVED reads. Both come from `wilcoxon(...)` directly, and
both get their own BH adjustment inside the same family.

The obvious shortcut — derive one direction from the other, `p > 1 - alpha`
instead of a lower-tail test — is wrong twice over. The tails are not exact
complements under the discrete signed-rank null, and, far worse, **BH never
lowers a p-value**. Adjusting the upper tail and then asking whether the result
is *large* makes that clause easier to satisfy the more cells a run has, which
is a multiplicity correction running backwards: adding cells would manufacture
improvements rather than suppress false ones.
`test_adjusted_slower_tail_is_not_read_as_evidence_of_improvement` pins this.

![Grouped columns over runs of 4, 12 and 24 cells, counting acceptances of the
improvement p-clause under a pure null. The old rule's count rises from 0.43 to
6.28 per run; the new rule's stays flat near
0.06.](docs/fig2-fdr-backwards.svg)

The scale of it, under a pure null where every acceptance is false by
construction: the old rule accepted on 0.43 cells per 4-cell run and 6.28 per
24-cell run — about a quarter of everything measured — while the new rule holds
near 0.06 whatever the run size. At one cell the two rules agree to within
0.002, which is what identifies this as a multiplicity artifact rather than a
discreteness one.

Those are counts for the *p-clause on its own*, not for completed IMPROVED
verdicts. On this null the accompanying CI clause (`ci_high < 1/1.15`) passed
0 of 2000 cells, so neither rule would have published a false IMPROVED — the
conjunction is what kept the broken clause off the output. Isolating the
clause is deliberate: it is the half whose behaviour under multiplicity is at
issue, and scoring whole verdicts would report zero for both rules and
distinguish nothing. A clause that gets *more* permissive as the run grows is
worth fixing while the other clause is still masking it.

Discreteness is the smaller of the two problems and is easy to over-credit.
scipy uses the exact signed-rank null only when `n <= 50` *and* there are no
ties, so the two tails sum to 1 + the point mass there, and to exactly 1
otherwise: the excess is about +0.010 at n = 20, +0.004 at n = 30, and zero at
n >= 51. Ties from a floored RSS push a cell onto the normal approximation and
*remove* the discrepancy rather than worsening it, so this lives only in the
clean wall/cpu cells.

#### Separate BH families

Gated keys are corrected as their own family. Ungated metrics get a family of
their own so they still carry a reportable verdict. Adjusting the gated metrics
against metrics nobody gates on would only make a real regression harder to
confirm. Controls and censored keys are excluded from correction entirely — an
A/A cell is not a hypothesis about the candidate. Both tails are adjusted
within the same families, so a key's two adjusted p-values always describe the
same set of hypotheses. A key outside every family has `p_adjusted` and
`p_adjusted_faster` both unset; a control falls back to its own raw tails,
since a floor that cannot resolve itself is no floor at all.

#### One A/A control per SDK, running first

A control measures a particular SDK's harness path. `cells_for()` emits each
SDK's control first, because a run that overruns its budget loses whatever is at
the end: losing one comparison leaves the rest trustworthy, losing the control
leaves nothing trustworthy, since without a noise floor no cell may report PASS.

`GateResult.noise` is the *worst* control in the run, not the average. A single
tripped control means the harness may be biased on this runner, and averaging
that away with two quiet ones is exactly the reassurance the control exists to
withhold.

#### Measurement isolation (`_launcher.py`)

On Linux a forked child inherits the parent's resident-set accounting and
`execve` does not clear it, so `ru_maxrss` comes back as
`max(child's true peak, parent's RSS at fork time)`. Measured from a pytest
process holding numpy, scipy and a session of samples, every invocation would
report *pytest's* ~165 MiB instead of its own — a stable `1.000x` ratio that
reads as "no regression".

`posix_spawn` and `sh -c 'exec ...'` do **not** help; both were measured and both
inherit the same floor, because an exec is too late. The only fix is to fork from
a process holding nothing, which is all `_launcher.py` is for. It reports its own
RSS as the floor alongside each reading, which is what powers censoring.

Two things in that file look wrong and are not:
- `except BaseException` in the forked child — letting a `SystemExit` or
  `KeyboardInterrupt` unwind past there would run the *parent's* atexit handlers
  and flush its buffers a second time, from a process that exists only to exec.
- `os.killpg(..., SIGKILL)` on timeout — signalling the group is the point;
  leaving a wedged JVM behind would hold the runner until the job timeout.

`os.wait4` rather than `resource.getrusage(RUSAGE_CHILDREN)`, because the latter
is a process-lifetime high-water mark: once one big child has run, every later
delta reads zero.

#### Everything except the build is pinned

Both arms get the same plaintext, the same attribute (explicit RSA, so an arm
does not silently switch to EC), the same container, and the same target mode.
`comparability_problem()` refuses the comparison outright when the two builds
disagree on `hexless`, `hexaflexible`, or `autoconfigure` — a timing difference
there is a difference in *work*, not in speed.

For decrypt, both arms read one ciphertext produced by the baseline. If each arm
decrypted its own output, a difference in how the two builds *write* a TDF would
show up as a difference in how fast they read one.

#### Baselines must be final releases

`SDK.is_released()` accepts `v0.29.0-rc.1`, and `semver()` parses it to the same
`(0, 29, 0)` as the final release — so ordering by semver alone leaves them tied
and the directory listing breaks the tie. That is a baseline nobody chose, and it
differs run to run. Baseline selection uses `is_final_release()`, which matches
only a plain `vX.Y.Z`.

#### Payloads are seeded per payload, not per run

`tmp_dir` persists between runs. With one RNG stream shared across the payloads, a
partially-cached set skips some `randbytes` calls and shifts the stream for every
payload after it — so a rerun measures different bytes than the run it claims to
be comparable with. Each payload derives from `f"{seed}:{label}"` instead.

Content is random rather than repetitive because compressible input would let an
SDK that happens to compress look faster for reasons unrelated to crypto.

#### Cells record; the session gates

The verdict cannot be reached cell by cell — the multiplicity correction spans
the run and the A/A control can invalidate all of it at once. So
`test_sdk_performance` never asserts. `pytest_sessionfinish` runs `analyze()`
once, writes the artifacts **unconditionally and before gating** (a run about to
fail is exactly the one whose raw numbers someone wants), and only then sets the
exit status.

A cell that cannot be measured is skipped *and* recorded as skipped, so a quiet
report is visibly quiet rather than indistinguishable from a clean one. If
*every* cell skips, `GateResult.nothing_measured` fails the run: `--bench` is an
explicit request for a measurement, and answering it with a green tick and an
empty table is the one outcome nobody inspects.

A control-only run counts as nothing measured too, and `analyze()` has to
register each control key *before* it censors that cell's floored RSS — the
`continue` must come after `control_keys.add(key)`. Reversed, the censored RSS
key stops looking like part of a control, `has_candidate_comparisons` goes
true, and a run holding only A/A cells reports a PASS headline.

The bench job installs `go` on every runner even when it is not the SDK under
measurement, because `otdfctl` provisions the attributes and KAS registry that
every cell needs and `conftest.py` loads it at import time. `OTDFCTL_HEADS` must
name *go's* head, not the matrix SDK's.

#### Collection and isolation

Benchmark cells are **deselected** without `--bench`, via
`pytest_collection_modifyitems` and the `benchmark` marker. They are not
parametrized over an empty list — `empty_parameter_set_mark` would turn that into
one *skipped* item per test, which reads as a benchmark nobody asked for.

`--bench` refuses to run under `pytest-xdist`. Parallel workers contend for the
CPU under measurement.

### Adding to it

**A new payload size** — add a `Payload` to `PAYLOADS` in `cells.py`. Note that
`CONTROL_PAYLOAD = PAYLOADS[1]`, so inserting at the front moves the control.
Cell count per SDK is `1 + 2 × len(PAYLOADS)`; the 1500s budget is divided
across all of them, so adding sizes makes every cell poorer unless the budget
grows too.

**A new metric** — add it to `METRICS` and `METRIC_LABELS` in `measure.py`, teach
`Sample.metric()` and `format_metric()` about it, and decide whether it belongs
in `BenchConfig.gated_metrics`. Default to ungated until it has shown a usable
noise floor over several nights.

**A new operation** — extend `operation_type` and `cells_for()` in `cells.py`,
then handle it in `build_arms()` in `fixtures/bench.py`. If it needs an input
produced by the baseline, follow `CiphertextFactory`: build it once, from the
baseline only, and share it between the arms.

**A new SDK** — nothing here needs to change; it comes from `--sdks` and the
matrix in `xtest.yml`.

**A new comparability hazard** — add the feature name to
`_COMPARABILITY_FEATURES`. Cheap to add, and the failure it prevents (comparing
two builds doing different amounts of work) is invisible in the output.

### Invariants — do not break these

1. Never stop the round loop on a p-value.
2. Never compare against a stored historical number.
3. Never let a cell assert; the gate is run-level.
4. Never report PASS without a noise floor establishing the run had the power to
   fail.
5. Never let the two arms differ in anything but the build.
6. Never run the measured command from a process holding memory.
7. Never run the benchmark in parallel with anything, including itself.
8. Never let a run that measured nothing report success.
9. Never infer one tail of a test from the other, and never read an *adjusted*
   p-value in the direction it was not adjusted for.
10. Never hand-edit the figures. Change `docs/make_figures.py` and regenerate;
    if a number moves, `--verify` is what tells you whether the figure or the
    world changed.

Every one of these fails *silently* and *plausibly* when broken: the numbers
still look like numbers. That is why they are written down.
