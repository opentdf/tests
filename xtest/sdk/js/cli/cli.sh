#!/usr/bin/env bash

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source "$SCRIPT_DIR"/../../../test.env

args=(
  --output "$3"
  --kasEndpoint "$KASURL"
  --oidcEndpoint "$KCFULLURL"
  --auth opentdf:secret
)
# default for js cli is nano
if [ "$4" == "False" ]; then 
    args+=(--containerType tdf3)
fi
if [ "$1" == "encrypt" ]; then
   npx @opentdf/cli encrypt "$2" "${args[@]}"
elif [ "$1" == "decrypt" ]; then
   npx @opentdf/cli decrypt "$2" "${args[@]}"
else
    echo "Incorrect argument provided"
    exit 1
fi
