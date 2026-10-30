# xtest - Agent Guide

The cross-client integration test suite. pytest with custom options that
fan out tests across SDK CLIs (`go`, `java`, `js`) and TDF container types.

For env-variable setup and audit-log details, see the root `AGENTS.md`.
Common-failure recipes are in `../.claude/skills/xtest-troubleshooting/SKILL.md`.
This guide focuses on test authoring and the fixture system.

## Layout

| Path | Contents |
|------|----------|
| `perf/` | Paired A/B performance regression benchmarks (opt-in via `--bench`). **Read `perf/README.md` before changing anything in here** — the design decisions fail silently when undone. |
| `sdk/{go,java,js}/dist/<version>/` | SDK CLI builds. Installed by `otdf-sdk-mgr install` (see `../otdf-sdk-mgr/AGENTS.md`). |
| `test.env` | Default endpoint and client-credential env vars. Source with `set -a && source test.env && set +a`. |

## Custom pytest Options (defined in `conftest.py`)

| Option | Purpose |
|--------|---------|
| `--sdks "go java js"` | Which SDKs to use for both encrypt and decrypt. |
| `--sdks-encrypt`, `--sdks-decrypt` | Asymmetric encrypt/decrypt SDK selection (use when reproducing cross-SDK interop bugs). |
| `--containers ztdf` | Which TDF container types to exercise. |
| `--no-audit-logs` | Skip audit-log assertions for this run. CLI equivalent of `DISABLE_AUDIT_ASSERTIONS=1`. |
| `--sizes small,chunky` | Which payload sizes to parametrize over (`small` 128 B, `chunky` 5 MiB, `medium` 2.1 GiB, `large` 5 GiB). Defaults to `small`. Every extra size fans out every test taking `pt_file`. `--large` is a deprecated alias for `small,large`. |

## Environment Variables

Beyond the repo-wide ones in `../AGENTS.md`:

| Variable | Purpose |
|----------|---------|
| `XT_TMP_DIR` | Root for generated fixtures and ciphertexts (default `tmp/`). Point at a large volume for `medium`/`large` runs. |
| `XT_FORCE_SUPPORTS` | Comma-separated features to treat as supported, bypassing the `cli.sh supports` gate. For evaluating a fix before it releases — see below. Unknown names raise, as do platform-only ones (`PLATFORM_ONLY_FEATURES` in `tdfs.py`). |
| `XT_FORCE_PLATFORM_SUPPORTS` | Comma-separated platform features to treat as supported. Independent of SDK overrides; does not enable service configuration. Unknown names raise. In CI, use `force-platform-supports`. See `README.md` for usage. |

## Evaluating an unreleased fix: `XT_FORCE_SUPPORTS`

`SDK.supports(feature)` answers from the `supports` case statements in
`xtest/sdk/{go,java,js}/cli.sh` — **in this repo, not in the SDK repos**. Most
cases are version gates, so a build from an unmerged branch reports the last
*released* version and answers "no" for precisely the fix you are trying to
evaluate. The cell then skips and the run is green without having tested
anything.

`XT_FORCE_SUPPORTS` short-circuits that:

```bash
otdf-sdk-mgr install tip --ref pr:396 java     # pr:N works on install
XT_FORCE_SUPPORTS=chunky uv run pytest test_tdfs.py --sdks "js java" -v
```

It applies to every SDK in the run — to force one side only, narrow with
`--sdks-encrypt` / `--sdks-decrypt`. An unrecognised feature name raises rather
than being ignored, since a silently-ignored typo is indistinguishable from a
clean run. In CI, pass `force-supports` to the `X-Test` workflow dispatch.

A platform-only feature — one in `PLATFORM_ONLY_FEATURES` in `xtest/tdfs.py`,
such as `kas_uri_from_kao` — raises here too, and directs you to
`XT_FORCE_PLATFORM_SUPPORTS`.

Note `versions resolve` (which backs the workflow's `*-ref` inputs) does **not**
accept the `pr:N` shorthand — pass a branch name there instead.

## Authoring a New Test

1. Pick the right module — group by concern, not by SDK.
2. Use the existing fixtures wherever possible — they're already parametrized
   by `--sdks` / `--containers`. Add a new fixture in `fixtures/` only if
   the data is reused across modules.
3. If your test needs to skip in certain SDK combos, use
   `pytest.skip(...)` with a clear reason — the parametrization will run
   it once per combo, so the skip message tells the next reader why.
4. Audit-log assertions are **on by default**. If your test does not
   exercise KAS, mark it with the existing `no_audit_logs` pattern; do
   not silently drop the fixture.

## Audit-Log Fixture Quick Reference

`audit_logs` (in `fixtures/audit.py`) reads KAS log files (paths from
`PLATFORM_LOG_FILE` / `KAS_*_LOG_FILE` env vars, or auto-discovered under
`../platform/logs/`). It fails setup loudly if the logs aren't reachable.

- **Local dev, no services**: pass `--no-audit-logs` on the pytest command line.
- **CI without services**: set `DISABLE_AUDIT_ASSERTIONS=1` (preferred over
  the flag in CI configs because it survives shell wrappers).
- **Real integration runs**: leave both unset. Failure to find logs is a
  real signal that the local env is misconfigured.

## SDK CLI Abstraction (`tdfs.py`)

Every SDK exposes the same operations (`encrypt`, `decrypt`, etc.) via
`tdfs.py`. When a test fails for one SDK but not another, the divergence
is usually in either the CLI shim (`sdk/<lang>/dist/<version>/cli.sh`) or
the SDK's manifest emission, not the test. Reproduce manually with:

```bash
echo "hello" > /tmp/in.txt
sdk/go/dist/main/cli.sh encrypt /tmp/in.txt /tmp/out.tdf --attr https://example.com/attr/foo/value/bar
sdk/go/dist/main/cli.sh decrypt /tmp/out.tdf /tmp/out.txt
```

## Before Committing

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
```

See the root `AGENTS.md` ("Before Committing Python Changes") for why
`uvx` is the wrong invocation for pyright.
