# xtest/features

Specs for features that touch more than one OpenTDF repo (e.g. platform + Go SDK + Java SDK + JS SDK).

Each `<feature-name>.yaml` captures:

- The feature flag name — the `supports("<name>")` gate string in `xtest/tdfs.py`.
- The Jira ticket driving the work, if any.
- A list of *cells of effort*, each with a target repo (`path:`), a branch, a todo list, and an optional `depends_on:` edge to other cells. A single feature can have multiple cells in the same repo (e.g. `platform-proto`, `platform-service`, `platform-go-sdk` all targeting `platform`), which the orchestrator runs in separate git worktrees.
- The scenario(s) under `xtest/scenarios/` that exercise the feature once each cell's PR lands.

Specs are declarative — they describe intent, not status. PR state (open / merged / CI passing) is auto-discovered from `gh pr list --search "head:<branch>"` per repo, not stored here.

See `CLAUDE.md` in this directory for how Claude Code skills produce and consume these files.
