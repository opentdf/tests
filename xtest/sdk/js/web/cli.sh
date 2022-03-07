#!/usr/bin/env bash
# Common shell wrapper used to interface to browser tests.
#
# Usage: ./browser-oss.sh <tier> <encrypt | decrypt> <src-file> <dst-file>
#

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
PROJECT_ROOT="$(cd "${APP_DIR}/../../../../" >/dev/null && pwd)"

export PATH="$PATH:$APP_DIR:$PROJECT_ROOT/tools"

if ! cd "${PROJECT_ROOT}/xtest"; then
  monolog ERROR "Unable to find xtest folder within [${PROJECT_ROOT}]"
  exit 1
fi

node sdk/js/web/browser.js $1 -i $2 -o $3 "${@:4}"