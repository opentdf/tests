# otdf-adapter

A typed protocol for driving an OpenTDF SDK's command-line client, and one
implementation of it.

`xtest` runs an N x N encrypt/decrypt matrix across SDK clients. Today the
suite reaches each client through a hand-written bash shim
(`xtest/sdk/{go,java,js}/cli.sh`), which translates a positional argv plus a
set of `XT_WITH_*` environment variables into that client's flags and answers
capability questions with `jq` and `awk`. That contract works, but it is
implicit, untyped, and closed: the set of SDKs is a `Literal` in the suite's
own source, so a consumer who wants to put their own client in the matrix has
to edit this repo.

This package makes the contract explicit.

## What is here

| Module | Responsibility |
|--------|----------------|
| `protocol.py` | `SdkAdapter` (a `runtime_checkable` `Protocol`), the frozen `EncryptRequest` / `DecryptRequest` request objects, and `SdkVersion`. |
| `subprocess_cli.py` | `SubprocessCliAdapter` — the only implementation. Builds argv and `XT_WITH_*` env and execs the existing `cli.sh`. |
| `gates.py` | Capability gates as inert data (`MinVersion`, `HelpContains`, `Always`, `Delegate`, `Unprobeable`) and one evaluator. The tables are **empty**. |
| `registry.py` | `otdf.adapters` entry-point discovery: name -> adapter factory. |
| `descriptor.py` | Reads an install's optional `adapter.json`; falls back to the `cli.sh` layout every build uses today. |

## Status

`SubprocessCliAdapter` is a pass-through. It produces byte-identical argv and
environment to the code it replaced, which is asserted directly in
`xtest/test_sdk_commands.py`. No shim has been deleted and no native adapter
exists yet; those are follow-up changes. The gate tables are deliberately
empty, because an empty table means "no entry, ask the shim" — which is
exactly today's behaviour, and lets the ~50 capability answers currently
written in bash be transcribed one row at a time rather than in a flag day.

## Usage

```python
from pathlib import Path

from otdf_adapter import EncryptRequest, load_adapter

adapter = load_adapter("go", "v0.24.0")
adapter.encrypt(
    EncryptRequest(
        src=Path("plain.txt"),
        dst=Path("out.tdf"),
        container="ztdf",
        attributes=("https://example.com/attr/a/value/b",),
    )
)
```

`load_adapter` resolves the name through the `otdf.adapters` entry-point
group. The three built-ins are registered there in this package's own
`pyproject.toml` rather than special-cased, so the extension path is the path
the default run exercises:

```toml
[project.entry-points."otdf.adapters"]
myclient = "my_package.adapters:MyAdapter"
```

An adapter satisfies the protocol structurally — there is no base class to
inherit. It needs `name`, `version_spec`, `encrypt`, `decrypt`, `supports`,
and `version`.

## Two things to know before editing

**`supports` takes a container.** Capability is per-container — nano has no
assertions, ztdf has no ECDSA binding — and the shims cannot express that, so
they answer per-SDK and the caller re-derives the rest. The parameter is
accepted and currently cannot change the answer. It is there so that adding a
per-container gate later does not mean touching every caller a second time.

**`ecwrap` is a flag, not a container.** The suite has a pseudo-container
`ztdf-ecwrap`, which means "a ztdf, produced with an EC wrapping key". It is
split at the boundary: `EncryptRequest.container` is `"ztdf"` and
`EncryptRequest.ecwrap` is `True`. Anything that pattern-matches on
`container` downstream sees a real container name.

## Development

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
uv run pyright         # type-check
uv run pytest -q       # unit tests
```
