#!/bin/bash
# Removes a specific SDK worktree checkout.
#
# Usage: ./remove-checkout.sh [sdk language] [branch]
# Example: ./remove-checkout.sh js main
#
# This script safely removes a worktree and cleans up the git worktree registry.
# It does NOT remove the bare repository or build artifacts.

# Resolve script directory
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
XTEST_DIR=$(cd -- "$SCRIPT_DIR/../../" &>/dev/null && pwd)

# Parse arguments
LANGUAGE=${1:-}
BRANCH=${2:-}

if [[ -z "$LANGUAGE" ]]; then
    echo "Error: SDK language is required." >&2
    echo "Usage: $0 [sdk language] [branch]" >&2
    echo "Example: $0 go main" >&2
    exit 1
fi

if [[ -z "$BRANCH" ]]; then
    echo "Error: Branch name is required." >&2
    echo "Usage: $0 [sdk language] [branch]" >&2
    echo "Example: $0 go main" >&2
    exit 1
fi

# Replace slashes in branch name with double dashes for local naming
LOCAL_NAME=${BRANCH//\//--}

# Strip well known prefixes for monorepo output
if [[ $LOCAL_NAME == sdk--* ]]; then
  LOCAL_NAME=${LOCAL_NAME#sdk--}
fi

case "$LANGUAGE" in
  js)
    BARE_REPO_PATH="$XTEST_DIR/sdk/js/src/web-sdk.git"
    WORKTREE_PATH="$XTEST_DIR/sdk/js/src/$LOCAL_NAME"
    ;;
  java)
    BARE_REPO_PATH="$XTEST_DIR/sdk/java/src/java-sdk.git"
    WORKTREE_PATH="$XTEST_DIR/sdk/java/src/$LOCAL_NAME"
    ;;
  go)
    BARE_REPO_PATH="$XTEST_DIR/sdk/go/src/otdfctl.git"
    WORKTREE_PATH="$XTEST_DIR/sdk/go/src/$LOCAL_NAME"
    ;;
  *)
    echo "Error: Unsupported language '$LANGUAGE'. Supported values are 'js', 'java', or 'go'." >&2
    exit 1
    ;;
esac

# Check if bare repo exists
if [[ ! -d "$BARE_REPO_PATH" ]]; then
    echo "⚠️  Bare repository not found at $BARE_REPO_PATH"
    echo "Nothing to remove."
    exit 0
fi

# Check if worktree exists
if [[ ! -d "$WORKTREE_PATH" ]]; then
    echo "⚠️  Worktree not found at $WORKTREE_PATH"
    echo "Checking if it's registered in git worktree list..."

    # Check if it's still registered but missing
    if git --git-dir="$BARE_REPO_PATH" worktree list | grep -q "$WORKTREE_PATH"; then
        echo "📋 Worktree is registered but directory is missing. Pruning..."
        git --git-dir="$BARE_REPO_PATH" worktree prune
        echo "✅ Pruned stale worktree registration"
    else
        echo "Nothing to remove."
    fi
    exit 0
fi

# Remove the worktree
echo "🗑️  Removing $LANGUAGE/$LOCAL_NAME worktree..."
if git --git-dir="$BARE_REPO_PATH" worktree remove "$WORKTREE_PATH" --force; then
    echo "✅ Successfully removed worktree at $WORKTREE_PATH"

    # Prune to clean up any stale entries
    git --git-dir="$BARE_REPO_PATH" worktree prune
    echo "✓  Cleaned up worktree registry"
else
    echo "❌ Failed to remove worktree" >&2
    exit 1
fi
