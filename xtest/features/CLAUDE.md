# Agent guidance for xtest/features

This directory is owned by two skills:

- **`feature-design`** drafts new spec files here from a Jira ticket (or free-form description) using propose-then-iterate authoring. It also writes the tests-side artifacts that have to land first: the `feature_type` entry in `xtest/tdfs.py`, the scenario under `xtest/scenarios/`, and (if needed) a draft pytest.
- **`feature-orchestrate`** reads spec files and fans out per-cell subagents (one `claude -p` per cell, each in its own git worktree at `~/Documents/GitHub/worktrees/<JIRA-KEY>-<cell-key>/`) that implement the cell's work and open draft PRs. Cells run in parallel within each dependency wave.

When you see a `xtest/features/<name>.yaml` referenced:

- It is canonical for the feature's flag name, scope, per-cell todos, and `depends_on` edges.
- It is NOT canonical for status — query `gh pr list --search "head:<branch>"` per cell.

Don't hand-author spec files in this directory unless you've also done what `feature-design` would do (add the entry to `feature_type` in `xtest/tdfs.py`, generate the scenario + draft test). Those side effects keep the spec consistent with the tests it depends on.
