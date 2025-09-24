#!/bin/bash

# Start the Java SDK test helper server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Build the server if needed
if [ ! -f "server/target/sdk-server-1.0.0.jar" ]; then
    echo "Building Java SDK server..."
    cd server
    mvn clean package -DskipTests
    cd ..
fi

# Parse arguments
DAEMONIZE=""
PORT="${JAVA_SDK_PORT:-8092}"

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

echo "Starting Java SDK test helper server on port $PORT"
export JAVA_SDK_PORT=$PORT

# Start the server
exec java -jar server/target/sdk-server-1.0.0.jar $DAEMONIZE