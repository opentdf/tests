#!/bin/bash
set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.4.0 /tmp/js-dist"
  exit 1
fi

mkdir -p "$DIST_DIR"
cd "$DIST_DIR"

npm init -y
npm install "@opentdf/ctl@${VERSION}"

cp "$SCRIPT_DIR/cli.sh" .

echo "JS artifact v${VERSION} downloaded to ${DIST_DIR}"
