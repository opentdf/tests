#!/usr/bin/env bash
# Provision Keycloak and fixtures for xtest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

ACTION="${1:-all}"

provision_keycloak() {
    log_info "Provisioning Keycloak..."

    cd "$PLATFORM_DIR"
    go run ./service provision keycloak

    log_success "Keycloak provisioned"
}

provision_fixtures() {
    log_info "Provisioning fixtures..."

    cd "$PLATFORM_DIR"
    go run ./service provision fixtures

    log_success "Fixtures provisioned"
}

provision_all() {
    provision_keycloak
    provision_fixtures
}

case "$ACTION" in
    keycloak)
        provision_keycloak
        ;;
    fixtures)
        provision_fixtures
        ;;
    all)
        provision_all
        ;;
    *)
        echo "Usage: $0 {keycloak|fixtures|all}"
        exit 1
        ;;
esac
