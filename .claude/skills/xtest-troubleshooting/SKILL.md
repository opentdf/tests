---
name: xtest-troubleshooting
description: Known xtest failure recipes — "EC wrapping not supported", ABAC decrypt errors from unregistered KAS instances, golden/legacy TDF "message authentication failed", missing OT_ROOT_KEY/SCHEMA_FILE. Use when an xtest run fails during setup, encrypt, or decrypt.
---

# Common Test Failures and Debugging

### EC Wrapping Test Failures: "EC wrapping not supported"

**Fix**:
```bash
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf.yaml
yq e -i '.services.kas.preview.ec_tdf_enabled = true' platform/opentdf-dev.yaml
# Restart the platform service
```

### ABAC Test Failures: Decrypt Errors

**Symptom**: ABAC autoconfigure tests fail during decrypt

**Root Cause**: KAS instances (alpha, beta, etc.) not registered in platform's KAS registry

**Debug**:
```bash
curl http://localhost:8080/api/kas/v2/kas/key-access-servers | jq '.key_access_servers[].uri'
# Expected: alpha=8181, beta=8282, gamma=8383, delta=8484
```

**Fix**: Ensure all KAS instances are properly registered during startup.

### Legacy/Golden TDF Test Failures

**Symptom**: "cipher: message authentication failed"

**Root Cause**: Golden TDFs require specific keys loaded by the platform. Ensure the platform is configured with the correct golden keys.

```bash
cd xtest
uv run pytest test_legacy.py --sdks go -v --no-audit-logs
```

### Missing Environment Variables

**Symptom**: "OT_ROOT_KEY environment variable is not set"

**Fix**:
```bash
export OT_ROOT_KEY=$(yq e '.services.kas.root_key' platform/opentdf-dev.yaml)
export SCHEMA_FILE=manifest.schema.json
```
