#!/bin/bash
set -e

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.24.0 /tmp/go-dist"
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

mkdir -p "$DIST_DIR"
# Convert to absolute path
DIST_DIR=$(cd "$DIST_DIR" && pwd)

GOBIN="$DIST_DIR" go install "github.com/opentdf/otdfctl@v${VERSION}"
cp "$SCRIPT_DIR/cli.sh" "$DIST_DIR/"
cp "$SCRIPT_DIR/otdfctl.sh" "$DIST_DIR/"
cp "$SCRIPT_DIR/opentdfctl.yaml" "$DIST_DIR/"

echo "Go artifact v${VERSION} downloaded to ${DIST_DIR}"
