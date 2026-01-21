#!/usr/bin/env bash
# Initialize cryptographic keys for xtest
# Wraps platform's init-temp-keys.sh script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

FORCE="${1:-}"

# Check if keys already exist
keys_exist() {
    [ -f "$PLATFORM_DIR/kas-cert.pem" ] && \
    [ -f "$PLATFORM_DIR/kas-private.pem" ] && \
    [ -f "$PLATFORM_DIR/kas-ec-cert.pem" ] && \
    [ -f "$PLATFORM_DIR/kas-ec-private.pem" ]
}

init_keys() {
    log_info "Initializing cryptographic keys..."

    INIT_SCRIPT="$PLATFORM_DIR/.github/scripts/init-temp-keys.sh"

    if [ ! -x "$INIT_SCRIPT" ]; then
        log_error "Key initialization script not found: $INIT_SCRIPT"
        exit 1
    fi

    cd "$PLATFORM_DIR"
    "$INIT_SCRIPT"

    log_success "Keys initialized"
}

if [ "$FORCE" = "--force" ] || [ "$FORCE" = "-f" ]; then
    log_info "Force regenerating keys"
    init_keys
elif keys_exist; then
    log_info "Keys already exist, skipping initialization"
    log_info "Use --force to regenerate keys"
else
    init_keys
fi
