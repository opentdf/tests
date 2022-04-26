#!/usr/bin/env bash

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
TOOL_NAME="$(basename "$0")"
: "${PROJECT_DIR:="$(cd "${APP_DIR}" && git rev-parse --show-toplevel)"}"
export PATH="$PATH:$APP_DIR"

projects=(backend client-web frontend tdf3-js)

if ! cd "$PROJECT_DIR"; then
  echo "[ERROR](${TOOL_NAME}) Unable to change to project dir [${PROJECT_DIR}] from [$(pwd)]"
  exit 1
fi

for project in "${projects[@]}"; do
  if ! git submodule add "git@github.com:/opentdf/$project" "projects/$project"; then
    echo "[ERROR](${TOOL_NAME}) Unable to pull [$project]"
    exit 1
  fi
done
