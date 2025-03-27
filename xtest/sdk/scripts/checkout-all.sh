#!/bin/bash
# Checks out the latest `main` branch of each of the sdks under test
# and builds them.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

for sdk in go java js; do
  if ! $SCRIPT_DIR/checkout-sdk-branch.sh $sdk main; then
    echo "Failed to checkout $sdk main branch"
    exit 1
  fi
done
