#!/bin/bash
# Refreshes to the latest sdk at branch in the appropriate folder.
#
# Usage: ./refresh-sdk-branch.sh [sdk language] [branch]
# Example: ./refresh-sdk-branch.sh js main

# Resolve script directory
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
XTEST_DIR=$(cd -- "$SCRIPT_DIR/../../" &>/dev/null && pwd)

# Parse arguments
LANGUAGE=${1:-js}
BRANCH=${2:-main}

case "$LANGUAGE" in
  js)
    BARE_REPO_PATH="$XTEST_DIR/sdk/js/src/web-sdk.git"
    WORKTREE_PATH="$XTEST_DIR/sdk/js/src/$BRANCH"
    REPO_URL="https://github.com/opentdf/web-sdk"
    ;;
  java)
    BARE_REPO_PATH="$XTEST_DIR/sdk/java/src/web-sdk.git"
    WORKTREE_PATH="$XTEST_DIR/sdk/java/src/$BRANCH"
    REPO_URL="https://github.com/opentdf/java-sdk"
    ;;
  go)
    BARE_REPO_PATH="$XTEST_DIR/sdk/go/src/web-sdk.git"
    WORKTREE_PATH="$XTEST_DIR/sdk/go/src/$BRANCH"
    REPO_URL="https://github.com/opentdf/otdfctl"
    ;;
  *)
    echo "Error: Unsupported language '$LANGUAGE'. Supported values are 'js', 'java', or 'go'." >&2
    exit 1
    ;;
esac

# Function to execute a command and handle errors
run_command() {
  "$@"
  local status=$?
  if [[ $status -ne 0 ]]; then
    echo "Error: Command '$*' failed." >&2
    exit $status
  fi
}

# Clone the repository as bare if it doesn't exist
if [[ ! -d $BARE_REPO_PATH ]]; then
  echo "Cloning $REPO_URL as a bare repository into $BARE_REPO_PATH..."
  run_command git clone --bare "$REPO_URL" "$BARE_REPO_PATH"
else
  echo "Bare repository already exists at $BARE_REPO_PATH. Fetching updates..."
  run_command git --git-dir="$BARE_REPO_PATH" fetch --all
fi

# Check if the worktree for the specified branch exists
if [[ -d $WORKTREE_PATH ]]; then
  echo "Worktree for branch '$BRANCH' already exists at $WORKTREE_PATH. Updating..."
  run_command git --git-dir="$BARE_REPO_PATH" --work-tree="$WORKTREE_PATH" pull origin "$BRANCH"
else
  echo "Setting up worktree for branch '$BRANCH' at $WORKTREE_PATH..."
  run_command git --git-dir="$BARE_REPO_PATH" worktree add "$WORKTREE_PATH" "$BRANCH"
fi
