#!/usr/bin/env bash

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
TOOL_NAME="$(basename "$0")"
: "${PROJECT_DIR:="$(cd "${APP_DIR}" && git rev-parse --show-toplevel)"}"
export PATH="$PATH:$APP_DIR"

projects=(backend client-web frontend tdf3-js)
now=$(date +"%Y-%m-%dT%H:%M:%S%z")

if ! cd "$PROJECT_DIR"; then
  echo "[ERROR](${TOOL_NAME}) Unable to change to project dir [${PROJECT_DIR}] from [$(pwd)]"
  exit 1
fi

for project in "${projects[@]}"; do
  m="🔀 git subtree pull $project at $now"
  if ! git subtree pull -m "$m" -P "$project" "git@github.com:/opentdf/$project" main; then
    echo "[ERROR](${TOOL_NAME}) Unable to pull [$project]"
    exit 1
  fi
done

if ! git log -1 | grep "at $now"; then
  echo "[INFO](${TOOL_NAME}) No changes found during sync with (${projects[*]})"
fi
