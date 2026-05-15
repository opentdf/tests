---
name: scenario-run
description: Execute the pytest suite declared by a scenarios.yaml against the running instance, then classify the result as "bug reproduced", "not reproduced", or "unrelated failure". Use after `scenario-up` has confirmed the instance is healthy.
allowed-tools: Bash, Read
---

# scenario-run

You run the pytest selection declared by the scenario's `suite` block against the running instance and interpret the result in terms of the bug being investigated.

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

3. **Classify**:
   - **Bug reproduced** — the test failed with an assertion or stderr that matches the scenario's `actual:` field. Cite the matching line.
   - **Bug NOT reproduced** — the test passed. This is meaningful: either the bug is fixed at this version combination, or the scenario doesn't capture it precisely yet. Suggest the user widen the assertion or pick a different version pin.
   - **Unrelated failure** — pytest errored out (collection error, environment issue, import error, timeout). Don't claim repro success or failure; report the error and recommend a next diagnostic step.

4. **Record artifacts**. The pytest run leaves logs under `tests/instances/<id>/logs/`. List the relevant log files in your reply so the user can attach them to the Jira ticket.

## Output format

One-line headline (`bug reproduced` / `not reproduced` / `unrelated failure`), then a short bulleted summary:
- `select:` the pytest selector
- `exit_code:` the return value
- `evidence:` 1-2 lines from the output that justify the classification
- `logs:` paths to the relevant per-service logs
