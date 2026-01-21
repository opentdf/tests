#!/usr/bin/env bash
# Start keycloak and postgres containers for xtest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

ACTION="${1:-start}"

start_containers() {
    log_info "Starting docker containers (keycloak, postgres)..."

    cd "$PLATFORM_DIR"

    # Check if containers are already running
    if docker compose ps --services --filter "status=running" | grep -q keycloak; then
        log_warn "Containers appear to be already running"
    fi

    # Start containers
    docker compose up -d keycloak

    log_success "Docker containers started"
}

stop_containers() {
    log_info "Stopping docker containers..."

    cd "$PLATFORM_DIR"
    docker compose down

    log_success "Docker containers stopped"
}

wait_for_containers() {
    log_info "Waiting for containers to be healthy..."

    # Wait for Keycloak
    wait_for_health "$KEYCLOAK_HEALTH" "Keycloak" 90

    # Wait for Postgres via pg_isready (service is named opentdfdb)
    local max_attempts=30
    local attempt=1
    log_info "Waiting for Postgres..."
    while [ "$attempt" -le "$max_attempts" ]; do
        if docker compose -f "$PLATFORM_DIR/docker-compose.yaml" exec -T opentdfdb pg_isready -U postgres >/dev/null 2>&1; then
            log_success "Postgres is ready"
            return 0
        fi
        sleep 1
        ((attempt++))
    done
    log_error "Postgres failed to become ready"
    return 1
}

show_logs() {
    cd "$PLATFORM_DIR"
    docker compose logs -f
}

status() {
    cd "$PLATFORM_DIR"
    docker compose ps
}

case "$ACTION" in
    start)
        start_containers
        wait_for_containers
        ;;
    stop)
        stop_containers
        ;;
    logs)
        show_logs
        ;;
    status)
        status
        ;;
    wait)
        wait_for_containers
        ;;
    *)
        echo "Usage: $0 {start|stop|logs|status|wait}"
        exit 1
        ;;
esac
