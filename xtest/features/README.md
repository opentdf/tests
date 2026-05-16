# xtest/features

Specs for features that touch more than one OpenTDF repo (e.g. platform + Go SDK + Java SDK + JS SDK).

Each `<feature-name>.yaml` captures:

- The feature flag name — the `supports("<name>")` gate string in `xtest/tdfs.py`.
- The Jira ticket driving the work, if any.
- Per-repo todo lists and the shared branch name to use across them.
- The scenario(s) under `xtest/scenarios/` that exercise the feature once each repo's PR lands.

Specs are declarative — they describe intent, not status. PR state (open / merged / CI passing) is auto-discovered from `gh pr list --search "head:<branch>"` per repo, not stored here.

See `CLAUDE.md` in this directory for how Claude Code skills produce and consume these files.
