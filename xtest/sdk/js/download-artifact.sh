#!/bin/bash
set -e

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

VERSION="$1"
DIST_DIR="$2"

if [ -z "$VERSION" ] || [ -z "$DIST_DIR" ]; then
  echo "Usage: $0 <version> <dist-dir>"
  echo "Example: $0 0.4.0 /tmp/js-dist"
  echo "Example: $0 dev /tmp/js-dist  (downloads from dev release)"
  exit 1
fi

mkdir -p "$DIST_DIR"
cd "$DIST_DIR"

if [[ "$VERSION" == "dev" ]]; then
  echo "Downloading JS artifact from dev release..."
  gh release download dev --repo opentdf/web-sdk -p "opentdf-ctl-*.tgz" -D .
  npm init -y
  npm install ./opentdf-ctl-*.tgz
else
  npm init -y
  npm install "@opentdf/ctl@${VERSION}"
fi

cp "$SCRIPT_DIR/cli.sh" .

echo "JS artifact ${VERSION} downloaded to ${DIST_DIR}"
