# otdf-adapter - Agent Guide

A typed protocol for driving an OpenTDF SDK client, plus `SubprocessCliAdapter`,
which implements it by exec'ing the existing `xtest/sdk/{go,java,js}/cli.sh`
shims. Overview and usage: [README.md](README.md).

Consumed by `xtest` through an editable path dependency declared in
`xtest/pyproject.toml` under `[tool.uv.sources]`. An edit here takes effect in
`xtest` without a re-sync.

## The Invariant

`SubprocessCliAdapter` must emit **byte-identical** argv and `XT_WITH_*`
environment to what `xtest/tdfs.py` emitted before it existed. That is what
makes the migration safe without a live platform to test against.

`xtest/test_sdk_commands.py` is the characterization suite that enforces it.
Every assertion in it predates this package and was reproduced unchanged; only
the call shape moved. If you change what argv or env this adapter produces,
you are changing SDK behaviour, and that test failing is the point — do not
update the expectation to match the new output without a reason that belongs
in the commit message.

Two consequences worth stating, because both look like bugs:

- **`XT_WITH_KAS_ALLOWLIST` is misspelled relative to the shims**, which all
  read `XT_WITH_KAS_ALLOW_LIST` (`sdk/go/cli.sh`, `sdk/java/cli.sh`,
  `sdk/js/cli.sh`). The `kasallowlist=` option has therefore never reached any
  SDK. It is preserved verbatim, and recorded in `KNOWN_SHIM_MISMATCH` in
  `subprocess_cli.py`, because fixing it here would change behaviour under
  cover of a refactor. Fix it in its own change, where the matrix result can
  be read as the evidence.
- **`policy_mode` and `ecdsa_binding` are accepted and ignored.** They are on
  the request objects because callers pass them; no shim consumes them today.

## Layout

| Module | Responsibility |
|--------|----------------|
| `protocol.py` | `SdkAdapter` Protocol, `EncryptRequest` / `DecryptRequest`, `SdkVersion`. No I/O, no imports from the rest of the package. |
| `subprocess_cli.py` | The only implementation. argv + env construction, version and help probes, `supports`. |
| `gates.py` | Gate dataclasses and `evaluate`. Inert data — must not run a subprocess. |
| `registry.py` | `otdf.adapters` entry-point lookup. |
| `descriptor.py` | `adapter.json`, with a fallback to the `cli.sh` layout. |

`protocol.py` is imported by everything else and imports none of it. Keep it
that way; it is what lets a consumer's adapter depend on the protocol without
dragging in the subprocess machinery.

## Command Builders Are Pure

`encrypt_command` / `decrypt_command` return a `Command` (an `(argv, env)`
NamedTuple) and touch nothing else: no filesystem, no environment mutation, no
caching. `TestDeterminism` in `xtest/test_sdk_commands.py` asserts this,
including that a caller-owned list handed in as `attributes` cannot later
mutate a command that was already built. Purity is why the golden-argv tests
can exist at all — keep the building and the running separate.

`encrypt_command` returns a two-tuple because `xtest/fixtures/bench.py`
unpacks it as one. `Command` is a NamedTuple so it stays unpackable while
having names.

## Gate Tables Are Empty On Purpose

`GATES` in `gates.py` is `{}`. `SubprocessCliAdapter.supports` consults it
first and falls back to the shim's `supports` verb when there is no entry — so
an empty table is exactly today's behaviour, and the ~50 case arms in the
three shims can be transcribed one row at a time, each row reviewable against
the bash it replaces. Do not populate a table and delete the corresponding
bash in the same change.

## Before Committing

Run from this directory:

```bash
uv run ruff check .    # lint — must pass
uv run ruff format .   # auto-format
uv run pyright         # type-check — must pass
uv run pytest -q       # unit tests
```

Then, from `../xtest`, the characterization suite:

```bash
uv run --frozen --no-sync pytest -q test_sdk_commands.py
```

Use `uv run`, **not `uvx`** — `uvx` strips the project venv, so pyright
reports every project import as unresolved.

Note the `--no-sync` in the `xtest` invocation. `otdf-adapter` reaches `xtest`
as an editable path dependency, and `uv run --no-build` refuses to install it
(it has no wheel to install, by design). `xtest`'s CI job therefore pins
resolution at the `uv sync --frozen` step instead and runs with `--no-sync`.

## Testing Without an SDK

Nothing in this package's own test suite needs a real SDK or a platform. The
tests write a stub `cli.sh` into `tmp_path` and `chdir` to it. That is the
reason gates are data rather than code: a transcription of fifty capability
rules can be checked against a stub, which is the only way a change that size
ever actually gets reviewed.
