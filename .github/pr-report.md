# Opt-in consolidated PR reporting

Reusable `X-Test` callers may set `consolidated-pr-report: true` only when they
provide a trusted central comment publisher. The default is `false`: direct
pull requests, dispatches, schedules, and existing callers retain the current
independent `publish-results` comment behavior and permissions. No new maintaining
team is introduced; repository CODEOWNERS review routing remains unchanged.

Opted-in calls skip the independent comment writer and instead run the read-only
`export-pr-report` job. It uploads `section.json` in artifact
`pr-report-xtest-RUN_ID-ATTEMPT`, retention 14 days, replacing the complete section
on retry. It exports the same `xct` aggregate previously shown by publish-results,
not optional ZIP64 or performance benchmark gates. The capstone `xtest` job and
required-check behavior are unchanged.

The version-1 JSON section contains `section`, plain-text `title`, `status`,
`summary`, optional-content `details`, and caller-owned
`repository`, `pr`, `sha`, `run`, `attempt` identity fields. Reusable workflows
use the caller's GitHub context, run ID, token, and artifact storage. This is
why a platform caller's exported artifact is in **opentdf/platform's run**, not
an independent tests run. The publisher must validate this identity and treat
all exported text as untrusted data, never executable content.

The exporter queries attempt-specific jobs. A rerun without completed `xct`
cells in that attempt exports unavailable rather than reviving prior results.
Artifact links exclude expired artifacts and those created before this attempt.
No missing artifact is interpreted as a clean test run, and no logs are scraped.
This export does not certify that every test cell ran rather than was skipped;
it intentionally preserves the existing aggregate's meaning.

## Rollout and verification

Merge this backward-compatible companion before the platform opt-in caller.
The platform action/publisher is local to platform; this repo introduces no
shared action dependency, service, or custom queue. Suppression is never enabled
by default. The platform's privileged publisher must also be deployed on its
default branch before consolidated reporting operates.

Offline contract tests:

```sh
node --test .github/test-pr-report.cjs
```

These execute the actual inline exporter script with mocked Actions API data,
checking caller identity, current-attempt artifact links, failure/cancellation,
partial reruns, and default-preserving opt-in. The existing lint workflow runs
these tests with Node 24. Live caller integration and CODEOWNERS human review
remain separate rollout gates.
