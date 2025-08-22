# Multi-KAS Testing Profile

This profile runs 5 independent Key Access Servers (KAS) for testing split-key functionality and multi-domain security scenarios.

## Overview

The multi-KAS profile enables comprehensive testing of:
- Split-key encryption/decryption across multiple KAS servers
- Different grant types (value, attribute, namespace)
- Complex policy enforcement across security domains
- Cross-KAS attribute management

## Architecture

### KAS Servers

| Service | Port | gRPC Port | Purpose | Realm |
|---------|------|-----------|---------|-------|
| kas-default | 8080 | 8084 | Default KAS | opentdf_default |
| kas-value1 | 8181 | 8185 | Value-level grants | opentdf_value1 |
| kas-value2 | 8282 | 8286 | Value-level grants | opentdf_value2 |
| kas-attr | 8383 | 8387 | Attribute-level grants | opentdf_attr |
| kas-ns | 8484 | 8488 | Namespace-level grants | opentdf_ns |

### Unique Keys

Each KAS server has its own cryptographic keys:
- RSA 2048-bit key pair (kid: "r1")
- EC P-256 key pair (kid: "e1")

Keys are stored in `work/multi-kas-keys/{service-name}/`

## Usage

### Starting Services

```bash
./run.py start --profile multi-kas
```

### Stopping Services

```bash
./run.py stop
```

### Running Tests

Run tests that require multiple KAS servers:
```bash
pytest xtest/test_abac.py -v
```

## Configuration

### Environment Variables

The tests use these environment variables to locate KAS servers:
- `KASURL` - Default KAS (http://localhost:8080/kas)
- `KASURL1` - Value1 KAS (http://localhost:8181/kas)
- `KASURL2` - Value2 KAS (http://localhost:8282/kas)
- `KASURL3` - Attribute KAS (http://localhost:8383/kas)
- `KASURL4` - Namespace KAS (http://localhost:8484/kas)

### Files

- `config.yaml` - Service configuration
- `capabilities.yaml` - Supported features
- `opentdf.yaml` - OpenTDF platform configuration template
- `generate-keys.sh` - Script to generate unique KAS keys (called automatically)

## Troubleshooting

### Check Service Status
```bash
# Check if services are running
curl http://localhost:8080/healthz  # Default KAS
curl http://localhost:8181/healthz  # Value1 KAS
curl http://localhost:8282/healthz  # Value2 KAS
curl http://localhost:8383/healthz  # Attribute KAS
curl http://localhost:8484/healthz  # Namespace KAS
```

### View Logs
```bash
tail -f work/kas-default.log
tail -f work/kas-value1.log
tail -f work/kas-value2.log
tail -f work/kas-attr.log
tail -f work/kas-ns.log
```

### Check PIDs
```bash
cat work/multi_kas_pids.txt
```

### Reset Profile

To completely reset the multi-KAS profile:
```bash
# Stop all services
./run.py stop

# Remove provisioning markers
rm -f work/.provisioned_opentdf_*

# Remove keys (optional - will be regenerated)
rm -rf work/multi-kas-keys/

# Remove databases (requires PostgreSQL access)
PGPASSWORD=changeme psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS opentdf_default;"
PGPASSWORD=changeme psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS opentdf_value1;"
PGPASSWORD=changeme psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS opentdf_value2;"
PGPASSWORD=changeme psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS opentdf_attr;"
PGPASSWORD=changeme psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS opentdf_ns;"
```

## Test Examples

### Split-Key Test
The `test_key_mapping_multiple_mechanisms` test in `test_abac.py` validates split-key functionality by:
1. Encrypting with attributes that require keys from multiple KAS
2. Verifying the manifest contains multiple keyAccess objects
3. Confirming successful decryption using keys from all involved KAS

### Multi-KAS Policy Test
The `test_autoconfigure_two_kas_*` tests validate policies that span multiple KAS servers with different grant types.