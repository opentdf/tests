# AGENTS.md

## Project Overview

OpenTDF Tests Repository - Comprehensive testing suite for the OpenTDF (Trusted Data Format) platform. Primary focus is cross-SDK compatibility testing to ensure encryption/decryption works correctly across Go, Java, JavaScript, and Swift implementations.

### Important Documentation
- **[REQUIREMENTS.md](./REQUIREMENTS.md)** - Phase 1 requirements for Test Framework Modernization
- **[DESIGN.md](./DESIGN.md)** - Technical design specification (keep in sync with implementation)
- **[TODO.md](./TODO.md)** - Comprehensive handover document maintaining context between sessions

## Development Environment Setup

### Initial Setup
```bash
# Complete environment setup
./run.py setup

# This will:
# - Create Python virtual environment with uv
# - Install Python dependencies
# - Clone/update platform services
# - Build all SDKs (Go, Java, JavaScript)
# - Build SDK test servers
# - Generate KAS certificates
```

### Python Environment
- Python 3.13.6 required
- Virtual environment managed by `uv`
- Activate before development: `source .venv/bin/activate`

## Project Structure

```
tests/
├── xtest/              # Main cross-SDK compatibility test suite (pytest)
├── work/               # Temporary files and test artifacts (auto-created)
│   └── platform/       # Cloned platform services
├── vulnerability/      # Playwright security tests
├── performance/        # Performance benchmarking
└── run.py             # Main test orchestration script
```

### Key Components
- **xtest/** - Cross-SDK pytest suite validating encryption/decryption
- **work/platform/** - Go-based platform services (KAS, policy, authorization)
- **xtest/sdk/** - SDK servers for testing (Go, Java, JavaScript)
- **xtest/otdfctl/** - Go CLI tool for TDF operations

## Code Style Guidelines

### Python (Primary Test Language)
- Follow PEP 8
- Use type hints where practical
- Fixtures for shared test resources
- Descriptive test names: `test_<feature>_<scenario>_<expected_result>`

### Go SDK Server
- Standard Go formatting (`go fmt`)
- Error handling: return errors, don't panic
- Use structured logging

### Java SDK Server
- Follow Spring Boot conventions
- Use SLF4J for logging
- Prefer `var` for local variables with obvious types

### JavaScript SDK Server
- ES6 modules
- Async/await over callbacks
- Express.js middleware patterns

## Testing Instructions

### Quick Start
```bash
# Run all tests with parallel execution (recommended)
./run.py test

# Run specific test suite
pytest xtest/test_tdfs.py -v

# Test specific SDKs
pytest --sdks go java js

# Test specific formats
pytest --containers nano ztdf
```

### Test Categories
1. **Container Formats**: nano (NanoTDF), ztdf (TDF3), ztdf-ecwrap
2. **SDKs**: Go, Java, JavaScript, Swift
3. **Policies**: ABAC, assertions, metadata
4. **Scenarios**: Encryption/decryption, policy enforcement, multi-KAS

### Key Test Files
- `test_tdfs.py` - Core TDF3 format testing
- `test_nano_roundtrip.py` - NanoTDF cross-SDK compatibility
- `test_abac_roundtrip.py` - Attribute-based access control
- `test_assertions.py` - Assertion and metadata handling

### Debugging Tests
```bash
# Verbose output
pytest -v

# Keep test artifacts for debugging
pytest --keep-artifacts

# Inspect TDF files
xtest/otdfctl inspect file.tdf

# Check platform logs
docker compose -f work/platform/docker-compose.yaml logs -f
```

## Development Workflows

### Building Components
```bash
# Build platform services
cd work/platform && make build

# Build all SDKs
cd xtest/sdk && make all

# Build individual SDK servers
cd xtest/sdk/go/server && go build
cd xtest/sdk/java/server && mvn package
cd xtest/sdk/js && npm install
```

### Running Platform Services
```bash
cd work/platform
go run ./service start
go run ./service provision keycloak  # Setup auth
```

## Temporary File Management

The test suite uses pytest's temporary directory management:

- **`tmp_path`** fixture: Function-scoped, isolated per test
- **`work_dir`** fixture: Session-scoped, for cross-test artifacts
- **Base directory**: `work/` at project root (IDE-visible)
- **Cleanup**: Failed test dirs retained for debugging (3 runs max)
- **Parallel safety**: Full isolation with `pytest-xdist`

Example structure:
```
work/
├── test_abac_test_key_mapping0/  # Per-test directory
├── test_tdfs_test_roundtrip1/
└── opentdf_work0/                # Session-scoped shared
```

## Configuration

- **pytest**: Configured in `pyproject.toml` under `[tool.pytest.ini_options]`
- **Platform**: Environment variables in `test.env`
- **OpenTDF**: Configuration in `opentdf.yaml`

## Important Context for AI Agents

### Multi-SDK Testing
Tests verify the same encryption/decryption scenarios work across all SDK implementations. When making changes:
1. Check cross-SDK compatibility
2. Validate both encryption and decryption paths
3. Test multiple container formats
4. Ensure BATS tests pass for end-to-end workflows

### Fixture System
pytest fixtures provide:
- KAS keys and certificates
- Namespaces and attributes
- Policy configurations
- Temporary directories

### Dependencies
- Platform services must be running (via Docker Compose)
- Keycloak provides OIDC authentication
- Each SDK has its own build requirements

### Common Issues
- **Import errors**: Run `./run.py setup` to rebuild SDKs
- **Connection refused**: Ensure platform services are running
- **Test isolation**: Use appropriate fixtures for temp files
- **Parallel test failures**: Check for shared state violations

## Contribution Guidelines

### Before Committing
1. Run tests: `./run.py test`
2. Update DESIGN.md if architecture changes
3. Update TODO.md with session context
4. Ensure all SDK servers build successfully

### Commit Messages
Format: `[component] Brief description`

Examples:
- `[xtest] Add cross-SDK encryption test for large files`
- `[sdk/go] Fix TDF decryption error handling`
- `[framework] Update pytest fixtures for parallel execution`

### Pull Request Process
1. All tests must pass
2. Document breaking changes
3. Update relevant .md files
4. Ensure .gitignore covers new artifacts

## Agent-Specific Instructions

### Do's
- Always run `./run.py setup` after major changes
- Keep DESIGN.md in sync with implementation
- Use existing fixtures for test resources
- Follow established patterns in existing tests
- Test across multiple SDKs when modifying core functionality

### Don'ts
- Don't hardcode paths - use fixtures
- Don't skip the setup phase
- Don't modify generated SDK source in `src/` directories
- Don't commit build artifacts (check .gitignore)
- Don't assume single SDK - test cross-compatibility

### When Stuck
1. Check TODO.md for context
2. Review REQUIREMENTS.md for goals
3. Examine existing tests for patterns
4. Use `pytest --fixtures` to understand available resources
5. Inspect logs in `work/platform/` for service issues