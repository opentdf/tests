---
name: scenario-from-bug-report
description: Pull a Jira bug into context (via `acli jira workitem view`) and turn it into an xtest/scenarios/<JIRA-KEY>.yaml manifest, optionally drafting xtest/bug_<jira_key>_test.py when no existing pytest covers it. Use when the user mentions a Jira issue key like DSPX-1234 (or another [PROJECT]-[NUMBER] format) and asks for a reproducer.
allowed-tools: Bash, Read, Write, Grep, Glob
---

# scenario-from-bug-report

Bugs are tracked in Jira. The user will reference an issue by its key in the form `[PROJECT]-[NUMBER]` — examples: `DSPX-3302`, `DSPX-1234`. `DSPX` is the current project's prefix but the prefix can change (e.g. `OPS-`, `SDK-`); accept any short uppercase prefix.

You produce two artifacts the rest of the toolchain consumes:

1. `xtest/scenarios/<jira-key-lowercased>.yaml` — validated against `otdf_sdk_mgr.schema.Scenario`.
2. (Optional) `xtest/bug_<jira_key_lowercased>_test.py` — only if no existing xtest pytest already exercises the bug.

The Jira key also becomes the working **branch name** (`<JIRA-KEY>-repro` if a fresh branch is needed) and the scenario file's `metadata.id`.

## Step 1 — Pull the Jira issue into context

Always start by fetching the full issue content. Don't proceed on the user's free-text summary alone — the issue body has the version pins and reproduction details you need.

```bash
acli jira workitem view <JIRA-KEY> --fields '*all' --json
acli jira workitem comment list <JIRA-KEY>
```

The first command's JSON output includes `summary`, `description`, `status`, and labels. The second lists comments. Extract:

- The **summary** (becomes scenario `metadata.title`).
- The **description** (read carefully — version numbers, KAS topology, container types, and feature flags typically live here).
- Recent **comments** — reproductions and "what changed" notes often appear in comments rather than the original description.

If the issue references attached logs, screenshots, or linked PRs, list them via `acli jira workitem attachment list <JIRA-KEY>` and `acli jira workitem link list <JIRA-KEY>` and mention them in your reply.

**Permitted Jira writes**: only `acli jira workitem comment create <JIRA-KEY> ...` (to post a reproduction-status update if the user asks). Everything else — `edit`, `transition`, `assign`, `archive`, `delete`, `link create`, `watcher add` — is explicitly disallowed by the plugin's permissions; if the user wants those actions, instruct them to run the command themselves.

## Step 2 — Identify the scenario inputs

From the issue text, extract:

- **Encrypt-side SDKs** — which SDKs *create* the TDF? (`go`, `java`, `js`). Pin versions.
- **Decrypt-side SDKs** — which SDKs *consume* the TDF? Pin versions.
- **Platform version** — git tag like `v0.9.0` (resolves to the `service/v0.9.0` tag in `opentdf/platform`).
- **KAS topology** — which KAS instances must be running (`alpha`, `beta`, `gamma`, `delta`, `km1`, `km2`) and whether any need a different pinned version than the platform.
- **Container type** — `ztdf`, `ztdf-ecwrap`, `nano`, or `nano-with-policy`.
- **Feature flags** — e.g. `ec_tdf_enabled`.
- **Expected vs actual behavior** — copy concise prose from the issue.

If anything is ambiguous in the Jira issue, ask the user — don't guess at versions.

## Step 3 — Pick the id and (optionally) the branch

- `metadata.id = <jira-key-lowercased>` — e.g. `DSPX-3302` → `dspx-3302`.
- Scenario file path: `xtest/scenarios/<jira-key-lowercased>.yaml`.
- If you need a new git branch, propose `<JIRA-KEY>-repro` (e.g. `DSPX-3302-repro`) and let the user confirm before switching.

## Step 4 — Search for an existing pytest

```bash
grep -rn "<key_term>" xtest/test_*.py
```

Likely candidates: `test_tdfs.py` (roundtrip), `test_abac.py` (ABAC), `test_legacy.py` (golden), `test_pqc.py`. If a test already asserts the relevant behavior, reuse it — only the scenario changes, not the code.

## Step 5 — Write `xtest/scenarios/<id>.yaml`

Exact field shape (the schema rejects unknown fields):

```yaml
apiVersion: opentdf.io/v1alpha1
kind: Scenario
metadata:
  id: <jira-key-lowercased>
  title: "<Jira summary>"
  created: <YYYY-MM-DD>
instance:
  metadata: { name: <jira-key-lowercased> }
  platform: { dist: <platform_version> }
  ports: { base: <pick free base; 8080 if first, +1000 per concurrent scenario> }
  kas:
    <name>: { dist: <version>, mode: standard }   # or mode: key_management
sdks:
  encrypt:
    <sdk>: { version: <version> }
  decrypt:
    <sdk>: { version: <version> }
suite:
  select: "<pytest selector, e.g. xtest/test_tdfs.py::test_tdf_roundtrip>"
  containers: <ztdf|ztdf-ecwrap|nano|nano-with-policy>
  # markers: "not slow"
  # extra_args: ["--no-audit-logs"]
expected: "<expected behavior copied from Jira>"
actual:   "<actual behavior copied from Jira>"
```

Validate before reporting success:

```bash
uv run python -m otdf_sdk_mgr.schema validate xtest/scenarios/<id>.yaml
```

## Step 6 — If no existing test fits

Draft `xtest/bug_<id>_test.py` using the `encrypt_sdk` / `decrypt_sdk` fixtures (pattern: `xtest/test_tdfs.py`). Surface the new file in your reply for the user to review — never silently land assertions.

## Notes

- `sdks.encrypt` and `sdks.decrypt` map to xtest's `--sdks-encrypt` / `--sdks-decrypt`. After PR #446 those pytest options take `sdk@version` specifiers like `go@v0.24.0`, `go@main`, or `go@*`. **Do NOT write those tokens in the YAML** — write a normal `{ version: lts }` (or any version string `otdf-sdk-mgr resolve` accepts: `v0.24.0`, `main`, an SDK-specific SHA, etc.). The `scenario-up` skill runs `otdf-sdk-mgr install scenario`, which records the resolved dist directory names in `xtest/scenarios/<id>.installed.json`; the bridge layers (`otdf-local scenario run` and pytest's `--scenario` default in `xtest/conftest.py`) read that file to emit the right `sdk@<dist>` tokens. If you forget the install step, those commands fail with `<id>.installed.json not found — run otdf-sdk-mgr install scenario first`.
- List the same SDK in both `encrypt` and `decrypt` maps to reproduce xtest's legacy "all pairs" mode. Listing it on only one side keeps the scenario focused (a→b without b→a).
- `instance.platform.dist` and each `kas.<name>.dist` need `otdf-sdk-mgr install scenario <path>` (or `install release platform:<dist>`) to have built the binary first. `scenario-up` handles that downstream.
- One-line summary when done: report the scenario path, the new test file (if any), and the Jira link `https://virtru.atlassian.net/browse/<JIRA-KEY>` so the user can cross-reference.
