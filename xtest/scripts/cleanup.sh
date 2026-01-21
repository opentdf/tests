#!/usr/bin/env bash
# Full teardown of xtest local environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/tmux-helpers.sh"

KEEP_LOGS="${1:-}"

cleanup() {
    log_info "Cleaning up xtest environment..."

    # Kill tmux session (stops all platform/KAS processes)
    if session_exists; then
        log_info "Stopping tmux session..."
        kill_session
    fi

    # Stop docker containers
    log_info "Stopping docker containers..."
    "$SCRIPT_DIR/services/docker-up.sh" stop 2>/dev/null || true

    # Clean up generated configs
    if [ "$KEEP_LOGS" != "--keep-logs" ]; then
        log_info "Cleaning up logs and configs..."
        rm -rf "$LOGS_DIR"
    else
        log_info "Keeping logs in $LOGS_DIR"
    fi

    log_success "Cleanup complete"
}

cleanup
