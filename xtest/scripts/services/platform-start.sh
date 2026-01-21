#!/usr/bin/env bash
# Start the main platform service for xtest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

ensure_logs_dir

CONFIG_FILE="${1:-opentdf.yaml}"
LOG_FILE="$LOGS_DIR/platform.log"

# Ensure config file exists
if [ ! -f "$PLATFORM_DIR/$CONFIG_FILE" ]; then
    log_info "Creating platform config from opentdf-dev.yaml"
    if [ -f "$PLATFORM_DIR/opentdf-dev.yaml" ]; then
        cp "$PLATFORM_DIR/opentdf-dev.yaml" "$PLATFORM_DIR/$CONFIG_FILE"
    else
        log_error "No config template found at $PLATFORM_DIR/opentdf-dev.yaml"
        exit 1
    fi
fi

log_info "Starting main platform on port $PLATFORM_PORT"
log_info "Config: $PLATFORM_DIR/$CONFIG_FILE"
log_info "Logs: $LOG_FILE"

cd "$PLATFORM_DIR"

# Use watch.sh if available for hot-reload capability
WATCH_SCRIPT="$PLATFORM_DIR/.github/scripts/watch.sh"

if [ -x "$WATCH_SCRIPT" ]; then
    log_info "Using watch.sh for hot-reload support"
    exec "$WATCH_SCRIPT" \
        --tee-out-to "$LOG_FILE" \
        --tee-err-to "$LOG_FILE" \
        "$CONFIG_FILE" \
        go run ./service start
else
    log_info "Running platform directly (no hot-reload)"
    exec go run ./service start 2>&1 | tee "$LOG_FILE"
fi
