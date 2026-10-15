#!/usr/bin/env bash
#
# Stage one `web` SDK dist directory.
#
# Usage: ./stage.sh <dist-dir> <sdk-package>
#
#   <dist-dir>     e.g. xtest/sdk/web/dist/v0.22.0
#   <sdk-package>  anything `npm install` accepts for @opentdf/sdk: a registry
#                  spec (@opentdf/sdk@0.22.0) or a packed tarball from a source
#                  build (/path/to/web-sdk/lib/opentdf-sdk-0.22.0.tgz)
#
# Copies cli.sh and the Playwright driver in, installs the driver's
# dependencies plus the requested @opentdf/sdk, bundles the page against it
# (build.mjs), and makes sure Playwright's browser is downloaded.
#
# The work happens in a sibling scratch directory that is renamed into place
# only once every step has succeeded, so an interrupted install never leaves a
# dist directory that looks complete to `otdf-sdk-mgr` or to xtest.
#
# Environment:
#   XT_WEB_BROWSER  browser to install (default chromium; firefox and webkit
#                   work with the driver but are not exercised in CI yet)
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <dist-dir> <sdk-package>" >&2
  exit 1
fi
dist_dir=$1
sdk_package=$2
if [[ -f "$sdk_package" ]]; then
  sdk_package=$(realpath "$sdk_package")
fi

mkdir -p "$(dirname "$dist_dir")"
dist_dir=$(realpath "$(dirname "$dist_dir")")/$(basename "$dist_dir")
staging="$dist_dir.staging.$$"
rm -rf "$staging"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging"

cp "$SCRIPT_DIR/cli.sh" "$staging/"
cp "$SCRIPT_DIR"/driver/{driver.mjs,page.js,build.mjs,index.html,package.json,package-lock.json} "$staging/"

cd "$staging"
echo "Installing driver dependencies and $sdk_package into $dist_dir"
npm install --no-audit --no-fund "$sdk_package"
node build.mjs

browser=${XT_WEB_BROWSER:-chromium}
install_args=("$browser")
if [[ -n "${CI:-}" && "$(uname -s)" == "Linux" ]]; then
  install_args+=(--with-deps)
fi
echo "Ensuring Playwright $browser is installed"
npx playwright install "${install_args[@]}"

cd "$SCRIPT_DIR"
rm -rf "$dist_dir"
mv "$staging" "$dist_dir"
trap - EXIT
echo "web SDK staged at $dist_dir ($(jq -r .version "$dist_dir/features.json"))"
