# xtest - Agent Guide

The cross-client integration test suite. pytest with custom options that
fan out tests across SDK CLIs (`go`, `java`, `js`) and TDF container types.

For env-variable setup, audit-log details, and common-failure recipes,
see the root `AGENTS.md`. This guide focuses on test authoring and the
fixture system.

## Layout

| Path | Contents |
|------|----------|
| `test_*.py` | Test modules. One per concern: `test_tdfs.py` (core roundtrip), `test_abac.py` (ABAC), `test_legacy.py` (golden TDFs), `test_policytypes.py`, `test_self.py`, `test_audit_logs.py`, `test_pqc.py`. |
| `conftest.py` | `pytest_addoption` + the encrypt/decrypt SDK parametrization. Defines `--sdks`, `--sdks-encrypt`, `--sdks-decrypt`, `--containers`, `--no-audit-logs`. |
| `fixtures/` | Module-scoped pytest fixtures: `attributes.py`, `keys.py`, `audit.py`, `assertions.py`, `kas.py`, `encryption.py`, `obligations.py`. |
| `tdfs.py` | SDK abstraction layer — wraps the `cli.sh` shims under `sdk/<lang>/dist/<version>/`. |
<<<<<<< HEAD
| `sdk/{go,java,js}/dist/<version>/` | SDK CLI builds. Installed by `otdf-sdk-mgr install` (see `../otdf-sdk-mgr/AGENTS.md`). |
| `test.env` | Default endpoint and client-credential env vars. Source with `set -a && source test.env && set +a`. |

## Custom pytest Options (defined in `conftest.py`)

| Option | Purpose |
|--------|---------|
| `--sdks "go java js"` | Which SDKs to use for both encrypt and decrypt. |
| `--sdks-encrypt`, `--sdks-decrypt` | Asymmetric encrypt/decrypt SDK selection (use when reproducing cross-SDK interop bugs). |
| `--containers ztdf ztdf-ecwrap` | Which TDF container types to exercise. |
| `--no-audit-logs` | Skip audit-log assertions for this run. CLI equivalent of `DISABLE_AUDIT_ASSERTIONS=1`. |

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
