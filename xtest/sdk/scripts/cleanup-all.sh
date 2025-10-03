#!/bin/bash
# Removes the checked out branches of each of the sdks under test

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# Function to get the bare repo path for each SDK
get_bare_repo_path() {
  local sdk=$1
  case "$sdk" in
    js)
      echo "$SCRIPT_DIR/../js/src/web-sdk.git"
      ;;
    java)
      echo "$SCRIPT_DIR/../java/src/java-sdk.git"
      ;;
    go)
      echo "$SCRIPT_DIR/../go/src/otdfctl.git"
      ;;
    *)
      echo ""
      ;;
  esac
}

for sdk in go java js; do
  rm -rf "$SCRIPT_DIR/../$sdk/dist"
  
  bare_repo_path=$(get_bare_repo_path "$sdk")
  
  for branch in "$SCRIPT_DIR/../${sdk}/src/"*; do
    # Check if the path ends with .git (skip bare repos)
    if [[ $branch == *.git ]]; then
      continue
    fi
    
    if [ -d "$branch" ]; then
      if ! git --git-dir="$bare_repo_path" worktree remove "$branch" --force; then
        echo "Failed to remove worktree: $sdk#$branch"
      fi
      rm -rf "$branch"
    fi
  done
  
  # Clean up any orphaned worktree registrations
  if [[ -d "$bare_repo_path" ]]; then
    echo "Pruning orphaned worktrees for $sdk..."
    git --git-dir="$bare_repo_path" worktree prune 2>/dev/null || true
  fi
done
