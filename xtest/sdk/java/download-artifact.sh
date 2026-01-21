#!/bin/bash
set -e

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.9.0 /tmp/java-dist"
  exit 1
fi

mkdir -p "$DIST_DIR"

curl -fsSL -o "$DIST_DIR/cmdline.jar" \
  "https://repo1.maven.org/maven2/io/opentdf/platform/cmdline/${VERSION}/cmdline-${VERSION}.jar"

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cp "$SCRIPT_DIR/cli.sh" "$DIST_DIR/"

echo "Java artifact v${VERSION} downloaded to ${DIST_DIR}"
