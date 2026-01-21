#!/bin/bash
set -e

# Download cmdline.jar from dev release or build from source for released versions.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.12.0 /tmp/java-dist"
  echo "Example: $0 dev /tmp/java-dist  (downloads from dev release)"
  exit 1
fi

mkdir -p "$DIST_DIR"
# Convert to absolute path before changing directories
DIST_DIR=$(cd "$DIST_DIR" && pwd)

if [[ "$VERSION" == "dev" ]]; then
  echo "Downloading cmdline.jar from dev release..."
  gh release download dev --repo opentdf/java-sdk -p "cmdline.jar" -D "$DIST_DIR"
else
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
fi

cp "$SCRIPT_DIR/cli.sh" "$DIST_DIR/"

echo "Java cmdline.jar ${VERSION} downloaded/built to ${DIST_DIR}"
