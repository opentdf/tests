#!/usr/bin/env bash
#
# Update all checked-out SDK main branches to latest and rebuild
#
# Usage:
#   ./update-all.sh           # Update main branches only
#   ./update-all.sh --all     # Update all checked-out versions
#
# This script:
# - Pulls latest commits for SDK worktrees (main by default, or all with --all)
# - Reports SHA changes for each SDK
# - Automatically rebuilds only the SDKs that were updated
# - Skips SDKs that aren't checked out

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
SDK_DIR="$(dirname "$SCRIPT_DIR")"

# Array of SDKs to update
SDKS=("go" "java" "js")

# Parse arguments
UPDATE_ALL=false
if [[ "${1:-}" == "--all" ]]; then
    UPDATE_ALL=true
    shift
fi

# Function to update a single SDK's main branch
update_sdk_main() {
    local sdk=$1
    local main_dir="$SDK_DIR/$sdk/src/main"

    if [[ ! -d "$main_dir" ]]; then
        echo "⚠️  $sdk: main branch not checked out (skipping)"
        return 0
    fi

    echo "📥 Updating $sdk main branch..."
    cd "$main_dir"

    # Get current SHA for comparison
    local old_sha=$(git rev-parse HEAD)

    # Pull latest changes
    git pull origin main

    # Get new SHA
    local new_sha=$(git rev-parse HEAD)

    # Report if updated
    if [[ "$old_sha" != "$new_sha" ]]; then
        echo "✅ $sdk updated: ${old_sha:0:7} → ${new_sha:0:7}"
        return 1  # Return 1 to indicate update occurred
    else
        echo "✓  $sdk already up to date (${old_sha:0:7})"
        return 0
    fi
}

# Function to update all worktrees for a SDK
update_sdk_all_versions() {
    local sdk=$1
    local src_dir="$SDK_DIR/$sdk/src"
    local updated_versions=()

    if [[ ! -d "$src_dir" ]]; then
        echo "⚠️  $sdk: source directory not found (skipping)"
        return 0
    fi

    # Find all worktrees (directories except .git)
    local found_worktrees=false
    for dir in "$src_dir"/*; do
        if [[ -d "$dir" ]] && [[ "$(basename "$dir")" != *.git ]]; then
            found_worktrees=true
            local version=$(basename "$dir")
            echo "📥 Updating $sdk/$version..."

            cd "$dir"
            local old_sha=$(git rev-parse HEAD)

            # Determine branch name
            local branch=$(git rev-parse --abbrev-ref HEAD)

            if [[ "$branch" == "HEAD" ]]; then
                echo "⚠️  $sdk/$version: detached HEAD (skipping)"
                continue
            fi

            # Pull latest changes
            if git pull origin "$branch" 2>/dev/null; then
                local new_sha=$(git rev-parse HEAD)
                if [[ "$old_sha" != "$new_sha" ]]; then
                    echo "✅ $sdk/$version updated: ${old_sha:0:7} → ${new_sha:0:7}"
                    updated_versions+=("$version")
                else
                    echo "✓  $sdk/$version already up to date (${old_sha:0:7})"
                fi
            else
                echo "⚠️  $sdk/$version: git pull failed (skipping)"
            fi
        fi
    done

    if [[ "$found_worktrees" == "false" ]]; then
        echo "⚠️  $sdk: no worktrees checked out (skipping)"
        return 0
    fi

    # Return 1 if any versions were updated
    if [[ ${#updated_versions[@]} -gt 0 ]]; then
        return 1
    else
        return 0
    fi
}

main() {
    if [[ "$UPDATE_ALL" == "true" ]]; then
        echo "=== Updating All SDK Versions ==="
    else
        echo "=== Updating SDK Main Branches ==="
    fi
    echo ""

    local updated_sdks=()

    # Update all SDKs
    for sdk in "${SDKS[@]}"; do
        if [[ "$UPDATE_ALL" == "true" ]]; then
            if update_sdk_all_versions "$sdk"; then
                # No update needed
                :
            else
                # Update occurred
                updated_sdks+=("$sdk")
            fi
        else
            if update_sdk_main "$sdk"; then
                # No update needed
                :
            else
                # Update occurred
                updated_sdks+=("$sdk")
            fi
        fi
        echo ""
    done

    # Rebuild if any SDKs were updated
    if [[ ${#updated_sdks[@]} -gt 0 ]]; then
        echo "=== Rebuilding Updated SDKs ==="
        echo "Updated SDKs: ${updated_sdks[*]}"
        echo ""

        cd "$SDK_DIR"

        # Rebuild each updated SDK
        for sdk in "${updated_sdks[@]}"; do
            echo "🔨 Building $sdk..."
            make "$sdk"
            echo ""
        done

        echo "✅ All updates complete!"
    else
        echo "✅ All SDKs already up to date. No rebuild needed."
    fi
}

main "$@"
