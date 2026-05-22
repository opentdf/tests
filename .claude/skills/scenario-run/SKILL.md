---
name: scenario-run
description: Use after `scenario-up` to run the scenario's test suite and classify results against its expected/actual fields.
allowed-tools: Bash, Read
---

# scenario-run

You run the pytest selection declared by the scenario's `suite` block against the running instance and interpret the result in terms of the ticket the scenario was authored for. The same three-bucket classification works for bug-repros (where "expected" means *failure that matches `actual:`*) and for TDD scenarios (where "expected" means *skip-until-feature-lands*).

## Inputs

- Path to the scenario YAML (`xtest/scenarios/<id>.yaml`).
- (Optional) the user's expected outcome, if the scenario's `expected:` field is sparse.

## Process

1. **Invoke the runner**:

   ```bash
   uv run otdf-local scenario run xtest/scenarios/<id>.yaml
   ```

   This translates the scenario's `suite.select`, `suite.containers`, `suite.markers`, and `sdks.{encrypt,decrypt}` into the equivalent `pytest --sdks-encrypt ... --sdks-decrypt ... --containers ...` invocation under `xtest/` with `OTDF_LOCAL_INSTANCE_NAME` set. SDK tokens are emitted in xtest's `sdk@version` form (see PR #446) — the resolved version names come from the sibling `<scenario>.installed.json` that `otdf-sdk-mgr install scenario` writes.

   If `scenario run` exits with `Error: <path>.installed.json not found`, the user skipped the install step. Tell them to run `uv run otdf-sdk-mgr install scenario <path>` (or re-run `scenario-up`) before retrying.

2. **Capture exit code and tail of output**. The pytest output is the source of truth; don't re-interpret.

3. **Classify** against the scenario's `expected:` and `actual:` fields:
   - **Expected outcome** — the test result matches what `expected:` (or, for a bug, `actual:`) predicts.
     - Bug scenario: pytest FAILED with an assertion/stderr matching `actual:`. Bug reproduced. Cite the matching line.
     - TDD/feature scenario on a ref where the feature isn't landed yet: tests SKIPPED via `supports("<feature>")`. Feature gate is still pending as predicted.
     - TDD/feature scenario on a ref where the feature is landed: tests PASSED. Feature works; the scenario is now a regression gate.
   - **Unexpected outcome** — the test result is *not* what the scenario predicted.
     - Bug scenario: pytest PASSED. Either the bug is fixed at this pin, or the scenario doesn't capture it tightly enough. Suggest widening the assertion, pinning a different ref, or marking the bug closed.
     - TDD/feature scenario: tests FAILED for a reason that doesn't match `actual:`. A real bug surfaced, OR the prereq implementation work landed and the test now needs a real assertion (not a skip). Surface the actual failure to the user.
   - **Unrelated failure** — pytest errored out (collection error, environment issue, import error, timeout). Don't claim outcome match either way; report the error and recommend a next diagnostic step.

4. **Record artifacts**. The pytest run leaves logs under `tests/instances/<id>/logs/`. List the relevant log files in your reply so the user can attach them to the Jira ticket.

## Output format

One-line headline (`expected outcome` / `unexpected outcome` / `unrelated failure`), then a short bulleted summary:
- `select:` the pytest selector
- `exit_code:` the return value
- `evidence:` 1-2 lines from the output that justify the classification
- `logs:` paths to the relevant per-service logs
