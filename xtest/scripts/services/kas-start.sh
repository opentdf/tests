#!/usr/bin/env bash
# Start an individual KAS instance for xtest
#
# Usage: ./kas-start.sh <name> <port> [--key-management]
#
# Creates config from opentdf-kas-mode.yaml template with:
# - server.port = specified port
# - services.kas.registered_kas_uri = http://localhost:<port>
# - services.kas.preview.ec_tdf_enabled = true
# - services.kas.preview.key_management = true (for km instances)
# - sdk_config.core.endpoint = http://localhost:8080

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

NAME="${1:-}"
PORT="${2:-}"
KEY_MANAGEMENT=false

# Parse optional flags
shift 2 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case "$1" in
        --key-management)
            KEY_MANAGEMENT=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$NAME" ] || [ -z "$PORT" ]; then
    echo "Usage: $0 <name> <port> [--key-management]"
    echo ""
    echo "Examples:"
    echo "  $0 alpha 8181"
    echo "  $0 km1 8585 --key-management"
    exit 1
fi

ensure_logs_dir

TEMPLATE_FILE="$PLATFORM_DIR/opentdf-kas-mode.yaml"
CONFIG_FILE="$LOGS_DIR/kas-${NAME}.yaml"
LOG_FILE="$LOGS_DIR/kas-${NAME}.log"

# Check template exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    log_error "KAS template not found: $TEMPLATE_FILE"
    exit 1
fi

# Generate config from template
log_info "Generating KAS config for $NAME on port $PORT"

cp "$TEMPLATE_FILE" "$CONFIG_FILE"

# Update port
yq e -i ".server.port = $PORT" "$CONFIG_FILE"

# Update registered KAS URI (without /kas suffix for km instances)
if [ "$KEY_MANAGEMENT" = true ]; then
    yq e -i ".services.kas.registered_kas_uri = \"http://localhost:$PORT\"" "$CONFIG_FILE"
else
    yq e -i ".services.kas.registered_kas_uri = \"http://localhost:$PORT/kas\"" "$CONFIG_FILE"
fi

# Enable EC TDF
yq e -i ".services.kas.preview.ec_tdf_enabled = true" "$CONFIG_FILE"

# Configure key management
if [ "$KEY_MANAGEMENT" = true ]; then
    yq e -i ".services.kas.preview.key_management = true" "$CONFIG_FILE"

    # Generate and set root key for key management instances
    ROOT_KEY_FILE="$LOGS_DIR/root_key.txt"
    if [ ! -f "$ROOT_KEY_FILE" ]; then
        log_info "Generating shared root key for key management KAS instances"
        generate_root_key > "$ROOT_KEY_FILE"
    fi
    ROOT_KEY=$(cat "$ROOT_KEY_FILE")
    yq e -i ".services.kas.root_key = \"$ROOT_KEY\"" "$CONFIG_FILE"

    log_info "Key management enabled for $NAME"
else
    yq e -i ".services.kas.preview.key_management = false" "$CONFIG_FILE"
fi

# Ensure SDK config points to main platform
yq e -i ".sdk_config.core.endpoint = \"http://localhost:$PLATFORM_PORT\"" "$CONFIG_FILE"

log_info "Starting KAS '$NAME' on port $PORT"
log_info "Config: $CONFIG_FILE"
log_info "Logs: $LOG_FILE"

cd "$PLATFORM_DIR"

# Use watch.sh if available for hot-reload capability
WATCH_SCRIPT="$PLATFORM_DIR/.github/scripts/watch.sh"

if [ -x "$WATCH_SCRIPT" ]; then
    exec "$WATCH_SCRIPT" \
        --tee-out-to "$LOG_FILE" \
        --tee-err-to "$LOG_FILE" \
        "$CONFIG_FILE" \
        go run ./service start --config-file "$CONFIG_FILE"
else
    exec go run ./service start --config-file "$CONFIG_FILE" 2>&1 | tee "$LOG_FILE"
fi
