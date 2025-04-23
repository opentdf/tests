#!/bin/bash

# Post checkout cleanups for java
# Currently, this inserts the missing `platform.branch` property into the pom.xml files
# on older branches that do not have it defined.

# Base directory for the script
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
BASE_DIR="$SCRIPT_DIR/../java/src"

# Detect the operating system to use the correct sed syntax
if [[ "$(uname)" == "Darwin" ]]; then
  SED_CMD="sed -i ''"
else
  SED_CMD="sed -i"
fi

# Loop through all subdirectories in the base directory
find "$BASE_DIR" -mindepth 1 -maxdepth 1 -type d -not -name "*.git" | while read -r SRC_DIR; do
  POM_FILE="$SRC_DIR/sdk/pom.xml"

  # Skip if path or file does not exist
  if [[ ! -f $POM_FILE ]]; then
    echo "No pom.xml file found in $SRC_DIR, skipping."
    continue
  fi

  # Check if the platform.branch property is already defined
  if grep -q "<platform.branch>" "$POM_FILE"; then
    echo "platform.branch already defined in $POM_FILE, skipping."
    continue
  fi

  echo "Updating $POM_FILE..."

  # Add the platform.branch property to the <properties> section
  $SED_CMD '/<properties>/a \
        <platform.branch>main</platform.branch>' "$POM_FILE"

  # Replace hardcoded branch=main with branch=${platform.branch} in the maven-antrun-plugin configuration
  # shellcheck disable=SC2016 # Literal $; it is for a variable expansion in the maven file
  $SED_CMD 's/branch=main/branch=${platform.branch}/g' "$POM_FILE"
done

echo "Update complete."
