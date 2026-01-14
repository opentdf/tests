#!/bin/bash
# Lists all checked-out SDK versions and their build status
#
# Usage: ./list-available.sh [--format json|table]
# Example: ./list-available.sh --format table

set -uo pipefail

# Resolve script directory
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
XTEST_DIR=$(cd -- "$SCRIPT_DIR/../../" &>/dev/null && pwd)

# Parse arguments
FORMAT="${1:-json}"
if [[ $FORMAT == "--format" ]]; then
  FORMAT="${2:-json}"
fi

# Function to get SHA for a worktree
get_worktree_sha() {
  local worktree_path=$1

  if [[ -e "$worktree_path/.git" ]]; then
    git -C "$worktree_path" rev-parse HEAD 2>/dev/null || echo "unknown"
  else
    echo "unknown"
  fi
}

# Function to check if a version is built
is_built() {
  local sdk=$1
  local version=$2
  local dist_path="$XTEST_DIR/sdk/$sdk/dist/$version"

  if [[ -d "$dist_path" ]]; then
    echo "true"
    return 0
  else
    echo "false"
    return 1
  fi
}

# Function to get dist path if built
get_dist_path() {
  local sdk=$1
  local version=$2
  local dist_path="$XTEST_DIR/sdk/$sdk/dist/$version"

  if [[ -d "$dist_path" ]]; then
    echo "$dist_path"
  else
    echo "null"
  fi
}

# Function to collect SDK info
collect_sdk_info() {
  local sdk=$1
  local bare_repo_name=$2
  local bare_repo_path="$XTEST_DIR/sdk/$sdk/src/$bare_repo_name"
  local src_dir="$XTEST_DIR/sdk/$sdk/src"

  # Check if bare repo exists
  if [[ ! -d "$bare_repo_path" ]]; then
    echo "null"
    return
  fi

  # Start building worktrees array
  local worktrees_json="[]"
  local worktree_count=0

  # Iterate through all directories in src/
  for dir in "$src_dir"/*; do
    # Skip if not a directory
    [[ ! -d "$dir" ]] && continue

    # Skip the bare repo itself
    [[ "$dir" == "$bare_repo_path" ]] && continue

    # Skip if it ends with .git
    [[ "$dir" == *.git ]] && continue

    local version=$(basename "$dir")
    local sha=$(get_worktree_sha "$dir")
    local built=$(is_built "$sdk" "$version")
    local dist_path=$(get_dist_path "$sdk" "$version")

    # Build dist_path JSON value
    local dist_path_json="null"
    if [[ "$dist_path" != "null" ]]; then
      dist_path_json="\"$dist_path\""
    fi

    # Build JSON for this worktree
    local worktree_json=$(cat <<EOF
{
  "version": "$version",
  "sha": "$sha",
  "path": "$dir",
  "built": $built,
  "dist_path": $dist_path_json
}
EOF
)

    # Add to array
    if [[ $worktree_count -eq 0 ]]; then
      worktrees_json="[$worktree_json"
    else
      worktrees_json="$worktrees_json,$worktree_json"
    fi
    ((worktree_count++))
  done

  # Close array
  if [[ $worktree_count -gt 0 ]]; then
    worktrees_json="$worktrees_json]"
  fi

  # Build SDK JSON
  cat <<EOF
{
  "bare_repo": "$bare_repo_path",
  "worktrees": $worktrees_json
}
EOF
}

# Collect info for all SDKs
GO_INFO=$(collect_sdk_info "go" "otdfctl.git")
JAVA_INFO=$(collect_sdk_info "java" "java-sdk.git")
JS_INFO=$(collect_sdk_info "js" "web-sdk.git")

# Build final JSON
JSON_OUTPUT=$(cat <<EOF
{
  "go": $GO_INFO,
  "java": $JAVA_INFO,
  "js": $JS_INFO
}
EOF
)

if [[ "$FORMAT" == "json" ]]; then
  echo "$JSON_OUTPUT"
elif [[ "$FORMAT" == "table" ]]; then
  # Parse JSON and output as table
  echo "SDK    VERSION           SHA       BUILT  PATH"
  echo "─────  ────────────────  ────────  ─────  ────────────────────────────────────────"

  for sdk in go java js; do
    # Extract worktrees for this SDK
    worktrees=$(echo "$JSON_OUTPUT" | grep -A 999 "\"$sdk\":" | grep -A 999 "\"worktrees\":" | sed -n '/\[/,/\]/p' | grep -v "bare_repo")

    # Parse each worktree
    while IFS= read -r line; do
      if [[ "$line" =~ \"version\":[[:space:]]*\"([^\"]+)\" ]]; then
        version="${BASH_REMATCH[1]}"
      fi
      if [[ "$line" =~ \"sha\":[[:space:]]*\"([^\"]+)\" ]]; then
        sha="${BASH_REMATCH[1]}"
        sha_short="${sha:0:7}"
      fi
      if [[ "$line" =~ \"built\":[[:space:]]*(true|false) ]]; then
        built="${BASH_REMATCH[1]}"
        if [[ "$built" == "true" ]]; then
          built_symbol="✓"
        else
          built_symbol="✗"
        fi
      fi
      if [[ "$line" =~ \"path\":[[:space:]]*\"([^\"]+)\" ]]; then
        path="${BASH_REMATCH[1]}"
        # Print the row when we have all data
        if [[ -n "${version:-}" && -n "${sha_short:-}" && -n "${built_symbol:-}" && -n "${path:-}" ]]; then
          printf "%-6s %-17s %-9s %-6s %s\n" "$sdk" "$version" "$sha_short" "$built_symbol" "$path"
          version=""
          sha_short=""
          built_symbol=""
          path=""
        fi
      fi
    done <<< "$worktrees"
  done
else
  echo "Error: Unknown format '$FORMAT'. Use 'json' or 'table'." >&2
  exit 1
fi
