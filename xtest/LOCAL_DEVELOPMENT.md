# Running xtest Locally with Audit Logs

This guide explains how to run xtest locally with the same audit log collection that runs in CI.

## Quick Start

### Prerequisites

1. Platform repository checked out as sibling:
   ```
   github.com/opentdf/
   ├── platform/
   └── tests/
   ```

2. Platform dependencies running:
   ```bash
   cd ../../platform
   docker compose up -d --wait
   go run ./service provision keycloak
   go run ./service provision fixtures
   ```

3. Platform started with log capture:
   ```bash
   LOG_LEVEL=audit LOG_TYPE=json test/local/start-platform.sh
   ```

### Run Tests

Use the `run-local.sh` wrapper which automatically:
- Verifies platform is running
- Starts additional KAS instances (alpha, beta, gamma, delta, km1, km2)
- Exports log file paths as environment variables
- Runs pytest with audit log collection enabled
- Cleans up KAS instances on exit

```bash
# Run all tests
./run-local.sh

# Run specific test file
./run-local.sh test_abac.py

# Run with pytest options
./run-local.sh test_abac.py -v -k test_rewrap

# Run with focus on specific SDK
./run-local.sh --focus go test_tdfs.py
```

## Manual Setup (Without Wrapper)

If you prefer more control or want to start services individually:

### 1. Start Platform

```bash
cd ../../platform
LOG_LEVEL=audit LOG_TYPE=json test/local/start-platform.sh
```

This outputs:
```
Platform is ready!
Log file path: /path/to/platform/logs/kas-main.log
Export for xtest: export PLATFORM_LOG_FILE="/path/to/platform/logs/kas-main.log"
```

### 2. Start Additional KAS Instances (Optional)

Only needed for multi-KAS tests (e.g., `test_abac.py`):

```bash
cd ../../platform

# Standard KAS instances
LOG_LEVEL=audit LOG_TYPE=json test/local/start-kas.sh alpha 8181
LOG_LEVEL=audit LOG_TYPE=json test/local/start-kas.sh beta 8282
LOG_LEVEL=audit LOG_TYPE=json test/local/start-kas.sh gamma 8383
LOG_LEVEL=audit LOG_TYPE=json test/local/start-kas.sh delta 8484

# Key management KAS instances
LOG_LEVEL=audit LOG_TYPE=json test/local/start-kas.sh km1 8585 \
  --key-management=true \
  --root-key=Sk5OQ1dLQWExRkMyelFWdz09

LOG_LEVEL=audit LOG_TYPE=json test/local/start-kas.sh km2 8686 \
  --key-management=true \
  --root-key=U2s1T1EzZExRV0V4UmtNMmVsRldkejA5
```

### 3. Export Log File Paths

```bash
export PLATFORM_DIR="$(cd ../../platform && pwd)"
export PLATFORM_LOG_FILE="${PLATFORM_DIR}/logs/kas-main.log"
export KAS_ALPHA_LOG_FILE="${PLATFORM_DIR}/logs/kas-alpha.log"
export KAS_BETA_LOG_FILE="${PLATFORM_DIR}/logs/kas-beta.log"
export KAS_GAMMA_LOG_FILE="${PLATFORM_DIR}/logs/kas-gamma.log"
export KAS_DELTA_LOG_FILE="${PLATFORM_DIR}/logs/kas-delta.log"
export KAS_KM1_LOG_FILE="${PLATFORM_DIR}/logs/kas-km1.log"
export KAS_KM2_LOG_FILE="${PLATFORM_DIR}/logs/kas-km2.log"
```

### 4. Run pytest

```bash
cd tests/xtest
pytest test_abac.py -v
```

### 5. Cleanup

```bash
# Kill all KAS processes
kill $(lsof -t -i:8080) $(lsof -t -i:8181) $(lsof -t -i:8282) \
     $(lsof -t -i:8383) $(lsof -t -i:8484) $(lsof -t -i:8585) \
     $(lsof -t -i:8686)
```

## Environment Variables

### Required

- `PLATFORM_DIR` - Path to platform repository (default: `../../platform`)

### Optional (for audit log collection)

- `PLATFORM_LOG_FILE` - Path to main platform/KAS log file
- `KAS_ALPHA_LOG_FILE` - Path to alpha KAS log file
- `KAS_BETA_LOG_FILE` - Path to beta KAS log file
- `KAS_GAMMA_LOG_FILE` - Path to gamma KAS log file
- `KAS_DELTA_LOG_FILE` - Path to delta KAS log file
- `KAS_KM1_LOG_FILE` - Path to km1 KAS log file
- `KAS_KM2_LOG_FILE` - Path to km2 KAS log file

If these are not set, the framework will:
1. Try to find log files in `${PLATFORM_DIR}/logs/`
2. Fall back to docker compose logs (if available)
3. Disable audit log collection if neither works

### Configuration

- `LOG_LEVEL` - Log level for services (audit, debug, info, warn, error). Default: `audit`
- `LOG_TYPE` - Log format (text, json). Default: `json` (recommended for audit logs)
- `START_KAS_INSTANCES` - Space-separated KAS names to start. Default: `"alpha beta gamma delta km1 km2"`
- `SKIP_KAS_START` - Set to `"true"` to skip starting KAS instances with run-local.sh

## Using Audit Logs in Tests

### Basic Example

```python
def test_rewrap(encrypt_sdk, decrypt_sdk, pt_file, tmp_dir, audit_logs):
    """Test that rewrap operations are logged."""
    # Encrypt file
    ct_file = encrypt_sdk.encrypt(pt_file, ...)

    # Mark timestamp before operation we want to assert on
    audit_logs.mark("before_decrypt")

    # Perform operation
    decrypt_sdk.decrypt(ct_file, ...)

    # Assert on logs
    audit_logs.assert_contains(
        r"rewrap.*200",
        min_count=1,
        since_mark="before_decrypt"
    )
```

### Advanced Assertions

```python
# Assert exact count
audit_logs.assert_count(r"rewrap request", expected_count=2, since_mark="start")

# Assert within time window
audit_logs.assert_within_time(r"rewrap.*200", reference_time=start_time, window_seconds=5)

# Query without asserting
matching_logs = audit_logs.get_matching_logs(r"entityId.*e-[a-f0-9]+")

# Filter by service
audit_logs.assert_contains(r"rewrap", service="kas-alpha", min_count=1)
```

### Opt-Out of Audit Logs

```python
@pytest.mark.no_audit_logs
def test_without_logs():
    """This test won't collect audit logs."""
    pass
```

## Viewing Logs

### Real-time

```bash
# Platform logs
tail -f ../../platform/logs/kas-main.log

# Specific KAS
tail -f ../../platform/logs/kas-alpha.log

# All logs
tail -f ../../platform/logs/*.log
```

### On Test Failure

Audit logs are automatically written to `tmp/audit-logs/` when tests fail:

```bash
ls -la tmp/audit-logs/
cat tmp/audit-logs/test_abac_py_test_one_kas_rewrap_fails_go_go_ztdf.log
```

## Troubleshooting

### "Platform is not running"

Start the platform:
```bash
cd ../../platform
LOG_LEVEL=audit LOG_TYPE=json test/local/start-platform.sh
```

### "Port already in use"

Find and kill the process:
```bash
lsof -t -i:8080 | xargs kill
```

### "Platform log file not found"

Make sure you started the platform with `test/local/start-platform.sh`, not manually with `go run ./service start`.

### Audit log assertions failing

1. Check log level is `audit`:
   ```bash
   grep -i "level.*audit" ../../platform/opentdf.yaml
   ```

2. Verify log files are being written:
   ```bash
   ls -lh ../../platform/logs/
   ```

3. Check log format matches expectations (JSON recommended):
   ```bash
   head -1 ../../platform/logs/kas-main.log | jq .
   ```

### Tests running but no audit log collection

Check environment variables are set:
```bash
env | grep -E '(PLATFORM_DIR|LOG_FILE)'
```

## Differences from CI

| Aspect | CI | Local (run-local.sh) |
|--------|-----|----------------------|
| Platform startup | Automatic | Manual (test/local/start-platform.sh) |
| KAS startup | Automatic | Automatic by wrapper |
| Cleanup | Automatic | Automatic on script exit |
| Log paths | Relative | Absolute |
| Docker compose | Fresh containers | Persistent containers |

## Performance Tips

### Skip Unnecessary KAS Instances

If your test doesn't need all KAS instances:

```bash
START_KAS_INSTANCES="alpha beta" ./run-local.sh test_simple.py
```

Or skip entirely:
```bash
SKIP_KAS_START=true ./run-local.sh test_simple.py
```

### Use Persistent Platform

Instead of restarting platform for each test run:

```bash
# Start once
cd ../../platform
LOG_LEVEL=audit LOG_TYPE=json test/local/start-platform.sh

# Run tests multiple times
cd ../tests/xtest
./run-local.sh test_abac.py  # KAS instances started/stopped each run
./run-local.sh test_tdfs.py  # Platform stays running
```

### Reduce Log Verbosity

For faster tests without audit log assertions:

```bash
# Start platform with minimal logging
cd ../../platform
LOG_LEVEL=error LOG_TYPE=text test/local/start-platform.sh

# Disable audit log collection in tests
cd ../tests/xtest
pytest --no-audit-logs test_tdfs.py
```

## See Also

- [Platform local development scripts](../../platform/test/local/README.md)
- [Audit log fixtures](fixtures/audit.py)
- [Audit log implementation](audit_logs.py)
- [CI workflow](.github/workflows/xtest.yml)
