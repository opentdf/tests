#!/usr/bin/env bash
# shellcheck disable=SC2206,SC1091

# Common shell wrapper used to interface to SDK implementation.
#
# Usage: ./cli.sh <encrypt | decrypt> <src-file> <dst-file> <nano>
#
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)

# shellcheck source=../../test.env
source "$SCRIPT_DIR"/../../test.env

args=(
  "--client-id=$CLIENTID"
  "--client-secret=$CLIENTSECRET"
  "--platform-endpoint=$PLATFORMENDPOINT"
  -i
)
COMMAND="$1"
if [ "$4" == "nano" ]; then
  COMMAND="$1"nano
fi
args+=("$COMMAND")

if [ "$1" == "encrypt" ]; then
  args+=(--kas-url=$KASURL)
fi

echo java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" -f "$2" ">" "$3"
java -jar "$SCRIPT_DIR"/cmdline.jar "${args[@]}" -f "$2" >"$3"
