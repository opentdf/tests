#!/usr/bin/env bash
# macOS certificate trust management for xtest
#
# Usage:
#   ./trust-cert.sh add      # Add localhost cert to system keychain
#   ./trust-cert.sh remove   # Remove localhost cert from system keychain
#   ./trust-cert.sh status   # Check if cert is trusted

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

ACTION="${1:-status}"

# Certificate path
CERT_PATH="$PLATFORM_DIR/keys/localhost.crt"
CERT_NAME="localhost"

# Check if we're on macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        log_warn "Certificate trust management is only implemented for macOS"
        log_info "On other systems, you may need to manually trust the certificate"
        return 1
    fi
    return 0
}

# Check if certificate is already trusted
is_trusted() {
    security find-certificate -c "$CERT_NAME" /Library/Keychains/System.keychain >/dev/null 2>&1
}

add_trust() {
    if ! check_macos; then
        return 0
    fi

    if [ ! -f "$CERT_PATH" ]; then
        log_error "Certificate not found: $CERT_PATH"
        log_info "Run init-keys.sh first to generate certificates"
        return 1
    fi

    if is_trusted; then
        log_info "Certificate '$CERT_NAME' is already trusted"
        return 0
    fi

    log_info "Adding certificate to system keychain (requires sudo)..."
    sudo security add-trusted-cert -d -r trustRoot \
        -k /Library/Keychains/System.keychain \
        "$CERT_PATH"

    log_success "Certificate added to system keychain"
}

remove_trust() {
    if ! check_macos; then
        return 0
    fi

    if ! is_trusted; then
        log_info "Certificate '$CERT_NAME' is not in system keychain"
        return 0
    fi

    log_info "Removing certificate from system keychain (requires sudo)..."
    sudo security delete-certificate -c "$CERT_NAME" /Library/Keychains/System.keychain

    log_success "Certificate removed from system keychain"
}

show_status() {
    if ! check_macos; then
        return 0
    fi

    if is_trusted; then
        log_success "Certificate '$CERT_NAME' is trusted"
    else
        log_warn "Certificate '$CERT_NAME' is NOT trusted"
        log_info "Run '$0 add' to trust the certificate"
    fi
}

case "$ACTION" in
    add)
        add_trust
        ;;
    remove)
        remove_trust
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {add|remove|status}"
        exit 1
        ;;
esac
