#!/bin/bash
set -e

# Build cmdline.jar from source, using the released SDK from Maven Central.
# This is faster than building the full SDK since we only compile cmdline.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.12.0 /tmp/java-dist"
  exit 1
fi

mkdir -p "$DIST_DIR"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

echo "Cloning java-sdk v${VERSION}..."
git clone --depth 1 --branch "v${VERSION}" \
  https://github.com/opentdf/java-sdk.git "$WORK_DIR/java-sdk"

echo "Building cmdline module only (using released SDK from Maven Central)..."
cd "$WORK_DIR/java-sdk"
# No -am flag: fetch sdk dependency from Maven Central instead of building from source
# Skip enforcer plugin since parent modules aren't in the reactor
mvn --batch-mode -pl cmdline package -DskipTests -Dmaven.javadoc.skip=true -Denforcer.skip=true

cp cmdline/target/cmdline.jar "$DIST_DIR/"
cp "$SCRIPT_DIR/cli.sh" "$DIST_DIR/"

echo "Java cmdline.jar v${VERSION} built and copied to ${DIST_DIR}"
