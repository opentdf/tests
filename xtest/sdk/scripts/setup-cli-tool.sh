#!/bin/bash
# Checks out up to 4 versions of a given SDK and builds them
# Usage: ./setup-cli-tool.sh [sdk] [version1 version2]
# Example: ./setup-cli-tool.sh go main latest 1.2.5

set -e

# Inputs
SDK=${1:-go} # Default to 'go' if not provided
VERSION=${2:-latest} # Default to 'latest' if not provided

# Validate SDK input
case "$SDK" in
  "go")
    SDK_REPO="opentdf/platform"
    ;;
  "java")
    SDK_REPO="opentdf/java-sdk"
    ;;
  "js")
    SDK_REPO="opentdf/web-sdk"
    ;;
  *)
    echo "Invalid SDK specified: $SDK"
    exit 1
    ;;
esac

echo "SDK: $SDK"
echo "SDK Repo: $SDK_REPO"

# Validate version string
if [[ ! "$VERSION" =~ ^[0-9a-zA-Z\.\ ]+$ ]]; then
  echo "Invalid version string: $VERSION"
  exit 1
fi

if [[ $(echo "$VERSION" | wc -w) -gt 4 ]]; then
  echo "Too many versions specified: $VERSION"
  exit 1
fi

# Checkout xtest/sdk folder
echo "Checking out xtest/sdk folder..."
git clone --depth 1 --filter=blob:none --sparse https://github.com/opentdf/platform.git otdf-sdk
cd otdf-sdk
git sparse-checkout set xtest/sdk
cd ..

# Resolve versions
echo "Resolving versions..."
VERSION_INFO=$(./scripts/resolve-version.py "$SDK" $VERSION)
VERSION_A=$(echo "$VERSION_INFO" | jq -r '.[0] // empty')
VERSION_B=$(echo "$VERSION_INFO" | jq -r '.[1] // empty')
VERSION_C=$(echo "$VERSION_INFO" | jq -r '.[2] // empty')
VERSION_D=$(echo "$VERSION_INFO" | jq -r '.[3] // empty')

echo "Resolved Versions:"
echo "Version A: $VERSION_A"
echo "Version B: $VERSION_B"
echo "Version C: $VERSION_C"
echo "Version D: $VERSION_D"

# Checkout versions
checkout_version() {
  local version=$1
  local path=$2
  if [[ -n "$version" ]]; then
    echo "Checking out version $version to $path..."
    git clone --depth 1 --branch "$(echo "$version" | jq -r '.sha')" https://github.com/$SDK_REPO "$path"
  fi
}

checkout_version "$VERSION_A" "otdf-sdk/${SDK}-src-a"
checkout_version "$VERSION_B" "otdf-sdk/${SDK}-src-b"
checkout_version "$VERSION_C" "otdf-sdk/${SDK}-src-c"
checkout_version "$VERSION_D" "otdf-sdk/${SDK}-src-d"

# Set up environment for specific SDKs
if [[ "$SDK" == "java" ]]; then
  echo "Setting up JDK 11..."
  export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
fi

if [[ "$SDK" == "js" ]]; then
  echo "Setting up Node.js 22..."
  export NODE_VERSION="22.x"
  npm install --prefix otdf-sdk/web-sdk/lib
  npm install --prefix otdf-sdk/web-sdk/cli
fi

# Build all checked-out versions
echo "Building all checked-out versions..."
for sdk_dir in otdf-sdk/${SDK}-src-*; do
  if [[ -d "$sdk_dir" ]]; then
    echo "Building in $sdk_dir..."
    case "$SDK" in
      "go")
        make -C "$sdk_dir" PLATFORM_DIR="$sdk_dir"
        ;;
      "java")
        make -C "$sdk_dir"
        ;;
      "js")
        make -C "$sdk_dir" JS_DIR="$sdk_dir"
        ;;
      *)
        echo "Unknown SDK: $SDK"
        exit 1
        ;;
    esac
  fi
done

echo "Setup complete!"
