#!/usr/bin/env bash
# Common shell wrapper used to interface to browser tests.
#
# Usage: ./browser-nanotdf.sh <owner> <tier> <decrypt> <src-file> <dst-file>
#
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
PROJECT_ROOT="$(cd "${APP_DIR}/../../../../" >/dev/null && pwd)"
export PATH="$PATH:$APP_DIR:$PROJECT_ROOT/scripts"
if ! cd "${PROJECT_ROOT}/xtest"; then
  monolog ERROR "Unable to find xtest folder within [${PROJECT_ROOT}]"
  exit 1
fi

monolog TRACE "node sdk/js/browser/nanotdf-helper.js -u $1 -s $2 $3 -i $4 -o $5 ${*:6}"
node sdk/js/browser/nanotdf-helper.js \
  -u $1 -s $2 $3 -i $4 -o $5 "${@:6}"
