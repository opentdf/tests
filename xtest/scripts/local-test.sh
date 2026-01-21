#!/usr/bin/env bash
# Main entry point for local xtest execution
#
# Usage:
#   ./local-test.sh start     # Start all services
#   ./local-test.sh stop      # Stop everything
#   ./local-test.sh status    # Show service health
#   ./local-test.sh attach    # Attach to tmux session
#   ./local-test.sh logs      # View combined logs
#   ./local-test.sh help      # Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/tmux-helpers.sh"

ACTION="${1:-help}"

show_help() {
    cat <<EOF
xtest Local Test Runner

Usage: $0 <command>

Commands:
  start     Start all services (docker, platform, KAS instances)
  stop      Stop everything and clean up
  status    Show service health status
  attach    Attach to tmux session
  logs      View combined logs
  help      Show this help

Startup sequence:
  1. Check prerequisites (go, docker, tmux, yq)
  2. Generate keys if missing
  3. Add cert to macOS keychain (optional)
  4. Create tmux session
  5. Start docker services (keycloak:8888, postgres:5432)
  6. Wait for containers healthy
  7. Start main platform on port 8080
  8. Provision keycloak and fixtures
  9. Start 6 additional KAS instances (8181-8686)
  10. Report ready status

tmux Navigation:
  tmux attach -t xtest    # Attach to session
  Ctrl-b <number>          # Switch to window
  Ctrl-b d                 # Detach from session

Environment Variables:
  PLATFORM_DIR    Path to platform directory (default: ../../platform)

EOF
    show_layout_help
}

do_start() {
    log_info "Starting xtest local environment..."

    # Step 1: Check prerequisites
    log_info "Checking prerequisites..."
    if ! check_prerequisites; then
        log_error "Missing prerequisites. Please install missing tools."
        exit 1
    fi
    log_success "All prerequisites found"

    # Step 2: Generate keys if missing
    log_info "Checking cryptographic keys..."
    "$SCRIPT_DIR/setup/init-keys.sh"

    # Step 3: Trust certificate on macOS (optional, don't fail if skipped)
    if [[ "$(uname)" == "Darwin" ]]; then
        log_info "Checking certificate trust..."
        "$SCRIPT_DIR/setup/trust-cert.sh" add || true
    fi

    # Step 4: Create tmux session
    create_session
    create_all_windows

    # Step 5: Start docker services
    log_info "Starting docker services..."
    run_in_window "docker" "cd '$PLATFORM_DIR' && docker compose up"

    # Step 6: Wait for containers
    "$SCRIPT_DIR/services/docker-up.sh" wait

    # Step 7: Start main platform
    log_info "Starting main platform..."
    run_in_window "platform" "'$SCRIPT_DIR/services/platform-start.sh'"

    # Wait for platform to be healthy
    wait_for_health "$PLATFORM_HEALTH" "Platform" 120

    # Step 8: Provision keycloak and fixtures
    log_info "Provisioning keycloak and fixtures..."
    "$SCRIPT_DIR/services/provision.sh"

    # Step 9: Start KAS instances
    log_info "Starting KAS instances..."

    # Start non-key-management KAS instances
    for name in alpha beta gamma delta; do
        port="${KAS_CONFIG[$name]}"
        run_in_window "kas-$name" "'$SCRIPT_DIR/services/kas-start.sh' '$name' '$port'"
    done

    # Start key management KAS instances
    for name in km1 km2; do
        port="${KAS_CONFIG[$name]}"
        run_in_window "kas-$name" "'$SCRIPT_DIR/services/kas-start.sh' '$name' '$port' --key-management"
    done

    # Wait for all KAS instances
    for name in "${!KAS_CONFIG[@]}"; do
        port="${KAS_CONFIG[$name]}"
        wait_for_health "http://localhost:$port/healthz" "KAS-$name" 60 || true
    done

    # Step 10: Report ready status
    log_success "xtest environment is ready!"
    echo ""
    show_layout_help
    echo ""
    log_info "To run tests:"
    log_info "  cd $XTEST_DIR"
    log_info "  uv run pytest test_self.py -v"
    log_info "  uv run pytest test_tdfs.py --sdks go -v"
    log_info "  uv run pytest test_abac.py --sdks go -v"
}

do_stop() {
    "$SCRIPT_DIR/cleanup.sh"
}

do_status() {
    echo "=== Service Status ==="
    echo ""

    # Check tmux session
    if session_exists; then
        log_success "tmux session '$TMUX_SESSION' is running"
        list_windows
    else
        log_warn "tmux session '$TMUX_SESSION' is not running"
    fi
    echo ""

    # Check docker containers
    echo "=== Docker Containers ==="
    if command -v docker &>/dev/null; then
        if ! (cd "$PLATFORM_DIR" && docker compose ps 2>/dev/null); then
            log_warn "Docker containers not running"
        fi
    fi
    echo ""

    # Check health endpoints
    echo "=== Health Checks ==="

    # Keycloak
    if curl -sf "$KEYCLOAK_HEALTH" >/dev/null 2>&1; then
        log_success "Keycloak (port $KEYCLOAK_PORT): healthy"
    else
        log_warn "Keycloak (port $KEYCLOAK_PORT): not responding"
    fi

    # Platform
    if curl -sf "$PLATFORM_HEALTH" >/dev/null 2>&1; then
        log_success "Platform (port $PLATFORM_PORT): healthy"
    else
        log_warn "Platform (port $PLATFORM_PORT): not responding"
    fi

    # KAS instances
    for name in "${!KAS_CONFIG[@]}"; do
        port="${KAS_CONFIG[$name]}"
        if curl -sf "http://localhost:$port/healthz" >/dev/null 2>&1; then
            log_success "KAS-$name (port $port): healthy"
        else
            log_warn "KAS-$name (port $port): not responding"
        fi
    done
}

do_attach() {
    if ! session_exists; then
        log_error "Session '$TMUX_SESSION' does not exist. Run 'start' first."
        exit 1
    fi
    attach_session
}

do_logs() {
    if [ ! -d "$LOGS_DIR" ]; then
        log_error "Logs directory does not exist: $LOGS_DIR"
        exit 1
    fi

    log_info "Tailing all logs (Ctrl-C to stop)..."
    tail -f "$LOGS_DIR"/*.log
}

case "$ACTION" in
    start)
        do_start
        ;;
    stop)
        do_stop
        ;;
    status)
        do_status
        ;;
    attach)
        do_attach
        ;;
    logs)
        do_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $ACTION"
        show_help
        exit 1
        ;;
esac
