#!/usr/bin/env bash
# Automate pushing a PR for updating submodules.
#
# Recommended use:
# 1. Checkout a clean repo in a safe place, separate from your current repo.
# 2. Run this script in a cron job with the form PROJECT_DIR=/your/clean/repo /path/to/this/script.sh

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"
TOOL_NAME="$(basename "$0")"
: "${PROJECT_DIR:="$(cd "${APP_DIR}" && git rev-parse --show-toplevel)"}"
export PATH="$PATH:$APP_DIR"
export PROJECT_DIR

if ! cd "$PROJECT_DIR"; then
  echo "[ERROR](${TOOL_NAME}) Unable to change to project dir [${PROJECT_DIR}] from [$(pwd)]"
  exit 1
fi

current_branch="$(git branch --show-current)"

list-prs-state() {
  # Let shellcheck ignore this go template
  # shellcheck disable=SC2016
  local template='{{range $a, $b := .}}{{.state}}{{end}}'
  gh pr list \
    --head "$1" \
    --state all \
    --json state \
    --template "${template}"
}

if [[ "$(git status -s)" ]]; then
  echo "[ERROR](${TOOL_NAME}) Not on a clean working tree"
  exit 1
fi

if [[ $current_branch != "main" ]]; then
  pr_state_now="$(list-prs-state "$current_branch")"
  if [[ $pr_state_now = *OPEN ]]; then
    echo "[INFO](${TOOL_NAME}) Existing PR found. Working with ${pr_state_now}."
    if ! git submodule update --remote; then
      echo "[ERROR](${TOOL_NAME}) Unable update submodules"
      exit 1
    fi
    if [[ ! "$(git status -s)" ]]; then
      echo "[INFO](${TOOL_NAME}) No new updates detected"
      exit 0
    fi
    if ! git push; then
      echo "[ERROR](${TOOL_NAME}) Unable push changes"
      exit 1
    fi
    echo "[INFO](${TOOL_NAME}) Pushed latest changes to existing PR"
    exit 0
  else
    echo "[INFO](${TOOL_NAME}) PR merged already. Starting afresh"
    if ! git checkout main; then
      echo "[ERROR](${TOOL_NAME}) Unable to checkout main"
      exit 1
    fi
  fi
fi

if ! git pull; then
  echo "[ERROR](${TOOL_NAME}) Failed to git pull from main repo"
  exit 1
fi

now=$(date +"%Y-%m-%dT%H%M%S%z")

new_branch="feature/autosync-starting-at-${now}"
if ! git checkout -b "${new_branch}"; then
  echo "[ERROR](${TOOL_NAME}) Failed to git checkout a new sync branch"
  exit 1
fi

if ! git submodule update --remote; then
  echo "[ERROR](${TOOL_NAME}) Unable update submodules"
  exit 1
fi
if [[ ! "$(git status -s)" ]]; then
  echo "[INFO](${TOOL_NAME}) No updates detected"
  git checkout main && git branch -D "${new_branch}"
  exit 0
fi

if ! git push --set-upstream origin "${new_branch}"; then
  echo "[ERROR](${TOOL_NAME}) Unable push changes"
  exit 1
fi

if ! gh pr create --title "🔀 submodule update $now" --body "Your irregularly scheduled submodule update"; then
  echo "[ERROR](${TOOL_NAME}) Unable create PR"
fi
