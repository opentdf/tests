#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# shellcheck source=../../test.env
source "$SCRIPT_DIR"/../../test.env

## USES THE PLATFORM/EXAMPLES CLI

args=(
  -o "$3"
  --creds $CLIENTID:$CLIENTSECRET
  --platformEndpoint $PLATFORMURL
  --tokenEndpoint $TOKENENDPOINT
)

if [ "$1" == "encrypt" ]; then
    if [ "$4" == "True" ]; then
        args+=(--nano)
    fi
    FILE_INPUT=$(cat "$2")
    "$SCRIPT_DIR"/examples encrypt "${args[@]}" --autoconfigure=false "$FILE_INPUT"
elif [ "$1" == "decrypt" ]; then
    "$SCRIPT_DIR"/examples decrypt "${args[@]}" "$2"
else
    echo "Incorrect argument provided"
    exit 1
fi

