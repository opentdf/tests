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
>
> To compare **two named refs** instead — a branch against `main`, say — use
> `bench-baseline-ref` / `bench-candidate-ref` and skip all of the above; see
> [Benchmarking one branch against another](#benchmarking-one-branch-against-another).

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

### The table

```
| cell                | metric     | baseline | candidate | ratio (95% CI)        | p (BH) | n  | verdict |
| go-encrypt-1MiB     | wall clock | 412.3 ms | 498.1 ms  | 1.208x [1.171, 1.245] | <0.001 | 22 | **REGRESSION** |
```

- **cell** — `<sdk>-<operation>-<payload>`, plus `-control` for the A/A cell.
  Payload sizes default to 1 KiB, 1 MiB, and 32 MiB; `--bench-payloads` selects
  others. See [Payload sizes and what they can gate](#payload-sizes-and-what-they-can-gate)
  before reading a throughput result — at the default sizes there is not one.
- **ratio** — candidate ÷ baseline. `1.208x` means the candidate took 20.8%
  longer. Below 1.0 means faster.
- **95% CI** — the bootstrap interval on that ratio. Its *width* is how precisely
  this run could measure; a wide interval means a noisy runner, not a big change.
- **p (BH)** — one-sided p-value, Benjamini–Hochberg adjusted across the run.
- **n** — paired rounds actually measured (20–60; the loop stops early once the
  interval is narrow enough).

### The verdicts

**REGRESSION** — the CI lower bound exceeds the threshold (default **1.15x**,
i.e. 15% slower) *and* the adjusted p < 0.05. Both clauses are required, and
neither is redundant: the threshold alone would fire on a reproducible 0.5%
slowdown nobody cares about, and significance alone would fire on noise often
enough to be ignored within a week. This fails the job.

**PASS** — not a regression, *and* the run had enough precision to have found
one. "We looked and found nothing" only counts when we could have found
something.

**IMPROVED** — the same test in the other direction. Never fails anything.

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
   process boot, package resolution, TLS handshake, token fetch. The largest
   cell firing on its own points at throughput — the crypto and IO path — but
   only if that cell is large enough for throughput to be most of it, which at
   32 MiB it is not. Both means something structural.
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
| `--bench-payloads` | `1KiB,1MiB,32MiB` | Sizes to measure, e.g. `1KiB,1GiB` |
| `--bench-min-rounds` / `--bench-max-rounds` | `20` / `60` | Rounds per cell |
| `--bench-warmup` | `5` | Discarded rounds paying one-time costs |
| `--bench-budget-seconds` | `1500` | Wall-clock allowance shared by all cells |
| `--bench-seed` | `0` | Payloads, round order, bootstrap. Fix it to reproduce |
| `--bench-out` | `test-results/benchmarks` | JSON destination |
| `--bench-no-gate` | off | Measure and report, never fail |

A local run is noisier than CI unless the machine is otherwise idle. Close
things; the noise floor will tell you whether you succeeded.

### Payload sizes and what they can gate

**At the default sizes this harness cannot fail a build on throughput.** Not
"is unlikely to" — cannot. On a 4-core Linux runner a go encrypt costs about
450 ms before it touches the payload: runtime start, config load, TLS
handshake, token fetch, KAS key fetch. Going from 1 KiB to 32 MiB — a 32,000x
increase in bytes — adds about 72 ms on top of that.

| operation | 1 KiB | 1 MiB | 32 MiB | payload-dependent |
| --- | --- | --- | --- | --- |
| encrypt | 455.0 ms | 447.6 ms | 526.7 ms | ~72 ms (13.6%) |
| decrypt | 533.6 ms | 513.1 ms | 600.7 ms | ~67 ms (11.2%) |

The gate is 1.15x of the *whole cell*, which at 32 MiB encrypt is +79 ms —
more than the entire payload-dependent portion. A candidate that doubled every
per-segment cost would come in at 1.136x and report **PASS**. The 1 MiB cells
are worse: indistinguishable from 1 KiB, so they measure startup twice.

This is not a statistics problem. The intervals are tight and the control is
clean; the matrix is simply asking the wrong sizes. To gate throughput the
payload term has to dominate, which means going much larger:

```bash
uv run pytest --bench --sdks go \
  --bench-payloads 1KiB,1GiB \
  --bench-budget-seconds 5400 --bench-max-rounds 200 \
  -v test_benchmarks.py
```

At 1 GiB the payload term is ~2.3 s against the same ~450 ms fixed cost, so it
is ~84% of the cell and a 15% gate lands inside the part being tested.

Three things to know before adding a large size:

- **Budget.** Each size adds an encrypt and a decrypt cell, and the budget is
  divided evenly as cells start. A 1 GiB round costs ~6 s against ~1 s at 32
  MiB, so the default 1500 s will not reach `min_rounds` on both new cells.
- **Disk.** A run holds roughly twice the payload total plus the largest size
  twice over. 1 GiB needs ~5 GiB free. This is checked before the first
  measurement, because running out mid-run arrives as a non-zero exit from the
  CLI under test and reads as "this build is broken".
- **`max_rounds` binds before the budget does.** In the run these numbers come
  from, 3 of 7 cells stopped on `max_rounds` while only 418 s of 1500 s was
  spent. Raising the budget alone buys nothing; raise both.

The control stays at 1 MiB whatever you select. Its CI width is the run's noise
floor and every other cell is judged against it, so it must not move with the
matrix — otherwise two runs of the same comparison can disagree about which
cells were trustworthy for a reason unrelated to either build.

### Benchmarking one branch against another

The nightly comparison is newest-release vs branch head, which is the right
question to ask every night and the wrong one to ask about a specific change:
the baseline carries every other commit that landed since the release. To
point the harness at two refs you name, dispatch X-Test with:

| Input | Example | Meaning |
| --- | --- | --- |
| `run-benchmarks` | ✅ | Required; the bench job is off otherwise |
| `focus-sdk` | `go` | Must name one SDK — the matrix runs only this one |
| `bench-baseline-ref` | `main` | The build you are comparing *against* |
| `bench-candidate-ref` | `feat/DSPX-2604-createtdf-chunked` | The build under suspicion |
| `bench-payloads` | `1KiB,1GiB` | Sizes to measure; default `1KiB,1MiB,32MiB` |
| `bench-budget-seconds` | `5400` | Shared allowance; default `1500` |
| `bench-max-rounds` | `200` | Cap per cell; default `60` |

The last three are why a dispatch can answer a question the nightly cannot. A
nightly runs unattended every day and has to stay inside a sensible cost; a
dispatch is asked for, once, about one thing. If the change is a throughput
claim, spend the budget — see [Payload sizes and what they can
gate](#payload-sizes-and-what-they-can-gate), because at the defaults the
answer will be **PASS** whatever the change did.

Either ref can be anything `otdf-sdk-mgr versions resolve` accepts: a branch, a
tag, a full or short SHA, or `refs/pull/N/head`. Both are built from source and
installed side by side, and arm selection is told which is which explicitly —
so neither has to be a release, which is the whole point.

The `*-ref` inputs are ignored by the bench job in this mode. They still drive
the functional test matrix, so a dispatch can answer "is it slower?" without
also changing what the rest of the run tests.

Two things this mode does **not** change, both of which bound what a result
means:

- **The server stays on `main`.** The bench job pins the platform and runs a
  single KAS, whatever the refs say. A candidate whose speed depends on a
  matching server change will not show it here.
- **The baseline is whatever you named.** For a stacked branch, `main` as the
  baseline measures the whole stack. Name the parent branch instead to isolate
  the top commit.

It fails fast, before spending a runner, when the two refs resolve to the same
commit or when `focus-sdk` is `all`.

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

#### Separate BH families

Gated keys are corrected as their own family. Ungated metrics get a family of
their own so they still carry a reportable verdict. Adjusting the gated metrics
against metrics nobody gates on would only make a real regression harder to
confirm. Controls and censored keys are excluded from correction entirely — an
A/A cell is not a hypothesis about the candidate.

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

#### A dist tag is one path component

`otdf-sdk-mgr` flattens `/` to `--` when it resolves a ref, so
`feat/DSPX-2604-createtdf-chunked` installs as
`dist/feat--DSPX-2604-createtdf-chunked/`. Everything downstream walks those
directories exactly one level deep — `tdfs.all_versions_of()` lists `dist/*/`,
the go `Makefile` finds `src/*/` — so a slash that survives resolution is
discovered as a build named `feat` with no `cli.sh` in it, which
`all_versions_of()` raises on before any cell runs. Branch-vs-branch dispatch
is the first thing to routinely feed it a slashed ref, and the `--bench-*`
specs name the flattened tag: `go@feat--DSPX-2604-createtdf-chunked`.

#### Payloads are seeded per payload, not per run

`tmp_dir` persists between runs. With one RNG stream shared across the payloads, a
partially-cached set skips some `randbytes` calls and shifts the stream for every
payload after it — so a rerun measures different bytes than the run it claims to
be comparable with. Each payload derives from `f"{seed}:{label}"` instead.

Content is random rather than repetitive because compressible input would let an
SDK that happens to compress look faster for reasons unrelated to crypto.

Large payloads are written in chunks so a 1 GiB file is not first built as a
1 GiB `bytes` in RAM. The chunk size must stay a multiple of 4: CPython's
`randbytes` draws a 32-bit word at a time, so a 4-byte-aligned split produces
the same stream as one call would, and the seed-to-bytes promise survives both
the constant changing and a payload growing past it.

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

**A new payload size** — no code change: `--bench-payloads 1KiB,1GiB` (or the
`bench-payloads` dispatch input). Sizes parse as a count and a binary unit —
`B`, `KiB`, `MiB`, `GiB` — and the list is sorted ascending and deduplicated by
byte count, so `1KiB,1024B` is one cell rather than two identical ones. Changing
`DEFAULT_PAYLOAD_SPEC` in `cells.py` changes what the nightly measures; think
about the budget first. Cell count per SDK is `1 + 2 × len(payloads)`, and the
budget is divided evenly across all of them.

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

Every one of these fails *silently* and *plausibly* when broken: the numbers
still look like numbers. That is why they are written down.
