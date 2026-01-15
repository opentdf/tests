# Repository Guidelines

## Project Structure & Module Organization

- `xtest/`: Cross-client compatibility test harness (Python + `pytest`), with fixtures in `xtest/fixtures/` and golden data in `xtest/golden/`.
- `xtest/sdk/`: Helper scripts and Makefiles for checking out/building SDKs under test (e.g., `xtest/sdk/scripts/checkout-all.sh`, `cd xtest/sdk && make`).
- `vulnerability/`: Playwright-based security regression tests (`vulnerability/tests/`).
- `.github/workflows/`: CI workflows (lint/type-check, xtest matrix runs, vulnerability runs).

## Build, Test, and Development Commands

- Enter the dev environment: `devbox shell` (installs Python/JDK/Node per `devbox.json`).
- Install xtest deps: `cd xtest && uv sync` (or `uv sync --extra dev` for dev tools)
- Run xtest: `cd xtest && uv run pytest`
  - Focus a subset: `uv run pytest --sdks "go js" --focus go` (see `xtest/conftest.py` options)
  - HTML report: `uv run pytest --html tmp/test-report.html --self-contained-html`
- Build SDK CLIs (after checkout): `cd xtest/sdk && make`
- Run vulnerability tests: `cd vulnerability && npm ci && npm test` (requires a running platform; see `README.md` and `vulnerability/README.md`).

## Coding Style & Naming Conventions

- Python code in `xtest/` uses 4-space indentation, `snake_case`, and `pytest`-style fixtures.
- CI enforces these checks in `xtest/`:
  - `ruff check` and `ruff format --check`
  - `pyright`
  - Local equivalent: `cd xtest && uv sync --extra dev && uv run ruff check . && uv run ruff format --check . && uv run pyright`

## Testing Guidelines

- `pytest` tests live in `xtest/test_*.py`; add new fixtures under `xtest/fixtures/`.
- Tests assume a platform backend is reachable (Docker + Keycloak). Use `xtest/test.env` as a template:
  - `cd xtest && set -a && source test.env && set +a`

## Commit & Pull Request Guidelines

- Use semantic commit/PR titles (enforced by CI): `feat(xtest): ...`, `fix(vulnerability): ...`, `docs: ...` (types: `fix|feat|chore|docs`; scopes include `xtest`, `vulnerability`, `go`, `java`, `web`, `ci`).
- DCO sign-off is required: `git commit -s -m "feat(xtest): ..."` (see `CONTRIBUTING.md`).
- PRs should include a clear description, linked issue (if any), and relevant logs/screenshots for test failures; reviewers are defined in `CODEOWNERS`.

