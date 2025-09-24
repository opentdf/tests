#!/bin/bash
# Generate unique KAS keys for each service in the multi-KAS profile

set -e

# Get the project root (tests directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
KEYS_DIR="${PROJECT_ROOT}/work/multi-kas-keys"

echo "Generating unique KAS keys for multi-KAS profile..."

# List of KAS services
KAS_SERVICES=("kas-default" "kas-value1" "kas-value2" "kas-attr" "kas-ns")

for kas in "${KAS_SERVICES[@]}"; do
    echo "Generating keys for ${kas}..."
    
    KAS_DIR="${KEYS_DIR}/${kas}"
    mkdir -p "${KAS_DIR}"
    
    # Generate RSA key pair if not exists
    if [ ! -f "${KAS_DIR}/kas-private.pem" ]; then
        echo "  Generating RSA 2048-bit key pair..."
        openssl genrsa -out "${KAS_DIR}/kas-private.pem" 2048
        openssl req -new -x509 -sha256 \
            -key "${KAS_DIR}/kas-private.pem" \
            -out "${KAS_DIR}/kas-cert.pem" \
            -days 365 \
            -subj "/C=US/ST=State/L=City/O=OpenTDF/OU=${kas}/CN=${kas}.opentdf.local"
    else
        echo "  RSA keys already exist, skipping..."
    fi
    
    # Generate EC key pair if not exists
    if [ ! -f "${KAS_DIR}/kas-ec-private.pem" ]; then
        echo "  Generating EC P-256 key pair..."
        openssl ecparam -genkey -name prime256v1 \
            -out "${KAS_DIR}/kas-ec-private.pem"
        openssl req -new -x509 -sha256 \
            -key "${KAS_DIR}/kas-ec-private.pem" \
            -out "${KAS_DIR}/kas-ec-cert.pem" \
            -days 365 \
            -subj "/C=US/ST=State/L=City/O=OpenTDF/OU=${kas}/CN=${kas}-ec.opentdf.local"
    else
        echo "  EC keys already exist, skipping..."
    fi
    
    # Set appropriate permissions
    chmod 600 "${KAS_DIR}"/*-private.pem
    chmod 644 "${KAS_DIR}"/*-cert.pem
    
    echo "  ✓ Keys generated for ${kas}"
done

echo ""
echo "All KAS keys generated successfully!"
echo ""
echo "Key locations:"
for kas in "${KAS_SERVICES[@]}"; do
    echo "  ${kas}:"
    echo "    RSA cert: ${KEYS_DIR}/${kas}/kas-cert.pem"
    echo "    RSA key:  ${KEYS_DIR}/${kas}/kas-private.pem"
    echo "    EC cert:  ${KEYS_DIR}/${kas}/kas-ec-cert.pem"
    echo "    EC key:   ${KEYS_DIR}/${kas}/kas-ec-private.pem"
done