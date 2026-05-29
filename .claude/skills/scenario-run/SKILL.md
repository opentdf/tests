---
name: scenario-run
description: This skill should be used when the user asks to "run the scenario", "run the scenario tests", "execute the scenario suite", "test the scenario", or after `scenario-up` to invoke the pytest selection declared by `xtest/scenarios/<id>.yaml` and classify the result against the scenario's `expected:` / `actual:` fields.
allowed-tools: Bash, Read
---

# scenario-run

Invoke the pytest selection declared by the scenario's `suite` block against the running instance, then classify the result in terms of the ticket the scenario was authored for. The same four-bucket classification works for bug-repros (where "expected" means *failure that matches `actual:`*), TDD scenarios (where "expected" means *skip-until-feature-lands*), and assertion drift between draft tests and what the implementation actually emits.

## Inputs

- Path to the scenario YAML (`xtest/scenarios/<id>.yaml`).
- (Optional) the user's expected outcome, if the scenario's `expected:` field is sparse.

## Process

### Step 1 — Invoke the runner

```bash
uv run otdf-local scenario run xtest/scenarios/<id>.yaml
```

This translates the scenario's `suite.select`, `suite.containers`, `suite.markers`, and `sdks.{encrypt,decrypt}` into the equivalent `pytest --sdks-encrypt … --sdks-decrypt … --containers …` invocation under `xtest/` with `OTDF_LOCAL_INSTANCE_NAME` set. SDK tokens are emitted in xtest's `sdk@version` form; the resolved version names come from the sibling `<scenario>.installed.json`.

Failure modes:
- `Error: <path>.installed.json not found` — the user skipped Step 1 of `scenario-up`. Run `uv run otdf-sdk-mgr install scenario <path>` first.
- `installed.json` is present but `sdks.encrypt` / `sdks.decrypt` are empty arrays despite the scenario declaring SDK pins — this is the **source-built SDK** case; fall back to a direct pytest invocation (see Step 1b).

### Step 1b — Source-build fallback

When the scenario pins source-built SDKs (`source.ref` rather than `version`), `otdf-local scenario run` today produces an empty `--sdks-*` argv. Invoke pytest directly instead:

```bash
cd xtest
set -a
eval "$(cd ../otdf-local && OTDF_LOCAL_INSTANCE_NAME=<id> uv run otdf-local env)"
source test.env
set +a

# Map each source-pinned SDK to its dist slug under xtest/sdk/<lang>/dist/.
# For platform PR #N, the slug is typically `refs--pull--<N>--head`.
PLATFORM_VERSION=<future-version> OTDFCTL_HEADS='["<go-dist-slug>"]' \
  uv run pytest <suite.select> \
    --sdks-encrypt <lang>@<dist-slug> \
    --sdks-decrypt <lang>@<dist-slug> \
    --containers <suite.containers>
```

`PLATFORM_VERSION` and `OTDFCTL_HEADS` defaults are noted in `scenario-up`; pull them from there or from the scenario's source-build env knobs section. This fallback is temporary — tracked at [DSPX-3417](https://virtru.atlassian.net/browse/DSPX-3417) (scenario YAML accepting source builds) and [DSPX-3418](https://virtru.atlassian.net/browse/DSPX-3418) (`OTDFCTL_HEADS` → CLI flag).

### Step 2 — Capture exit code and tail of output

The pytest output is the source of truth; do not re-interpret it. Save the last ~60 lines for the evidence quote in the classification.

### Step 3 — Classify against `expected:` and `actual:`

Pick exactly one bucket. Lead the reply with the bucket name; users skim for it.

- **Expected outcome** — the test result matches what `expected:` (or, for a bug, `actual:`) predicts.
  - Bug scenario: pytest FAILED with an assertion or stderr matching `actual:`. Bug reproduced; cite the matching line.
  - TDD/feature scenario on a ref where the feature isn't landed: tests SKIPPED via `supports("<feature>")`. Gate still pending as predicted.
  - TDD/feature scenario on a ref where the feature is landed: tests PASSED. The scenario is now a regression gate.

- **Unexpected outcome** — the test result is *not* what the scenario predicted.
  - Bug scenario: pytest PASSED. Either the bug is fixed at this pin, or the scenario doesn't capture it tightly enough. Suggest widening the assertion, pinning a different ref, or closing the bug.
  - TDD/feature scenario: tests FAILED for a reason that doesn't match `actual:`. A real bug surfaced, OR the prereq implementation landed and the test now needs a real assertion rather than a skip.

- **Assertion-stricter-than-implementation** — pytest FAILED on a specific assertion whose expected value is *aspirational* (drawn from a PR description, spec, or RFC) rather than current behaviour. Diagnostic: one assertion compares a single real field to a single concrete value, both legitimate, and they simply don't match. The implementation works correctly under a *different* contract than the test encodes. Action: relax the assertion to the observed value (record both old and new in a comment so the intent is preserved), file a follow-up if the strict value is load-bearing. This is what catches "PR description said KAO type is `mlkem-wrapped` but the binary emits `wrapped`."

- **Unrelated failure** — pytest errored out (collection error, environment issue, import error, timeout). Don't claim outcome match either way; report the error and recommend a next diagnostic step. If services look wrong, defer to `scenario-doctor` for a state diff.

### Step 4 — Record artifacts

Pytest leaves logs under `tests/instances/<id>/logs/`. List the relevant per-service log paths in the reply so the user can attach them to the Jira ticket.

## Output format

One-line headline naming the bucket, then a short bulleted summary:
- `select:` the pytest selector that ran
- `exit_code:` the pytest return value
- `evidence:` 1–2 lines from the output that justify the classification
- `logs:` paths to the relevant per-service logs

## When to defer

If the failure looks environmental (services missing, ports drift, stale binary) rather than test-substantive, hand off to `scenario-doctor` for a state-vs-intent diff before iterating on the test or scenario.
