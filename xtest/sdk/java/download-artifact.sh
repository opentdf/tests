#!/bin/bash
set -e

# NOTE: The Java cmdline.jar is not currently published to Maven Central.
# This script is provided for future use when/if the artifact is published.
# For now, the Java SDK must be built from source using the Makefile.

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.9.0 /tmp/java-dist"
  exit 1
fi

mkdir -p "$DIST_DIR"

echo "Attempting to download cmdline.jar v${VERSION} from Maven Central..."
if ! curl -fsSL -o "$DIST_DIR/cmdline.jar" \
  "https://repo1.maven.org/maven2/io/opentdf/platform/cmdline/${VERSION}/cmdline-${VERSION}.jar"; then
  echo "ERROR: cmdline.jar is not published to Maven Central."
  echo "The Java SDK must be built from source. See xtest/sdk/java/Makefile."
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cp "$SCRIPT_DIR/cli.sh" "$DIST_DIR/"

echo "Java artifact v${VERSION} downloaded to ${DIST_DIR}"
