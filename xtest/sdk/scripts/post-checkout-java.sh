#!/bin/bash

# Post checkout cleanups for java
# Currently, this inserts the missing `platform.branch` property into the pom.xml files
# on older branches that do not have it defined.

# Base directory for the script
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null  && pwd)
BASE_DIR="$SCRIPT_DIR/../java/src"

# Detect the operating system to use the correct sed syntax
if [[ "$(uname)" == "Darwin" ]]; then
  SED_CMD="sed -i ''"
else
  SED_CMD="sed -i"
fi

# Map Java SDK version to compatible platform protocol branch
# Must match the mappings in resolve-version.py
get_platform_branch() {
  local version="$1"
  case "$version" in
    0.7.8 | 0.7.7) echo "protocol/go/v0.2.29" ;;
    0.7.6) echo "protocol/go/v0.2.25" ;;
    0.7.5 | 0.7.4) echo "protocol/go/v0.2.18" ;;
    0.7.3 | 0.7.2) echo "protocol/go/v0.2.17" ;;
    0.6.1 | 0.6.0) echo "protocol/go/v0.2.14" ;;
    0.5.0) echo "protocol/go/v0.2.13" ;;
    0.4.0 | 0.3.0 | 0.2.0) echo "protocol/go/v0.2.10" ;;
    0.1.0) echo "protocol/go/v0.2.3" ;;
    *) echo "main" ;; # Default to main for unknown/newer versions
  esac
  return 0
}

# Loop through all subdirectories in the base directory
find "$BASE_DIR" -mindepth 1 -maxdepth 1 -type d -not -name "*.git" | while read -r SRC_DIR; do
  POM_FILE="$SRC_DIR/sdk/pom.xml"

  # Skip if path or file does not exist
  if [[ ! -f $POM_FILE ]]; then
    echo "No pom.xml file found in $SRC_DIR, skipping."
    continue
  fi

  # Extract version from directory name (e.g., "v0.7.5" -> "0.7.5", "main" -> "main")
  DIR_NAME=$(basename "$SRC_DIR")
  VERSION="${DIR_NAME#v}" # Remove leading 'v' if present
  PLATFORM_BRANCH=$(get_platform_branch "$VERSION")

  # Check if the correct platform.branch is already set
  if grep -q "<platform.branch>$PLATFORM_BRANCH</platform.branch>" "$POM_FILE"; then
    echo "platform.branch already set to $PLATFORM_BRANCH in $POM_FILE, skipping."
    continue
  fi

  # If we don't have a specific mapping for this version (defaults to "main"),
  # check if the pom.xml already has a valid protocol/go branch set - don't overwrite it
  if [[ "$PLATFORM_BRANCH" == "main" ]]; then
    if grep -q "<platform.branch>protocol/go/" "$POM_FILE"; then
      EXISTING_BRANCH=$(grep -o "<platform.branch>[^<]*</platform.branch>" "$POM_FILE" | sed 's/<[^>]*>//g')
      echo "platform.branch already set to $EXISTING_BRANCH in $POM_FILE (no mapping for version $VERSION), skipping."
      continue
    fi
  fi

  echo "Updating $POM_FILE (version=$VERSION, platform.branch=$PLATFORM_BRANCH)..."

  # Check if platform.branch property exists (possibly with wrong value)
  if grep -q "<platform.branch>" "$POM_FILE"; then
    # Replace existing platform.branch value with the correct one
    $SED_CMD "s|<platform.branch>[^<]*</platform.branch>|<platform.branch>$PLATFORM_BRANCH</platform.branch>|g" "$POM_FILE"
    echo "Updated existing platform.branch to $PLATFORM_BRANCH in $POM_FILE"
  else
    # Add the platform.branch property to the <properties> section
    $SED_CMD "/<properties>/a \\
        <platform.branch>$PLATFORM_BRANCH</platform.branch>" "$POM_FILE"

    # Only replace branch=main if the property now exists (sed above may have failed silently if no <properties> section)
    if grep -q "<platform.branch>" "$POM_FILE"; then
      # Replace hardcoded branch=main with branch=${platform.branch} in the maven-antrun-plugin configuration
      # shellcheck disable=SC2016 # Literal $; it is for a variable expansion in the maven file
      $SED_CMD 's/branch=main/branch=${platform.branch}/g' "$POM_FILE"
      echo "Added platform.branch=$PLATFORM_BRANCH and updated branch references in $POM_FILE"
    else
      # No <properties> section exists, directly replace branch=main with the actual branch value
      $SED_CMD "s|branch=main|branch=$PLATFORM_BRANCH|g" "$POM_FILE"
      echo "No <properties> section, directly replaced branch=main with branch=$PLATFORM_BRANCH in $POM_FILE"
    fi
  fi
done

echo "Update complete."
