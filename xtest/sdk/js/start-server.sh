#!/bin/bash

# Start the JavaScript SDK test helper server
# This server provides HTTP endpoints for test operations using the JS SDK directly

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "Installing server dependencies..."
    npm install --no-save express body-parser morgan node-fetch
fi

# Check if @opentdf/sdk is available
if [ ! -d "src/main/cli/node_modules/@opentdf/sdk" ]; then
    echo "Error: @opentdf/sdk not found. Please build the JS SDK first."
    echo "Run: make build"
    exit 1
fi

# Export SDK location
export NODE_PATH="$SCRIPT_DIR/src/main/cli/node_modules:$NODE_PATH"

# Parse arguments
DAEMONIZE=""
PORT="${TESTHELPER_PORT:-8090}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--daemonize)
            DAEMONIZE="--daemonize"
            shift
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

echo "Starting JavaScript SDK test helper server on port $PORT"
export TESTHELPER_PORT=$PORT

# Start the server
exec node server.js $DAEMONIZE