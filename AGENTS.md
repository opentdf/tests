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

### Custom pytest Options
- `--sdks`: Specify which SDKs to test (go, java, js)
- `--containers`: Specify TDF container types (ztdf, ztdf-ecwrap)
- `--no-audit-logs`: Disable audit log assertions globally
- Environment variables:
  - `PLATFORMURL`: Platform endpoint (default: http://localhost:8080)
  - `OT_ROOT_KEY`: Root key for key management tests
  - `SCHEMA_FILE`: Path to manifest schema file
  - `DISABLE_AUDIT_ASSERTIONS`: Set to `1`, `true`, or `yes` to disable audit log assertions

### Audit Log Assertions

**IMPORTANT**: Audit log assertions are **REQUIRED by default**. Tests will fail during setup if KAS log files are not available.

**Why Required by Default:**
- Ensures comprehensive test coverage of audit logging functionality
- Catches regressions in audit event generation
- Validates clock skew handling between test machine and services

**Disabling Audit Assertions:**

Only disable when:
- Running tests without services (unit tests only)
- Debugging non-audit-related issues
- CI environments where audit logs aren't available

To disable, use either:
```bash
# Environment variable (preferred for CI)
DISABLE_AUDIT_ASSERTIONS=1 uv run pytest --sdks go -v

# CLI flag (preferred for local dev)
uv run pytest --sdks go --no-audit-logs -v
```

**Setting Up Log Files:**

Audit log collection requires KAS log files. Set paths via environment variables:
```bash
export PLATFORM_LOG_FILE=/path/to/platform.log
export KAS_ALPHA_LOG_FILE=/path/to/kas-alpha.log
export KAS_BETA_LOG_FILE=/path/to/kas-beta.log
# ... etc for kas-gamma, kas-delta, kas-km1, kas-km2
```

Or ensure services are running with logs in `../../platform/logs/` (auto-discovered).

- Use semantic commit/PR titles (enforced by CI): `feat(xtest): ...`, `fix(vulnerability): ...`, `docs: ...` (types: `fix|feat|chore|docs`; scopes include `xtest`, `vulnerability`, `go`, `java`, `web`, `ci`).
- DCO sign-off is required: `git commit -s -m "feat(xtest): ..."` (see `CONTRIBUTING.md`).
- PRs should include a clear description, linked issue (if any), and relevant logs/screenshots for test failures; reviewers are defined in `CODEOWNERS`.

